import json
import csv
import io
import logging
import threading
from datetime import datetime, date, timedelta
from django.db import connection, transaction
from django.db.models import ProtectedError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.views.generic import TemplateView
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    Skill, Developer, DeveloperSkill, Project, ProjectSlot, 
    SlotSkillRequirement, Allocation, SolverRun, AllocationProposal,
    DeveloperLeave, AllocationAuditLog
)
from .serializers import (
    SkillSerializer, DeveloperSerializer, DeveloperSkillSerializer,
    ProjectSerializer, ProjectSlotSerializer, SlotSkillRequirementSerializer,
    AllocationSerializer, SolverRunSerializer, AllocationProposalSerializer,
    DeveloperLeaveSerializer, AllocationAuditLogSerializer
)
from staffing.solver.runner import run_optimization_engine
from staffing.solver.eligibility import check_date_overlap
from staffing.permissions import DemoAwareAdminPermission


MAX_UPLOAD_FILE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_UPLOAD_ROWS = 2000

logger = logging.getLogger('benchzero.bulk_upload')


def _parse_skills_string(skills_str):
    if not skills_str:
        return []
    result = []
    delimiter = '|' if '|' in skills_str else ','
    parts = [p.strip() for p in skills_str.split(delimiter) if p.strip()]
    for part in parts:
        if ':' in part:
            subparts = part.split(':')
            name = subparts[0].strip()
            try:
                level = int(subparts[1].strip())
            except ValueError:
                level = 3
        else:
            name = part.strip()
            level = 3
        if name:
            result.append({'name': name, 'proficiency_level': min(max(level, 1), 5)})
    return result


def _parse_slot_skills_string(skills_str):
    if not skills_str:
        return []
    result = []
    delimiter = '|' if '|' in skills_str else ','
    parts = [p.strip() for p in skills_str.split(delimiter) if p.strip()]
    for part in parts:
        subparts = part.split(':')
        name = subparts[0].strip()
        min_prof = 2
        is_mand = True
        if len(subparts) >= 2:
            try:
                min_prof = int(subparts[1].strip())
            except ValueError:
                min_prof = 2
        if len(subparts) >= 3:
            flag = subparts[2].strip().lower()
            if flag in ('optional', 'false', '0'):
                is_mand = False
        if name:
            result.append({
                'name': name,
                'min_proficiency': min(max(min_prof, 1), 5),
                'is_mandatory': is_mand
            })
    return result


from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from rest_framework.views import APIView


