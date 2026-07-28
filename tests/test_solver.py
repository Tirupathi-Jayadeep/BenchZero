import pytest
from django.test import TestCase
from django.core.exceptions import ValidationError
from datetime import date, timedelta
from staffing.models import (
    Skill, Developer, DeveloperSkill, Project, ProjectSlot, 
    SlotSkillRequirement, AllocationProposal, SolverRun, Allocation
)
from staffing.solver.eligibility import is_developer_eligible, check_date_overlap
from staffing.solver.fit_score import compute_fit_score
from staffing.solver.cpsat_solver import solve_cpsat_staffing
from staffing.solver.greedy_solver import solve_greedy_staffing
from staffing.solver.scipy_solver import solve_scipy_staffing
from staffing.solver.runner import run_optimization_engine


class TestOptimizationSolverEngine(TestCase):

    def setUp(self):
        self.py_skill, _ = Skill.objects.get_or_create(name="TestPython", defaults={'category': 'backend'})
        self.react_skill, _ = Skill.objects.get_or_create(name="TestReact", defaults={'category': 'frontend'})
        self.aws_skill, _ = Skill.objects.get_or_create(name="TestAWS", defaults={'category': 'devops'})

        # Developer 1: Expert Python & AWS
        self.dev1 = Developer.objects.create(name="Alice Test", email="alice_test@test.com", hourly_cost=120)
        DeveloperSkill.objects.create(developer=self.dev1, skill=self.py_skill, proficiency_level=5)
        DeveloperSkill.objects.create(developer=self.dev1, skill=self.aws_skill, proficiency_level=4)

        # Developer 2: Novice Python & Expert React
        self.dev2 = Developer.objects.create(name="Bob Test", email="bob_test@test.com", hourly_cost=90)
        DeveloperSkill.objects.create(developer=self.dev2, skill=self.py_skill, proficiency_level=2)
        DeveloperSkill.objects.create(developer=self.dev2, skill=self.react_skill, proficiency_level=5)

        # Project & Slot requiring Python >= Lvl 4
        self.project = Project.objects.create(name="Test Platform", client="Acme", priority=5)
        today = date.today()
        self.slot1 = ProjectSlot.objects.create(
            project=self.project,
            role_title="Senior Python Architect",
            start_date=today,
            end_date=today + timedelta(days=30),
            priority=5,
            headcount_needed=1
        )
        SlotSkillRequirement.objects.create(
            project_slot=self.slot1,
            skill=self.py_skill,
            min_proficiency=4,
            is_mandatory=True
        )

    def test_date_overlap_logic(self):
        today = date.today()
        d1_start, d1_end = today, today + timedelta(days=10)
        d2_start, d2_end = today + timedelta(days=5), today + timedelta(days=15)
        d3_start, d3_end = today + timedelta(days=11), today + timedelta(days=20)

        assert check_date_overlap(d1_start, d1_end, d2_start, d2_end) is True
        assert check_date_overlap(d1_start, d1_end, d3_start, d3_end) is False

    def test_eligibility_filter_enforces_mandatory_skills(self):
        # Alice has Python Lvl 5 (>= 4), so eligible
        assert is_developer_eligible(self.dev1, self.slot1) is True
        # Bob has Python Lvl 2 (< 4), so ineligible
        assert is_developer_eligible(self.dev2, self.slot1) is False

    def test_existing_confirmed_allocation_makes_dev_ineligible(self):
        today = date.today()
        # Create confirmed allocation for Alice on slot1 dates
        alloc = Allocation.objects.create(
            developer=self.dev1,
            project_slot=self.slot1,
            start_date=today,
            end_date=today + timedelta(days=30),
            allocated_hours=40,
            status='confirmed'
        )

        # Now check eligibility for slot1 with existing_allocations
        assert is_developer_eligible(self.dev1, self.slot1, existing_allocations=[alloc]) is False

    def test_allocation_model_clean_prevents_overlapping_confirmed_allocations(self):
        today = date.today()
        Allocation.objects.create(
            developer=self.dev1,
            project_slot=self.slot1,
            start_date=today,
            end_date=today + timedelta(days=30),
            allocated_hours=40,
            status='confirmed'
        )

        # Attempting to save a second overlapping allocation for Alice should raise ValidationError
        alloc2 = Allocation(
            developer=self.dev1,
            project_slot=self.slot1,
            start_date=today + timedelta(days=10),
            end_date=today + timedelta(days=20),
            allocated_hours=40,
            status='confirmed'
        )
        with pytest.raises(ValidationError):
            alloc2.save()

    def test_fit_score_calculation(self):
        score_alice = compute_fit_score(self.dev1, self.slot1, objective='balanced')
        score_bob = compute_fit_score(self.dev2, self.slot1, objective='balanced')

        # Alice has higher proficiency above minimum and priority 5 multiplier
        assert score_alice > score_bob

    def test_cpsat_solver_assigns_optimal_eligible_developer(self):
        devs = [self.dev1, self.dev2]
        slots = [self.slot1]

        result = solve_cpsat_staffing(devs, slots, objective='balanced')
        assert result['status'] in ('OPTIMAL', 'FEASIBLE')
        assert len(result['assignments']) == 1
        assert result['assignments'][0]['developer_id'] == self.dev1.id

    def test_cpsat_excludes_dev_with_existing_confirmed_allocation(self):
        today = date.today()
        alloc = Allocation.objects.create(
            developer=self.dev1,
            project_slot=self.slot1,
            start_date=today,
            end_date=today + timedelta(days=30),
            allocated_hours=40,
            status='confirmed'
        )

        devs = [self.dev1, self.dev2]
        slots = [self.slot1]

        result = solve_cpsat_staffing(devs, slots, objective='balanced', existing_allocations=[alloc])
        # Alice is excluded due to existing allocation, Bob is ineligible due to skill proficiency -> 0 assignments
        assert len(result['assignments']) == 0

    def test_cpsat_prevents_double_booking_on_overlapping_slots(self):
        today = date.today()
        slot2 = ProjectSlot.objects.create(
            project=self.project,
            role_title="AWS Infrastructure Lead",
            start_date=today + timedelta(days=5),
            end_date=today + timedelta(days=25),
            priority=4,
            headcount_needed=1
        )
        SlotSkillRequirement.objects.create(
            project_slot=slot2,
            skill=self.aws_skill,
            min_proficiency=3,
            is_mandatory=True
        )

        devs = [self.dev1, self.dev2]
        slots = [self.slot1, slot2]

        result = solve_cpsat_staffing(devs, slots, objective='balanced')
        dev1_assignments = [a for a in result['assignments'] if a['developer_id'] == self.dev1.id]
        assert len(dev1_assignments) <= 1

    def test_comparison_benchmarks_cpsat_vs_greedy(self):
        res = run_optimization_engine(objective='balanced', time_limit_seconds=5.0, run_comparison=True)
        assert res['status'] == 'completed'
        assert 'comparison' in res['summary_metrics']
        
        comp = res['summary_metrics']['comparison']
        assert 'cpsat' in comp
        assert 'greedy' in comp
        assert 'scipy' in comp
        assert comp['cpsat']['total_score'] >= comp['greedy']['total_score']
