from django.db import transaction
from django.core.exceptions import ValidationError
from django.views.generic import TemplateView
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    Skill, Developer, DeveloperSkill, Project, ProjectSlot, 
    SlotSkillRequirement, Allocation, SolverRun, AllocationProposal
)
from .serializers import (
    SkillSerializer, DeveloperSerializer, DeveloperSkillSerializer,
    ProjectSerializer, ProjectSlotSerializer, SlotSkillRequirementSerializer,
    AllocationSerializer, SolverRunSerializer, AllocationProposalSerializer
)
from staffing.solver.runner import run_optimization_engine
from staffing.solver.eligibility import check_date_overlap


class DashboardView(TemplateView):
    template_name = 'index.html'


class SkillViewSet(viewsets.ModelViewSet):
    queryset = Skill.objects.all().order_by('category', 'name')
    serializer_class = SkillSerializer


class DeveloperViewSet(viewsets.ModelViewSet):
    queryset = Developer.objects.all().prefetch_related('developer_skills__skill').order_by('name')
    serializer_class = DeveloperSerializer

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


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().prefetch_related('slots__skill_requirements').order_by('-priority', 'name')
    serializer_class = ProjectSerializer


class ProjectSlotViewSet(viewsets.ModelViewSet):
    queryset = ProjectSlot.objects.all().select_related('project').prefetch_related('skill_requirements__skill').order_by('-priority')
    serializer_class = ProjectSlotSerializer

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
    queryset = Allocation.objects.all().select_related('developer', 'project_slot__project').order_by('-created_at')
    serializer_class = AllocationSerializer


class SolverRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SolverRun.objects.all().prefetch_related('proposals__developer', 'proposals__project_slot__project').order_by('-timestamp')
    serializer_class = SolverRunSerializer

    @action(detail=False, methods=['post'], url_path='run')
    def run_solver(self, request):
        objective = request.data.get('objective', 'balanced')
        time_limit = float(request.data.get('time_limit', 10.0))
        run_comparison = request.data.get('run_comparison', True)

        try:
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


class AllocationProposalViewSet(viewsets.ModelViewSet):
    queryset = AllocationProposal.objects.all().select_related('developer', 'project_slot__project').order_by('-created_at')
    serializer_class = AllocationProposalSerializer

    @action(detail=True, methods=['post'], url_path='accept')
    def accept_proposal(self, request, pk=None):
        with transaction.atomic():
            try:
                proposal = AllocationProposal.objects.select_for_update().select_related('developer', 'project_slot').get(pk=pk)
            except AllocationProposal.DoesNotExist:
                return Response({'error': 'Proposal not found'}, status=status.HTTP_404_NOT_FOUND)

            if proposal.status == 'accepted':
                return Response({'message': 'Proposal already accepted'}, status=status.HTTP_200_OK)

            # 1. Check for overlapping confirmed allocation for this developer
            existing_alloc = Allocation.objects.filter(
                developer=proposal.developer,
                status='confirmed',
                start_date__lte=proposal.project_slot.end_date,
                end_date__gte=proposal.project_slot.start_date
            ).first()

            if existing_alloc:
                proposal.status = 'rejected'
                proposal.notes = f"Conflict: Already allocated to {existing_alloc.project_slot}"
                proposal.save()
                return Response({
                    'error': f"Developer {proposal.developer.name} is already committed to an overlapping allocation ({existing_alloc.project_slot}).",
                    'proposal': AllocationProposalSerializer(proposal).data
                }, status=status.HTTP_409_CONFLICT)

            # 2. Create official Allocation record safely
            try:
                allocation = Allocation.objects.create(
                    developer=proposal.developer,
                    project_slot=proposal.project_slot,
                    start_date=proposal.project_slot.start_date,
                    end_date=proposal.project_slot.end_date,
                    allocated_hours=proposal.project_slot.weekly_hours_required,
                    status='confirmed'
                )
            except ValidationError as ve:
                proposal.status = 'rejected'
                proposal.notes = f"Validation Error: {ve}"
                proposal.save()
                return Response({'error': str(ve)}, status=status.HTTP_409_CONFLICT)

            proposal.status = 'accepted'
            proposal.save()

            # 3. Auto-invalidate any remaining pending proposals for this developer that overlap in date range
            other_proposals = AllocationProposal.objects.filter(
                developer=proposal.developer,
                status='proposed'
            ).exclude(pk=proposal.pk).select_related('project_slot')

            for other_prop in other_proposals:
                if check_date_overlap(
                    other_prop.project_slot.start_date, other_prop.project_slot.end_date,
                    proposal.project_slot.start_date, proposal.project_slot.end_date
                ):
                    other_prop.status = 'rejected'
                    other_prop.notes = f"Auto-rejected due to accepted allocation on slot {proposal.project_slot.id}"
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

            for proposal in proposals:
                # Check for existing confirmed allocation conflict
                existing_alloc = Allocation.objects.filter(
                    developer=proposal.developer,
                    status='confirmed',
                    start_date__lte=proposal.project_slot.end_date,
                    end_date__gte=proposal.project_slot.start_date
                ).exists()

                if existing_alloc:
                    proposal.status = 'rejected'
                    proposal.notes = "Conflict: Developer already allocated during bulk accept."
                    proposal.save()
                    conflicts_count += 1
                    continue

                try:
                    Allocation.objects.create(
                        developer=proposal.developer,
                        project_slot=proposal.project_slot,
                        start_date=proposal.project_slot.start_date,
                        end_date=proposal.project_slot.end_date,
                        allocated_hours=proposal.project_slot.weekly_hours_required,
                        status='confirmed'
                    )
                    proposal.status = 'accepted'
                    proposal.save()
                    accepted_count += 1
                except ValidationError:
                    proposal.status = 'rejected'
                    proposal.save()
                    conflicts_count += 1

        return Response({
            'message': f"Accepted {accepted_count} proposals. ({conflicts_count} conflicts auto-rejected)",
            'accepted_count': accepted_count,
            'conflicts_count': conflicts_count
        }, status=status.HTTP_200_OK)