class AuthStatusView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({
            'is_authenticated': request.user.is_authenticated,
            'username': request.user.username if request.user.is_authenticated else '',
            'is_staff': request.user.is_staff if request.user.is_authenticated else False,
            'require_auth_for_writes': getattr(settings, 'REQUIRE_AUTH_FOR_WRITES', False)
        })


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '').strip()

        if not username or not password:
            return Response({'error': 'Username and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(request, username=username, password=password)
        if user is not None:
            django_login(request, user)
            return Response({
                'message': 'Login successful',
                'user': {
                    'username': user.username,
                    'is_staff': user.is_staff
                }
            }, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Invalid username or password.'}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        django_logout(request)
        return Response({'message': 'Logged out successfully.'}, status=status.HTTP_200_OK)


class DashboardView(TemplateView):
    template_name = 'index.html'


class SkillViewSet(viewsets.ModelViewSet):
    queryset = Skill.objects.all().order_by('category', 'name')
    serializer_class = SkillSerializer

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [DemoAwareAdminPermission()]
        return super().get_permissions()


class DeveloperViewSet(viewsets.ModelViewSet):
    queryset = Developer.objects.all().prefetch_related('developer_skills__skill', 'leaves').order_by('name')
    serializer_class = DeveloperSerializer

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy', 'add_skill', 'upload_developers'):
            return [DemoAwareAdminPermission()]
        return super().get_permissions()

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {
                    'error': "Cannot delete Developer because active or historical allocations refer to it. "
                             "Cancel or clear related allocations first."
                },
                status=status.HTTP_409_CONFLICT
            )

    @action(detail=True, methods=['post'], url_path='add-skill')
    def add_skill(self, request, pk=None):
        developer = self.get_object()
        skill_id = request.data.get('skill_id')
        proficiency_level = request.data.get('proficiency_level', 3)

        if not skill_id:
            return Response({'error': 'skill_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        dev_skill, created = DeveloperSkill.objects.update_or_create(
            developer=developer,
            skill_id=skill_id,
            defaults={'proficiency_level': proficiency_level}
        )
        serializer = DeveloperSkillSerializer(dev_skill)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='upload')
    def upload_developers(self, request):
        file_obj = request.FILES.get('file')
        raw_data = request.data.get('developers')

        dev_list = []
        filename = getattr(file_obj, 'name', '').lower()

        if file_obj:
            if getattr(file_obj, 'size', 0) > MAX_UPLOAD_FILE_BYTES:
                return Response(
                    {'error': f"File too large ({file_obj.size} bytes). Maximum allowed is {MAX_UPLOAD_FILE_BYTES // (1024 * 1024)} MB."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            try:
                content = file_obj.read().decode('utf-8-sig', errors='replace')
            except Exception as e:
                return Response({'error': f"Failed to read file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

            if filename.endswith('.json') or content.strip().startswith('[') or content.strip().startswith('{'):
                try:
                    parsed = json.loads(content)
                    dev_list = parsed.get('developers', parsed) if isinstance(parsed, dict) else parsed
                except Exception as e:
                    return Response({'error': f"Invalid JSON format: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
            else:
                reader = csv.DictReader(io.StringIO(content))
                dev_list = list(reader)
        elif raw_data:
            if isinstance(raw_data, str):
                try:
                    dev_list = json.loads(raw_data)
                except Exception as e:
                    return Response({'error': f"Invalid JSON body: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
            elif isinstance(raw_data, list):
                dev_list = raw_data
        else:
            return Response({'error': 'No file or developers data provided.'}, status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(dev_list, list):
            return Response({'error': 'Input data must be a list of developer objects.'}, status=status.HTTP_400_BAD_REQUEST)

        if len(dev_list) > MAX_UPLOAD_ROWS:
            return Response(
                {'error': f"Too many rows ({len(dev_list)}). Maximum allowed per upload is {MAX_UPLOAD_ROWS}. Split the file into smaller batches."},
                status=status.HTTP_400_BAD_REQUEST
            )

        imported_count = 0
        updated_count = 0
        errors = []
        warnings = []

        # NOTE on skill merging: uploading a developer with a partial `skills`
        # list only creates/updates the skills listed -- it never removes an
        # existing DeveloperSkill that isn't mentioned in this row. Re-uploading
        # someone with just a title change, for example, will not wipe their
        # previously recorded skills.
        for idx, item in enumerate(dev_list, start=1):
            # Each row gets its own savepoint. A bad or unexpectedly-erroring
            # row is rolled back and reported individually -- it can never
            # discard the rows that already succeeded earlier in the same
            # request, which is what "transactional batch processing with
            # row-by-row feedback" actually requires.
            try:
                with transaction.atomic():
                    if not isinstance(item, dict):
                        errors.append(f"Row {idx}: Item is not an object/dictionary.")
                        continue

                    name = str(item.get('name') or item.get('full_name') or '').strip()
                    email = str(item.get('email') or '').strip()
                    title = str(item.get('title') or item.get('job_title') or 'Senior Software Engineer').strip()
                    raw_cost = item.get('hourly_cost') or item.get('rate') or item.get('cost') or 75.0
                    raw_hours = item.get('max_weekly_hours') or item.get('hours') or 40

                    if not name:
                        errors.append(f"Row {idx}: Missing developer name.")
                        continue

                    if not email:
                        errors.append(f"Row {idx} ({name}): Missing email address.")
                        continue

                    try:
                        validate_email(email)
                    except ValidationError:
                        errors.append(f"Row {idx} ({name}): Invalid email format '{email}'.")
                        continue

                    try:
                        cost = float(raw_cost)
                        if cost < 0:
                            raise ValueError()
                    except ValueError:
                        errors.append(f"Row {idx} ({name}): Invalid hourly cost '{raw_cost}'. Must be a non-negative number.")
                        continue

                    try:
                        hours = int(raw_hours)
                        if not (1 <= hours <= 80):
                            raise ValueError()
                    except ValueError:
                        errors.append(f"Row {idx} ({name}): Invalid max weekly hours '{raw_hours}'. Must be between 1 and 80.")
                        continue

                    existing = Developer.objects.filter(email=email).first()
                    if existing is not None:
                        changed_fields = [
                            f for f, old, new in (
                                ('name', existing.name, name),
                                ('title', existing.title, title),
                                ('hourly_cost', float(existing.hourly_cost), cost),
                                ('max_weekly_hours', existing.max_weekly_hours, hours),
                            ) if old != new
                        ]
                        if changed_fields:
                            logger.info(
                                "Bulk upload updating developer %s (row %s): fields changed=%s",
                                email, idx, changed_fields
                            )

                    dev, created = Developer.objects.update_or_create(
                        email=email,
                        defaults={
                            'name': name,
                            'title': title,
                            'hourly_cost': cost,
                            'max_weekly_hours': hours,
                        }
                    )

                    if created:
                        imported_count += 1
                    else:
                        updated_count += 1

                    skills_input = item.get('skills', [])
                    parsed_skills = []
                    if isinstance(skills_input, list):
                        for sk in skills_input:
                            if isinstance(sk, dict):
                                s_name = sk.get('name') or sk.get('skill_name') or sk.get('skill')
                                s_lvl = sk.get('proficiency_level') or sk.get('level') or sk.get('proficiency') or 3
                                if s_name:
                                    parsed_skills.append({'name': str(s_name).strip(), 'proficiency_level': int(s_lvl)})
                            elif isinstance(sk, str) and sk.strip():
                                parsed_skills.append({'name': sk.strip(), 'proficiency_level': 3})
                    elif isinstance(skills_input, str):
                        parsed_skills = _parse_skills_string(skills_input)

                    for sk in parsed_skills:
                        s_name = sk['name']
                        s_lvl = min(max(int(sk['proficiency_level']), 1), 5)
                        skill_obj, sk_created = Skill.objects.get_or_create(
                            name__iexact=s_name,
                            defaults={'name': s_name, 'category': 'backend'}
                        )
                        if sk_created:
                            warnings.append(f"Row {idx} ({name}): Created missing skill '{s_name}'.")

                        DeveloperSkill.objects.update_or_create(
                            developer=dev,
                            skill=skill_obj,
                            defaults={'proficiency_level': s_lvl}
                        )
            except Exception as e:
                # Catch-all so one malformed/unexpected row can never 500 the
                # whole request or silently roll back earlier successful rows.
                logger.exception("Bulk developer upload: unexpected error on row %s", idx)
                errors.append(f"Row {idx}: Unexpected error - {str(e)}")
                continue

        return Response({
            'success': len(errors) == 0,
            'imported_count': imported_count,
            'updated_count': updated_count,
            'errors': errors,
            'warnings': warnings
        }, status=status.HTTP_200_OK)


class DeveloperLeaveViewSet(viewsets.ModelViewSet):
    queryset = DeveloperLeave.objects.all().select_related('developer', 'approved_by').order_by('-start_date')
    serializer_class = DeveloperLeaveSerializer

    def get_permissions(self):
        if self.action in ('approve', 'revoke'):
            return [DemoAwareAdminPermission()]
        return super().get_permissions()

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        leave = self.get_object()
        leave.is_approved = True
        leave.approved_by = request.user if request.user.is_authenticated else None
        leave.save(update_fields=['is_approved', 'approved_by'])
        return Response(self.get_serializer(leave).data)

    @action(detail=True, methods=['post'], url_path='revoke')
    def revoke(self, request, pk=None):
        leave = self.get_object()
        leave.is_approved = False
        leave.approved_by = None
        leave.save(update_fields=['is_approved', 'approved_by'])
        return Response(self.get_serializer(leave).data)


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().prefetch_related('slots__skill_requirements').order_by('-priority', 'name')
    serializer_class = ProjectSerializer

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy', 'upload_projects'):
            return [DemoAwareAdminPermission()]
        return super().get_permissions()

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {
                    'error': "Cannot delete Project because active or historical allocations refer to its project slots. "
                             "Cancel or clear related allocations first."
                },
                status=status.HTTP_409_CONFLICT
            )

    @action(detail=False, methods=['post'], url_path='upload')
    def upload_projects(self, request):
        file_obj = request.FILES.get('file')
        raw_data = request.data.get('projects')

        proj_list = []
        filename = getattr(file_obj, 'name', '').lower()

        if file_obj:
            if getattr(file_obj, 'size', 0) > MAX_UPLOAD_FILE_BYTES:
                return Response(
                    {'error': f"File too large ({file_obj.size} bytes). Maximum allowed is {MAX_UPLOAD_FILE_BYTES // (1024 * 1024)} MB."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            try:
                content = file_obj.read().decode('utf-8-sig', errors='replace')
            except Exception as e:
                return Response({'error': f"Failed to read file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

            if filename.endswith('.json') or content.strip().startswith('[') or content.strip().startswith('{'):
                try:
                    parsed = json.loads(content)
                    proj_list = parsed.get('projects', parsed) if isinstance(parsed, dict) else parsed
                except Exception as e:
                    return Response({'error': f"Invalid JSON format: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
            else:
                reader = csv.DictReader(io.StringIO(content))
                proj_list = list(reader)
        elif raw_data:
            if isinstance(raw_data, str):
                try:
                    proj_list = json.loads(raw_data)
                except Exception as e:
                    return Response({'error': f"Invalid JSON body: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
            elif isinstance(raw_data, list):
                proj_list = raw_data
        else:
            return Response({'error': 'No file or projects data provided.'}, status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(proj_list, list):
            return Response({'error': 'Input data must be a list of project or project-slot objects.'}, status=status.HTTP_400_BAD_REQUEST)

        if len(proj_list) > MAX_UPLOAD_ROWS:
            return Response(
                {'error': f"Too many rows ({len(proj_list)}). Maximum allowed per upload is {MAX_UPLOAD_ROWS}. Split the file into smaller batches."},
                status=status.HTTP_400_BAD_REQUEST
            )

        imported_projects_count = 0
        updated_projects_count = 0
        imported_slots_count = 0
        errors = []
        warnings = []

        for idx, item in enumerate(proj_list, start=1):
            # Same per-row savepoint pattern as developer upload: one bad or
            # unexpectedly-erroring row/project is rolled back and reported
            # individually, without discarding rows that already succeeded.
            try:
                with transaction.atomic():
                    if not isinstance(item, dict):
                        errors.append(f"Row {idx}: Item is not an object/dictionary.")
                        continue

                    name = str(item.get('name') or item.get('project_name') or '').strip()
                    client = str(item.get('client') or '').strip()
                    raw_priority = item.get('priority') or item.get('project_priority') or 3
                    raw_budget = item.get('budget') or 50000.0
                    description = str(item.get('description') or '').strip()

                    if not name:
                        errors.append(f"Row {idx}: Missing project name.")
                        continue

                    if not client:
                        errors.append(f"Row {idx} ({name}): Missing client name.")
                        continue

                    try:
                        priority = int(raw_priority)
                        if not (1 <= priority <= 5):
                            raise ValueError()
                    except ValueError:
                        errors.append(f"Row {idx} ({name}): Invalid priority '{raw_priority}'. Must be 1 to 5.")
                        continue

                    try:
                        budget = float(raw_budget)
                        if budget < 0:
                            raise ValueError()
                    except ValueError:
                        errors.append(f"Row {idx} ({name}): Invalid budget '{raw_budget}'. Must be non-negative.")
                        continue

                    # Dedup/update key is (name, client), matching how Developer
                    # dedups on email: a re-upload of an existing project updates
                    # its priority/budget/description instead of silently leaving
                    # them stale, and the change is logged the same way.
                    existing_proj = Project.objects.filter(name=name, client=client).first()
                    if existing_proj is not None:
                        changed_fields = [
                            f for f, old, new in (
                                ('priority', existing_proj.priority, priority),
                                ('budget', float(existing_proj.budget), budget),
                                ('description', existing_proj.description, description),
                            ) if old != new
                        ]
                        if changed_fields:
                            logger.info(
                                "Bulk upload updating project '%s'/'%s' (row %s): fields changed=%s",
                                name, client, idx, changed_fields
                            )

                    project, created_proj = Project.objects.update_or_create(
                        name=name,
                        client=client,
                        defaults={
                            'priority': priority,
                            'budget': budget,
                            'description': description
                        }
                    )

                    if created_proj:
                        imported_projects_count += 1
                    else:
                        updated_projects_count += 1

                    slots_input = item.get('slots')
                    if slots_input and isinstance(slots_input, list):
                        for s_idx, slot_item in enumerate(slots_input, start=1):
                            role_title = str(slot_item.get('role_title') or slot_item.get('role') or '').strip()
                            raw_start = str(slot_item.get('start_date') or '').strip()
                            raw_end = str(slot_item.get('end_date') or '').strip()
                            s_priority = slot_item.get('priority') or priority
                            s_headcount = slot_item.get('headcount_needed') or slot_item.get('headcount') or 1
                            s_hours = slot_item.get('weekly_hours_required') or 40

                            if not role_title:
                                errors.append(f"Row {idx} Slot {s_idx}: Missing role_title.")
                                continue

                            try:
                                start_date = datetime.strptime(raw_start, '%Y-%m-%d').date()
                            except ValueError:
                                errors.append(f"Row {idx} Slot {s_idx} ({role_title}): Invalid start_date '{raw_start}'. Use YYYY-MM-DD.")
                                continue

                            try:
                                end_date = datetime.strptime(raw_end, '%Y-%m-%d').date()
                            except ValueError:
                                errors.append(f"Row {idx} Slot {s_idx} ({role_title}): Invalid end_date '{raw_end}'. Use YYYY-MM-DD.")
                                continue

                            if end_date < start_date:
                                errors.append(f"Row {idx} Slot {s_idx} ({role_title}): end_date ({end_date}) cannot be before start_date ({start_date}).")
                                continue

                            slot, created_slot = ProjectSlot.objects.update_or_create(
                                project=project,
                                role_title=role_title,
                                start_date=start_date,
                                end_date=end_date,
                                defaults={
                                    'priority': min(max(int(s_priority), 1), 5),
                                    'headcount_needed': max(int(s_headcount), 1),
                                    'weekly_hours_required': max(int(s_hours), 1)
                                }
                            )
                            if created_slot:
                                imported_slots_count += 1

                            req_skills = slot_item.get('required_skills', [])
                            parsed_reqs = []
                            if isinstance(req_skills, list):
                                for rk in req_skills:
                                    if isinstance(rk, dict):
                                        r_name = rk.get('name') or rk.get('skill_name') or rk.get('skill')
                                        r_min = rk.get('min_proficiency') or rk.get('level') or 2
                                        r_mand = rk.get('is_mandatory') if 'is_mandatory' in rk else True
                                        if r_name:
                                            parsed_reqs.append({'name': str(r_name).strip(), 'min_proficiency': int(r_min), 'is_mandatory': bool(r_mand)})
                                    elif isinstance(rk, str) and rk.strip():
                                        parsed_reqs.append({'name': rk.strip(), 'min_proficiency': 2, 'is_mandatory': True})
                            elif isinstance(req_skills, str):
                                parsed_reqs = _parse_slot_skills_string(req_skills)

                            for rk in parsed_reqs:
                                s_name = rk['name']
                                min_p = min(max(rk['min_proficiency'], 1), 5)
                                is_m = rk['is_mandatory']
                                skill_obj, sk_created = Skill.objects.get_or_create(
                                    name__iexact=s_name,
                                    defaults={'name': s_name, 'category': 'backend'}
                                )
                                SlotSkillRequirement.objects.update_or_create(
                                    project_slot=slot,
                                    skill=skill_obj,
                                    defaults={'min_proficiency': min_p, 'is_mandatory': is_m}
                                )

                    elif item.get('role_title') or item.get('role'):
                        role_title = str(item.get('role_title') or item.get('role')).strip()
                        raw_start = str(item.get('start_date') or '').strip()
                        raw_end = str(item.get('end_date') or '').strip()
                        s_priority = item.get('slot_priority') or priority
                        s_headcount = item.get('headcount_needed') or item.get('headcount') or 1
                        s_hours = item.get('weekly_hours_required') or 40

                        try:
                            start_date = datetime.strptime(raw_start, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Row {idx} ({name}): Invalid start_date '{raw_start}'. Use YYYY-MM-DD.")
                            continue

                        try:
                            end_date = datetime.strptime(raw_end, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Row {idx} ({name}): Invalid end_date '{raw_end}'. Use YYYY-MM-DD.")
                            continue

                        if end_date < start_date:
                            errors.append(f"Row {idx} ({name}): end_date ({end_date}) cannot be before start_date ({start_date}).")
                            continue

                        slot, created_slot = ProjectSlot.objects.update_or_create(
                            project=project,
                            role_title=role_title,
                            start_date=start_date,
                            end_date=end_date,
                            defaults={
                                'priority': min(max(int(s_priority), 1), 5),
                                'headcount_needed': max(int(s_headcount), 1),
                                'weekly_hours_required': max(int(s_hours), 1)
                            }
                        )
                        if created_slot:
                            imported_slots_count += 1

                        req_skills_raw = item.get('required_skills')
                        if req_skills_raw:
                            parsed_reqs = _parse_slot_skills_string(req_skills_raw)
                            for rk in parsed_reqs:
                                s_name = rk['name']
                                min_p = min(max(rk['min_proficiency'], 1), 5)
                                is_m = rk['is_mandatory']
                                skill_obj, sk_created = Skill.objects.get_or_create(
                                    name__iexact=s_name,
                                    defaults={'name': s_name, 'category': 'backend'}
                                )
                                SlotSkillRequirement.objects.update_or_create(
                                    project_slot=slot,
                                    skill=skill_obj,
                                    defaults={'min_proficiency': min_p, 'is_mandatory': is_m}
                                )
            except Exception as e:
                # Same catch-all guarantee as the developer upload: one bad or
                # unexpectedly-erroring project row can never 500 the whole
                # request or roll back rows that already succeeded.
                logger.exception("Bulk project upload: unexpected error on row %s", idx)
                errors.append(f"Row {idx}: Unexpected error - {str(e)}")
                continue

        return Response({
            'success': len(errors) == 0,
            'imported_projects_count': imported_projects_count,
            'updated_projects_count': updated_projects_count,
            'imported_slots_count': imported_slots_count,
            'errors': errors,
            'warnings': warnings
        }, status=status.HTTP_200_OK)


class ProjectSlotViewSet(viewsets.ModelViewSet):
    queryset = ProjectSlot.objects.all().select_related('project').prefetch_related('skill_requirements__skill').order_by('-priority')
    serializer_class = ProjectSlotSerializer

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy', 'add_requirement'):
            return [DemoAwareAdminPermission()]
        return super().get_permissions()

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {
                    'error': "Cannot delete ProjectSlot because active or historical allocations refer to it. "
                             "Cancel or clear related allocations first."
                },
                status=status.HTTP_409_CONFLICT
            )

    @action(detail=True, methods=['post'], url_path='add-requirement')
    def add_requirement(self, request, pk=None):
        slot = self.get_object()
        skill_id = request.data.get('skill_id')
        min_proficiency = request.data.get('min_proficiency', 2)
        is_mandatory = request.data.get('is_mandatory', True)

        if not skill_id:
            return Response({'error': 'skill_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        req, created = SlotSkillRequirement.objects.update_or_create(
            project_slot=slot,
            skill_id=skill_id,
            defaults={
                'min_proficiency': min_proficiency,
                'is_mandatory': is_mandatory
            }
        )
        serializer = SlotSkillRequirementSerializer(req)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class AllocationViewSet(viewsets.ModelViewSet):
    queryset = Allocation.objects.all().select_related('developer', 'project_slot__project').prefetch_related('audit_logs').order_by('-created_at')
    serializer_class = AllocationSerializer

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy', 'cancel_allocation'):
            return [DemoAwareAdminPermission()]
        return super().get_permissions()

    def perform_create(self, serializer):
        allocation = serializer.save()
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        AllocationAuditLog.objects.create(
            allocation=allocation,
            action='created',
            performed_by=user,
            reason="Direct API allocation creation"
        )

    def destroy(self, request, *args, **kwargs):
        # AllocationAuditLog has on_delete=CASCADE against Allocation, so a raw
        # hard delete here would silently wipe that allocation's entire audit
        # trail along with it -- defeating the point of keeping one. The
        # `cancel` action below is the audited equivalent (soft state change,
        # history preserved) and is what the UI and API should use instead.
        return Response(
            {
                'error': "Direct deletion is disabled to protect the audit trail. "
                         "Use POST /api/allocations/{id}/cancel/ to revert an allocation instead."
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel_allocation(self, request, pk=None):
        with transaction.atomic():
            allocation = Allocation.objects.select_for_update().get(pk=pk)
            if allocation.status == 'cancelled':
                return Response({'message': 'Allocation is already cancelled'}, status=status.HTTP_200_OK)

            reason = request.data.get('reason', 'User initiated cancellation')
            allocation.status = 'cancelled'
            allocation.save()

            # Sync matching proposal status if any
            proposals = AllocationProposal.objects.filter(
                developer=allocation.developer,
                project_slot=allocation.project_slot,
                status='accepted'
            )
            for prop in proposals:
                prop.status = 'rejected'
                prop.notes = f"Allocation cancelled: {reason}"
                prop.save()

            user = request.user if request.user and request.user.is_authenticated else None
            AllocationAuditLog.objects.create(
                allocation=allocation,
                action='cancelled',
                performed_by=user,
                reason=reason
            )

            return Response({
                'message': 'Allocation successfully cancelled',
                'allocation': AllocationSerializer(allocation).data
            }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='bench-trend')
    def bench_trend(self, request):
        """
        Reconstructs bench % for each of the last `days` days from existing
        Allocation date ranges -- no snapshot table or migration needed. Capped
        at 180 days; this is O(days * confirmed_allocations) in Python, which
        is fine at demo/portfolio scale but would want a date-indexed query
        (or an actual daily snapshot table) at real workforce scale.
        """
        try:
            days = int(request.query_params.get('days', 30))
        except ValueError:
            days = 30
        days = max(1, min(days, 180))

        total_developers = Developer.objects.count()
        today = date.today()
        start_range = today - timedelta(days=days - 1)

        # Pull confirmed allocations once, not once per day.
        confirmed = list(
            Allocation.objects.filter(status='confirmed', start_date__lte=today, end_date__gte=start_range)
            .values('developer_id', 'start_date', 'end_date')
        )

        trend = []
        for offset in range(days):
            day = start_range + timedelta(days=offset)
            allocated_dev_ids = {
                a['developer_id'] for a in confirmed
                if a['start_date'] <= day <= a['end_date']
            }
            allocated_count = len(allocated_dev_ids)
            bench_count = max(0, total_developers - allocated_count)
            bench_pct = round((bench_count / total_developers) * 100, 1) if total_developers else 0.0
            trend.append({
                'date': day.isoformat(),
                'total_developers': total_developers,
                'allocated': allocated_count,
                'bench': bench_count,
                'bench_pct': bench_pct,
            })

        return Response({'days': days, 'trend': trend})


SOLVER_LOCK_KEY = 847392
_solver_lock = threading.Lock()


class SolverRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SolverRun.objects.all().prefetch_related('proposals__developer', 'proposals__project_slot__project').order_by('-timestamp')
    serializer_class = SolverRunSerializer

    def get_permissions(self):
        if self.action == 'run_solver':
            return [DemoAwareAdminPermission()]
        return super().get_permissions()

    @action(detail=False, methods=['post'], url_path='run')
    def run_solver(self, request):
        use_pg_lock = (connection.vendor == 'postgresql')
        got_lock = False

        if use_pg_lock:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", [SOLVER_LOCK_KEY])
                got_lock = bool(cursor.fetchone()[0])
        else:
            got_lock = _solver_lock.acquire(blocking=False)

        if not got_lock:
            return Response(
                {
                    'error': "A solver optimization run is currently in progress. "
                             "Please wait for the active run to complete."
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        try:
            objective = request.data.get('objective', 'balanced')
            raw_time_limit = request.data.get('time_limit', 10.0)
            try:
                time_limit = float(raw_time_limit)
            except (ValueError, TypeError):
                time_limit = 10.0

            # Server-side clamp max 60s
            time_limit = min(max(time_limit, 0.5), 60.0)
            run_comparison = request.data.get('run_comparison', True)

            result = run_optimization_engine(
                objective=objective,
                time_limit_seconds=time_limit,
                run_comparison=run_comparison
            )
            solver_run = SolverRun.objects.get(id=result['solver_run_id'])
            serializer = SolverRunSerializer(solver_run)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            if use_pg_lock:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(%s)", [SOLVER_LOCK_KEY])
            else:
                if got_lock:
                    try:
                        _solver_lock.release()
                    except RuntimeError:
                        pass



class AllocationProposalViewSet(viewsets.ModelViewSet):
    queryset = AllocationProposal.objects.all().select_related('developer', 'project_slot__project').order_by('-created_at')
    serializer_class = AllocationProposalSerializer

    def get_permissions(self):
        if self.action in ('accept_proposal', 'reject_proposal', 'bulk_accept', 'create', 'update', 'partial_update', 'destroy'):
            return [DemoAwareAdminPermission()]
        return super().get_permissions()

    @action(detail=True, methods=['post'], url_path='accept')
    def accept_proposal(self, request, pk=None):
        with transaction.atomic():
            try:
                proposal = AllocationProposal.objects.select_for_update().select_related('developer', 'project_slot').get(pk=pk)
            except AllocationProposal.DoesNotExist:
                return Response({'error': 'Proposal not found'}, status=status.HTTP_404_NOT_FOUND)

            if proposal.status == 'accepted':
                return Response({'message': 'Proposal already accepted'}, status=status.HTTP_200_OK)

            if proposal.status == 'expired':
                return Response({'error': 'Cannot accept an expired proposal from a prior solver run'}, status=status.HTTP_400_BAD_REQUEST)

            # Lock ProjectSlot and Developer rows atomically
            slot = ProjectSlot.objects.select_for_update().get(pk=proposal.project_slot_id)
            developer = Developer.objects.select_for_update().get(pk=proposal.developer_id)

            # Check headcount limit
            confirmed_count = Allocation.objects.filter(project_slot=slot, status='confirmed').count()
            if confirmed_count >= slot.headcount_needed:
                proposal.status = 'rejected'
                proposal.notes = f"Conflict: Slot reached max headcount limit ({slot.headcount_needed})."
                proposal.save()
                return Response({
                    'error': f"Project slot '{slot.role_title}' has already reached its headcount limit ({slot.headcount_needed}).",
                    'proposal': AllocationProposalSerializer(proposal).data
                }, status=status.HTTP_409_CONFLICT)

            # Create official Allocation record (triggers full_clean validation for capacity, leaves, skills)
            try:
                allocation = Allocation.objects.create(
                    developer=developer,
                    project_slot=slot,
                    start_date=slot.start_date,
                    end_date=slot.end_date,
                    allocated_hours=slot.weekly_hours_required,
                    status='confirmed'
                )
                user = request.user if request.user and request.user.is_authenticated else None
                AllocationAuditLog.objects.create(
                    allocation=allocation,
                    action='accepted',
                    performed_by=user,
                    reason=f"Accepted Proposal #{proposal.id}"
                )
            except ValidationError as ve:
                proposal.status = 'rejected'
                proposal.notes = f"Validation Error: {ve}"
                proposal.save()
                return Response({'error': str(ve)}, status=status.HTTP_409_CONFLICT)

            proposal.status = 'accepted'
            proposal.save()

            # Auto-invalidate any remaining pending proposals for this developer that overlap in date range
            other_proposals = AllocationProposal.objects.filter(
                developer=developer,
                status='proposed'
            ).exclude(pk=proposal.pk).select_related('project_slot')

            for other_prop in other_proposals:
                if check_date_overlap(
                    other_prop.project_slot.start_date, other_prop.project_slot.end_date,
                    slot.start_date, slot.end_date
                ):
                    other_prop.status = 'rejected'
                    other_prop.notes = f"Auto-rejected due to accepted allocation on slot {slot.id}"
                    other_prop.save()

            return Response({
                'proposal': AllocationProposalSerializer(proposal).data,
                'allocation': AllocationSerializer(allocation).data
            }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject_proposal(self, request, pk=None):
        proposal = self.get_object()
        proposal.status = 'rejected'
        proposal.save()
        return Response(AllocationProposalSerializer(proposal).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='bulk-accept')
    def bulk_accept(self, request):
        proposal_ids = request.data.get('proposal_ids', [])
        accepted_count = 0
        conflicts_count = 0

        with transaction.atomic():
            proposals = list(
                AllocationProposal.objects.filter(id__in=proposal_ids, status='proposed')
                .select_for_update()
                .select_related('developer', 'project_slot')
            )

            # Extract unique ProjectSlot and Developer IDs to acquire DB locks
            slot_ids = list({p.project_slot_id for p in proposals})
            dev_ids = list({p.developer_id for p in proposals})

            # Lock slots and developers
            list(ProjectSlot.objects.filter(id__in=slot_ids).select_for_update())
            list(Developer.objects.filter(id__in=dev_ids).select_for_update())

            for proposal in proposals:
                slot = proposal.project_slot
                developer = proposal.developer

                # Check slot headcount limit
                confirmed_count = Allocation.objects.filter(project_slot=slot, status='confirmed').count()
                if confirmed_count >= slot.headcount_needed:
                    proposal.status = 'rejected'
                    proposal.notes = f"Conflict: Slot reached headcount limit ({slot.headcount_needed}) during bulk accept."
                    proposal.save()
                    conflicts_count += 1
                    continue

                try:
                    allocation = Allocation.objects.create(
                        developer=developer,
                        project_slot=slot,
                        start_date=slot.start_date,
                        end_date=slot.end_date,
                        allocated_hours=slot.weekly_hours_required,
                        status='confirmed'
                    )
                    user = request.user if request.user and request.user.is_authenticated else None
                    AllocationAuditLog.objects.create(
                        allocation=allocation,
                        action='accepted',
                        performed_by=user,
                        reason=f"Bulk-accepted Proposal #{proposal.id}"
                    )
                    proposal.status = 'accepted'
                    proposal.save()
                    accepted_count += 1
                except ValidationError:
                    proposal.status = 'rejected'
                    proposal.notes = "Validation failed during bulk accept."
                    proposal.save()
                    conflicts_count += 1

        return Response({
            'message': f"Accepted {accepted_count} proposals. ({conflicts_count} conflicts auto-rejected)",
            'accepted_count': accepted_count,
            'conflicts_count': conflicts_count
        }, status=status.HTTP_200_OK)
