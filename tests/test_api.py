from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from staffing.models import Developer, Skill, Project, ProjectSlot, SolverRun, AllocationProposal, Allocation

@override_settings(REQUIRE_AUTH_FOR_WRITES=False)
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

    def test_accept_proposal_headcount_limit_returns_409(self):
        dev2 = Developer.objects.create(name="Dev Two", email="dev2@test.com", hourly_cost=100)
        # Allocate dev1 to slot (headcount = 1)
        Allocation.objects.create(
            developer=self.dev,
            project_slot=self.slot,
            start_date="2026-08-01",
            end_date="2026-09-01",
            allocated_hours=40,
            status='confirmed'
        )

        run = SolverRun.objects.create(objective_used='balanced', status='completed')
        proposal2 = AllocationProposal.objects.create(
            solver_run=run,
            developer=dev2,
            project_slot=self.slot,
            fit_score=80.0,
            status='proposed'
        )

        res = self.client.post(f'/api/proposals/{proposal2.id}/accept/')
        assert res.status_code == 409
        proposal2.refresh_from_db()
        assert proposal2.status == 'rejected'
        assert "headcount limit" in proposal2.notes.lower()

    def test_cancel_allocation_endpoint_and_audit_log(self):
        alloc = Allocation.objects.create(
            developer=self.dev,
            project_slot=self.slot,
            start_date="2026-08-01",
            end_date="2026-09-01",
            allocated_hours=40,
            status='confirmed'
        )

        res = self.client.post(f'/api/allocations/{alloc.id}/cancel/', {'reason': 'Project postponed'}, format='json')
        assert res.status_code == 200
        alloc.refresh_from_db()
        assert alloc.status == 'cancelled'
        assert alloc.audit_logs.filter(action='cancelled').exists()

    def test_cannot_accept_expired_proposal(self):
        run = SolverRun.objects.create(objective_used='balanced', status='completed')
        proposal = AllocationProposal.objects.create(
            solver_run=run,
            developer=self.dev,
            project_slot=self.slot,
            fit_score=85.0,
            status='expired'
        )

        res = self.client.post(f'/api/proposals/{proposal.id}/accept/')
        assert res.status_code == 400

    def test_bulk_accept_enforces_headcount(self):
        dev2 = Developer.objects.create(name="Dev Two", email="dev2_bulk@test.com", hourly_cost=100)
        run = SolverRun.objects.create(objective_used='balanced', status='completed')
        p1 = AllocationProposal.objects.create(
            solver_run=run, developer=self.dev, project_slot=self.slot, fit_score=90.0, status='proposed'
        )
        p2 = AllocationProposal.objects.create(
            solver_run=run, developer=dev2, project_slot=self.slot, fit_score=80.0, status='proposed'
        )

        res = self.client.post('/api/proposals/bulk-accept/', {'proposal_ids': [p1.id, p2.id]}, format='json')
        assert res.status_code == 200
        assert res.data['accepted_count'] == 1
        assert res.data['conflicts_count'] == 1

    def test_direct_allocation_delete_is_blocked(self):
        """Raw DELETE would cascade-wipe the audit trail (AllocationAuditLog
        has on_delete=CASCADE). It must be blocked in favor of the audited
        `cancel` action, which soft-cancels and preserves history."""
        alloc = Allocation.objects.create(
            developer=self.dev,
            project_slot=self.slot,
            start_date="2026-08-01",
            end_date="2026-09-01",
            allocated_hours=40,
            status='confirmed'
        )
        audit_log_count_before = alloc.audit_logs.count()

        res = self.client.delete(f'/api/allocations/{alloc.id}/')
        assert res.status_code == 405

        alloc.refresh_from_db()
        assert alloc.audit_logs.count() == audit_log_count_before

    def test_bench_trend_reflects_known_allocation(self):
        from datetime import date, timedelta
        today = date.today()

        Allocation.objects.all().delete()

        # Developer is allocated for a 5-day window starting 3 days ago.
        Allocation.objects.create(
            developer=self.dev,
            project_slot=self.slot,
            start_date=today - timedelta(days=3),
            end_date=today + timedelta(days=1),
            allocated_hours=40,
            status='confirmed'
        )

        res = self.client.get('/api/allocations/bench-trend/?days=10')
        assert res.status_code == 200
        trend = res.data['trend']
        assert len(trend) == 10

        total_devs = Developer.objects.count()
        by_date = {row['date']: row for row in trend}

        # 5 days ago: before the allocation started -> everyone on bench.
        five_days_ago = (today - timedelta(days=5)).isoformat()
        assert by_date[five_days_ago]['allocated'] == 0
        assert by_date[five_days_ago]['bench'] == total_devs

        # Yesterday: inside the allocation window -> this dev counted as allocated.
        yesterday = (today - timedelta(days=1)).isoformat()
        assert by_date[yesterday]['allocated'] >= 1
        assert by_date[yesterday]['bench'] == total_devs - by_date[yesterday]['allocated']

    def test_bench_trend_days_param_is_capped(self):
        res = self.client.get('/api/allocations/bench-trend/?days=9999')
        assert res.status_code == 200
        assert len(res.data['trend']) == 180

    def test_delete_developer_with_allocation_returns_409(self):
        Allocation.objects.create(
            developer=self.dev,
            project_slot=self.slot,
            start_date="2026-08-01",
            end_date="2026-09-01",
            allocated_hours=40,
            status='confirmed'
        )
        res = self.client.delete(f'/api/developers/{self.dev.id}/')
        assert res.status_code == 409
        assert "cannot delete developer" in res.data['error'].lower()

    def test_delete_project_with_allocation_returns_409(self):
        Allocation.objects.create(
            developer=self.dev,
            project_slot=self.slot,
            start_date="2026-08-01",
            end_date="2026-09-01",
            allocated_hours=40,
            status='confirmed'
        )
        res = self.client.delete(f'/api/projects/{self.project.id}/')
        assert res.status_code == 409
        assert "cannot delete project" in res.data['error'].lower()

    def test_delete_project_slot_with_allocation_returns_409(self):
        Allocation.objects.create(
            developer=self.dev,
            project_slot=self.slot,
            start_date="2026-08-01",
            end_date="2026-09-01",
            allocated_hours=40,
            status='confirmed'
        )
        res = self.client.delete(f'/api/slots/{self.slot.id}/')
        assert res.status_code == 409
        assert "cannot delete projectslot" in res.data['error'].lower()


    def test_solver_concurrency_lock_returns_429(self):
        from staffing.views import _solver_lock
        locked = _solver_lock.acquire(blocking=False)
        try:
            res = self.client.post('/api/solver-runs/run/', {
                'objective': 'balanced',
                'time_limit': 1.0,
            }, format='json')
            assert res.status_code == 429
            assert "in progress" in res.data['error'].lower()
        finally:
            if locked:
                _solver_lock.release()

    def test_postgres_advisory_lock_called_and_released(self):
        from unittest.mock import patch, MagicMock
        from staffing.views import SOLVER_LOCK_KEY

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [True]

        mock_conn = MagicMock()
        mock_conn.vendor = 'postgresql'
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch('staffing.views.connection', mock_conn):
            res = self.client.post('/api/solver-runs/run/', {'objective': 'balanced', 'time_limit': 1.0}, format='json')
            assert res.status_code == 200

            # Verify pg_try_advisory_lock and pg_advisory_unlock SQL executed
            calls = [c[0][0] for c in mock_cursor.execute.call_args_list]
            assert any("pg_try_advisory_lock" in sql for sql in calls)
            assert any("pg_advisory_unlock" in sql for sql in calls)

    def test_solver_lock_releases_on_exception(self):
        from unittest.mock import patch
        from staffing.views import _solver_lock

        with patch('staffing.views.run_optimization_engine', side_effect=RuntimeError("Solver crash simulation")):
            res = self.client.post('/api/solver-runs/run/', {'objective': 'balanced', 'time_limit': 1.0}, format='json')
            assert res.status_code == 500

        # Verify lock was released despite exception and next call is not 429
        res2 = self.client.post('/api/solver-runs/run/', {'objective': 'balanced', 'time_limit': 1.0}, format='json')
        assert res2.status_code == 200


