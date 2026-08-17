from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from staffing.models import Developer, DeveloperLeave, Project, ProjectSlot


class TestAuthToggle(TestCase):
    """REQUIRE_AUTH_FOR_WRITES=True (the new default) locks down mutating endpoints;
    =False allows unauthenticated writes for zero-config demo mode."""

    def setUp(self):
        self.client = APIClient()

    @override_settings(REQUIRE_AUTH_FOR_WRITES=False)
    def test_anonymous_write_allowed_in_demo_mode(self):
        res = self.client.post('/api/skills/', {'name': 'Anon Skill', 'category': 'backend'}, format='json')
        assert res.status_code == 201

    @override_settings(REQUIRE_AUTH_FOR_WRITES=True)
    def test_anonymous_write_blocked_by_default(self):
        res = self.client.post('/api/skills/', {'name': 'Blocked Skill Default', 'category': 'backend'}, format='json')
        assert res.status_code in (401, 403)

    def test_anonymous_read_always_allowed(self):
        res = self.client.get('/api/skills/')
        assert res.status_code == 200

    @override_settings(REQUIRE_AUTH_FOR_WRITES=True)
    def test_anonymous_write_blocked_when_auth_required(self):
        res = self.client.post('/api/skills/', {'name': 'Blocked Skill', 'category': 'backend'}, format='json')
        assert res.status_code in (401, 403)

    @override_settings(REQUIRE_AUTH_FOR_WRITES=True)
    def test_read_still_open_when_auth_required(self):
        res = self.client.get('/api/skills/')
        assert res.status_code == 200

    @override_settings(REQUIRE_AUTH_FOR_WRITES=True)
    def test_authenticated_write_allowed_when_auth_required(self):
        user = User.objects.create_user('writer', password='pw', is_staff=True)
        self.client.force_authenticate(user=user)
        res = self.client.post('/api/skills/', {'name': 'Authed Skill', 'category': 'backend'}, format='json')
        assert res.status_code == 201

    @override_settings(REQUIRE_AUTH_FOR_WRITES=True)
    def test_regular_user_blocked_from_solver_and_bulk_accept(self):
        regular = User.objects.create_user('regular_user', password='pw', is_staff=False)
        self.client.force_authenticate(user=regular)

        res_solver = self.client.post('/api/solver-runs/run/', {'time_limit': 1.0}, format='json')
        assert res_solver.status_code == 403

        res_bulk = self.client.post('/api/proposals/bulk-accept/', {'proposal_ids': []}, format='json')
        assert res_bulk.status_code == 403

    @override_settings(REQUIRE_AUTH_FOR_WRITES=True)
    def test_staff_user_allowed_on_solver_run(self):
        staff = User.objects.create_user('staff_pm', password='pw', is_staff=True)
        self.client.force_authenticate(user=staff)

        res_solver = self.client.post('/api/solver-runs/run/', {'time_limit': 1.0}, format='json')
        assert res_solver.status_code == 200



@override_settings(REQUIRE_AUTH_FOR_WRITES=False)
class TestLeaveApprovalWorkflow(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.dev = Developer.objects.create(name="Leave Test Dev", email="leave_test@test.com", hourly_cost=100)
        self.project = Project.objects.create(name="Leave Test Project", client="Acme", priority=3)
        self.slot = ProjectSlot.objects.create(
            project=self.project, role_title="Dev", start_date="2026-08-01",
            end_date="2026-09-01", priority=3, headcount_needed=1,
        )

    def test_new_leave_defaults_to_pending(self):
        res = self.client.post('/api/leaves/', {
            'developer': self.dev.id, 'start_date': '2026-08-05',
            'end_date': '2026-08-10', 'reason': 'Vacation',
        }, format='json')
        assert res.status_code == 201
        leave = DeveloperLeave.objects.get(id=res.data['id'])
        assert leave.is_approved is False

    def test_cannot_self_approve_via_direct_write(self):
        """is_approved must be read-only on create/update; only the
        approve/revoke actions may change it."""
        res = self.client.post('/api/leaves/', {
            'developer': self.dev.id, 'start_date': '2026-08-05',
            'end_date': '2026-08-10', 'reason': 'Vacation', 'is_approved': True,
        }, format='json')
        assert res.status_code == 201
        leave = DeveloperLeave.objects.get(id=res.data['id'])
        assert leave.is_approved is False

    def test_pending_leave_does_not_block_availability(self):
        DeveloperLeave.objects.create(
            developer=self.dev, start_date='2026-08-01', end_date='2026-09-01',
            reason='Vacation', is_approved=False,
        )
        from staffing.models import Allocation
        alloc = Allocation(
            developer=self.dev, project_slot=self.slot, allocated_hours=40,
            start_date='2026-08-01', end_date='2026-09-01', status='confirmed',
        )
        alloc.clean()  # should not raise -- leave is only pending

    def test_approve_action_blocks_availability(self):
        leave = DeveloperLeave.objects.create(
            developer=self.dev, start_date='2026-08-01', end_date='2026-09-01',
            reason='Vacation', is_approved=False,
        )
        res = self.client.post(f'/api/leaves/{leave.id}/approve/')
        assert res.status_code == 200
        leave.refresh_from_db()
        assert leave.is_approved is True

        from django.core.exceptions import ValidationError
        from staffing.models import Allocation
        alloc = Allocation(
            developer=self.dev, project_slot=self.slot, allocated_hours=40,
            start_date='2026-08-01', end_date='2026-09-01', status='confirmed',
        )
        with self.assertRaises(ValidationError):
            alloc.clean()

    def test_revoke_action_unblocks_availability(self):
        leave = DeveloperLeave.objects.create(
            developer=self.dev, start_date='2026-08-01', end_date='2026-09-01',
            reason='Vacation', is_approved=True,
        )
        res = self.client.post(f'/api/leaves/{leave.id}/revoke/')
        assert res.status_code == 200
        leave.refresh_from_db()
        assert leave.is_approved is False

    @override_settings(REQUIRE_AUTH_FOR_WRITES=True)
    def test_approve_requires_staff_when_auth_required(self):
        leave = DeveloperLeave.objects.create(
            developer=self.dev, start_date='2026-08-01', end_date='2026-09-01',
            reason='Vacation', is_approved=False,
        )
        User.objects.filter(username__in=['regular', 'staff']).delete()
        regular_user = User.objects.create_user('regular', password='pw')
        self.client.force_authenticate(user=regular_user)
        res = self.client.post(f'/api/leaves/{leave.id}/approve/')
        assert res.status_code == 403

        staff_user = User.objects.create_user('staff', password='pw', is_staff=True)
        self.client.force_authenticate(user=staff_user)
        res = self.client.post(f'/api/leaves/{leave.id}/approve/')
        assert res.status_code == 200
        User.objects.filter(username__in=['regular', 'staff']).delete()
