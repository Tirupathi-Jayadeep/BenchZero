import os
import django
from datetime import date, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'benchzero.settings')
django.setup()

from staffing.models import Skill, Developer, DeveloperSkill, Project, ProjectSlot, SlotSkillRequirement, AllocationProposal, Allocation
from staffing.solver.runner import run_optimization_engine

def run_6_dev_demo():
    print("=" * 80)
    print(" DEMO SCENARIO: LARGE PROJECT REQUIRING 6 DEVELOPERS")
    print("=" * 80)

    # Clear existing allocations to make all developers available for 6-slot staffing
    Allocation.objects.all().delete()
    AllocationProposal.objects.all().delete()

    today = date.today()
    project = Project.objects.create(
        name="Titan Autonomous Edge Platform",
        client="Titan Motors",
        priority=5,
        budget=550000.00,
        description="Comprehensive 6-developer engineering initiative."
    )
    print(f"\n[Project Created]: '{project.name}' (Priority: P5, 6 Roles Required)")

    skills_dict = {s.name: s for s in Skill.objects.all()}

    # Create 6 Project Slots
    slots_data = [
        ("Lead PyTorch AI Architect", "PyTorch", 4, "Python", 4, 5),
        ("Principal React Frontend Engineer", "React", 4, "TypeScript", 4, 5),
        ("Go Microservices Lead", "Go", 3, "Docker", 3, 5),
        ("Senior Cloud DevOps Lead", "AWS", 4, "Kubernetes", 4, 5),
        ("Data Pipeline Architect", "Python", 4, "PostgreSQL", 4, 4),
        ("Backend Node & API Engineer", "Node.js", 3, "PostgreSQL", 3, 4),
    ]

    for role_title, main_skill, main_lvl, sec_skill, sec_lvl, prio in slots_data:
        slot = ProjectSlot.objects.create(
            project=project,
            role_title=role_title,
            start_date=today,
            end_date=today + timedelta(days=90),
            priority=prio,
            headcount_needed=1,
            weekly_hours_required=40
        )
        SlotSkillRequirement.objects.create(project_slot=slot, skill=skills_dict[main_skill], min_proficiency=main_lvl, is_mandatory=True)
        SlotSkillRequirement.objects.create(project_slot=slot, skill=skills_dict[sec_skill], min_proficiency=sec_lvl, is_mandatory=True)
        print(f"  * Created Slot: [{role_title}] -> Requires {main_skill}>=Lvl{main_lvl}, {sec_skill}>=Lvl{sec_lvl}")

    # Trigger CP-SAT Solver
    print("\nExecuting CP-SAT Engine...")
    result = run_optimization_engine(objective='balanced', time_limit_seconds=10.0, run_comparison=True)

    print(f"\n[Solver Completed] Total Optimal Score: {result['total_score']:.1f}")

    # Auto-accept proposals for this project to commit allocations
    props = AllocationProposal.objects.filter(project_slot__project=project)
    for p in props:
        Allocation.objects.create(
            developer=p.developer,
            project_slot=p.project_slot,
            start_date=p.project_slot.start_date,
            end_date=p.project_slot.end_date,
            allocated_hours=40,
            status='confirmed'
        )
        p.status = 'accepted'
        p.save()

    print(f"\n[Success] All {props.count()} developer proposals accepted and committed into confirmed Allocations!")

if __name__ == '__main__':
    run_6_dev_demo()
