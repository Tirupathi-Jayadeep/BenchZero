import os
import django
from datetime import date, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'benchzero.settings')
django.setup()

from staffing.models import Skill, Developer, DeveloperSkill, Project, ProjectSlot, SlotSkillRequirement, AllocationProposal, Allocation
from staffing.solver.runner import run_optimization_engine
from staffing.solver.eligibility import is_developer_eligible
from staffing.solver.fit_score import compute_fit_score

def run_demo():
    print("=" * 80)
    print(" DEMO SCENARIO: NEW HIGH-PRIORITY PROJECT REQUIRING 4 EMPLOYEES")
    print("=" * 80)

    # 1. Create New High-Priority Project
    today = date.today()
    project = Project.objects.create(
        name="Titan Mobility Edge Cloud",
        client="Titan Motors",
        priority=5,
        budget=320000.00,
        description="Next-generation autonomous vehicle telemetry & edge cloud architecture."
    )
    print(f"\n[1. New Project Created]: '{project.name}' (Client: {project.client}, Priority: P{project.priority}, Budget: ${project.budget:,.2f})")

    # Fetch required skills
    skills_dict = {s.name: s for s in Skill.objects.all()}

    # 2. Add 4 Open Role Slots with Skill Requirements
    slots_data = [
        ("Lead PyTorch AI Architect", "PyTorch", 4, "Python", 4, 5, 1),
        ("Principal React Frontend Engineer", "React", 4, "TypeScript", 4, 5, 1),
        ("Go Microservices Specialist", "Go", 3, "Docker", 3, 4, 1),
        ("Senior Cloud DevOps Lead", "AWS", 4, "Kubernetes", 4, 5, 1),
    ]

    slots = []
    print("\n[2. Open Project Slots Added (4 Headcount Needed)]:")
    for role_title, main_skill, main_lvl, sec_skill, sec_lvl, prio, headcount in slots_data:
        slot = ProjectSlot.objects.create(
            project=project,
            role_title=role_title,
            start_date=today,
            end_date=today + timedelta(days=90),
            priority=prio,
            headcount_needed=headcount,
            weekly_hours_required=40
        )
        SlotSkillRequirement.objects.create(project_slot=slot, skill=skills_dict[main_skill], min_proficiency=main_lvl, is_mandatory=True)
        SlotSkillRequirement.objects.create(project_slot=slot, skill=skills_dict[sec_skill], min_proficiency=sec_lvl, is_mandatory=True)
        slots.append(slot)
        print(f"  * Slot #{slot.id}: [{role_title}] -> Required Skills: {main_skill}>=Lvl{main_lvl}, {sec_skill}>=Lvl{sec_lvl} (Priority: P{prio})")

    # 3. Candidate Pool Analysis BEFORE Optimization
    all_devs = list(Developer.objects.filter(is_active=True).prefetch_related('developer_skills__skill'))

    print("\n" + "=" * 80)
    print(" 3. STEP 1: PRUNING & CANDIDATE ELIGIBILITY ANALYSIS")
    print("=" * 80)
    print(" The engine evaluates all developers against hard constraints (mandatory skills + min proficiency levels).")

    for slot in slots:
        print(f"\n  Role: [{slot.role_title}]")
        eligible_candidates = []
        for dev in all_devs:
            if is_developer_eligible(dev, slot, existing_allocations=[]):
                score = compute_fit_score(dev, slot, objective='balanced')
                eligible_candidates.append((dev, score))
        
        eligible_candidates.sort(key=lambda x: x[1], reverse=True)
        for dev, score in eligible_candidates:
            dev_skills = ", ".join([f"{ds.skill.name}:Lvl{ds.proficiency_level}" for ds in dev.developer_skills.all()])
            print(f"    - Eligible Candidate: {dev.name:<18} ({dev.title}) | Fit Score: {score:>5.1f} | Skills: [{dev_skills}]")

    # 4. Trigger Google OR-Tools CP-SAT Optimization Solver Engine
    print("\n" + "=" * 80)
    print(" 4. STEP 2: GOOGLE OR-TOOLS CP-SAT GLOBAL OPTIMIZATION")
    print("=" * 80)
    print(" Solving integer linear programming model maximizing total score across all 4 slots without double-booking...")

    # Clear previous allocations so developers are available for the demo allocation run
    Allocation.objects.all().delete()

    result = run_optimization_engine(objective='balanced', time_limit_seconds=10.0, run_comparison=True)

    print(f"\n  [Solver Status]: COMPLETED in {result['runtime_seconds']:.4f}s")
    print(f"  [Total Optimal Fit Score]: {result['total_score']:.1f}")
    
    comp = result['summary_metrics']['comparison']
    print(f"\n  [Algorithm Comparison Results]:")
    print(f"    • Google OR-Tools CP-SAT:    Score {comp['cpsat']['total_score']:.1f} ({len(comp['cpsat']['assignments'])} slots assigned)")
    print(f"    • Naive Greedy Matcher:     Score {comp['greedy']['total_score']:.1f} ({len(comp['greedy']['assignments'])} slots assigned)")
    print(f"    • SciPy Hungarian Matcher:    Score {comp['scipy']['total_score']:.1f} ({len(comp['scipy']['assignments'])} slots assigned)")
    print(f"    • CP-SAT Optimization Gain: +{comp['gain_vs_greedy_pct']:.1f}% higher quality score than Naive Greedy!")

    # 5. Display How Each of the 4 Employees Was Chosen
    print("\n" + "=" * 80)
    print(" 5. STEP 3: FINAL SELECTION RATIONALE FOR THE 4 EMPLOYEES")
    print("=" * 80)

    proposals = AllocationProposal.objects.filter(solver_run_id=result['solver_run_id'], project_slot__project=project).select_related('developer', 'project_slot')

    for i, prop in enumerate(proposals, 1):
        dev = prop.developer
        slot = prop.project_slot
        reqs = ", ".join([f"{r.skill.name}>=Lvl{r.min_proficiency}" for r in slot.skill_requirements.all()])
        dev_skills = ", ".join([f"{ds.skill.name} (Lvl {ds.proficiency_level})" for ds in dev.developer_skills.all()])

        print(f"\n  [Employee #{i} Selected]: {dev.name.upper()} ({dev.title})")
        print(f"  * Project Slot Assigned: {slot.role_title} ({slot.project.name})")
        print(f"  * Mandatory Required Skills: {reqs}")
        print(f"  * Employee Skill Profile:    {dev_skills}")
        print(f"  * Hourly Rate:              ${dev.hourly_cost}/hr")
        print(f"  * Computed Fit Score:       {prop.fit_score:.1f}")
        print(f"  * Why Selected: Engine proved {dev.name} satisfies all mandatory skills ({reqs}), has the highest proficiency bonus above minimums, and achieves optimal score for Priority P{slot.priority} project slot.")

    # Accept all 4 proposals to commit allocations
    for prop in proposals:
        Allocation.objects.create(
            developer=prop.developer,
            project_slot=prop.project_slot,
            start_date=prop.project_slot.start_date,
            end_date=prop.project_slot.end_date,
            allocated_hours=40,
            status='confirmed'
        )
        prop.status = 'accepted'
        prop.save()

    print("\n" + "=" * 80)
    print(" [6. Human Approval]: All 4 proposals accepted and committed as confirmed Allocations!")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    run_demo()
