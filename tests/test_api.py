from django.test import TestCase
from rest_framework.test import APIClient
from staffing.models import Developer, Skill, Project, ProjectSlot, SolverRun, AllocationProposal, Allocation

class TestStaffingAPI(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.skill, _ = Skill.objects.get_or_create(name="TestGo", defaults={'category': 'backend'})
        self.dev = Developer.objects.create(name="Dave Test", email="dave_test@test.com", hourly_cost=100)
        self.project = Project.objects.create(name="Cloud Platform Test", client="CloudCorp", priority=4)
        self.slot = ProjectSlot.objects.create(
            project=self.project,
            role_title="Backend Go Dev",
            start_date="2026-08-01",
            end_date="2026-09-01",
            priority=4,
            headcount_needed=1
        )

    def test_list_developers(self):
        res = self.client.get('/api/developers/')
        assert res.status_code == 200
        items = res.data['results'] if isinstance(res.data, dict) and 'results' in res.data else res.data
        assert len(items) >= 1

    def test_create_developer(self):
        res = self.client.post('/api/developers/', {
            'name': 'Eve Test',
            'email': 'eve_test@test.com',
            'title': 'Frontend Lead',
            'hourly_cost': 115,
            'max_weekly_hours': 40
        }, format='json')
        assert res.status_code == 201
        assert Developer.objects.filter(email='eve_test@test.com').exists()

    def test_run_solver_api(self):
        res = self.client.post('/api/solver-runs/run/', {
            'objective': 'balanced',
            'time_limit': 5.0,
            'run_comparison': True
        }, format='json')
        assert res.status_code == 200
        assert 'total_score' in res.data
        assert 'summary_metrics' in res.data

    def test_accept_proposal_creates_allocation(self):
        run = SolverRun.objects.create(objective_used='balanced', status='completed')
        proposal = AllocationProposal.objects.create(
            solver_run=run,
            developer=self.dev,
            project_slot=self.slot,
            fit_score=85.0,
            status='proposed'
        )

        res = self.client.post(f'/api/proposals/{proposal.id}/accept/')
        assert res.status_code == 200
        proposal.refresh_from_db()
        assert proposal.status == 'accepted'
        
        # Verify official Allocation record was created
        alloc_res = self.client.get('/api/allocations/')
        assert alloc_res.status_code == 200
        items = alloc_res.data['results'] if isinstance(alloc_res.data, dict) and 'results' in alloc_res.data else alloc_res.data
        assert len(items) >= 1

    def test_accept_proposal_conflict_returns_409(self):
        # Create an existing confirmed allocation for Dave
        Allocation.objects.create(
            developer=self.dev,
            project_slot=self.slot,
            start_date="2026-08-01",
            end_date="2026-09-01",
            allocated_hours=40,
            status='confirmed'
        )

        run = SolverRun.objects.create(objective_used='balanced', status='completed')
        proposal = AllocationProposal.objects.create(
            solver_run=run,
            developer=self.dev,
            project_slot=self.slot,
            fit_score=85.0,
            status='proposed'
        )

        res = self.client.post(f'/api/proposals/{proposal.id}/accept/')
        assert res.status_code == 409
        proposal.refresh_from_db()
        assert proposal.status == 'rejected'
