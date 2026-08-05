from django.db import transaction
from staffing.models import Developer, ProjectSlot, SolverRun, AllocationProposal, Allocation, DeveloperLeave
from .cpsat_solver import solve_cpsat_staffing
from .greedy_solver import solve_greedy_staffing
from .scipy_solver import solve_scipy_staffing

def run_optimization_engine(objective='balanced', time_limit_seconds=10.0, run_comparison=True):
    """
    Executes the staffing optimization engine, generates SolverRun and AllocationProposal records,
    and returns comprehensive benchmark metrics comparing CP-SAT vs Greedy vs SciPy matching.
    Includes active confirmed database Allocations and Developer Leaves as hard constraints.
    Auto-expires proposals from prior SolverRuns upon completion.
    """
    # Server-side time limit capping (max 60s)
    time_limit_seconds = min(max(float(time_limit_seconds), 0.5), 60.0)

    developers = list(Developer.objects.filter(is_active=True).prefetch_related('developer_skills__skill'))
    project_slots = list(ProjectSlot.objects.select_related('project').prefetch_related('skill_requirements__skill'))
    existing_allocations = list(Allocation.objects.filter(status='confirmed').select_related('developer', 'project_slot'))
    leaves = list(DeveloperLeave.objects.filter(is_approved=True))

    # Build input snapshot for audit trail
    input_snapshot = {
        'total_developers': len(developers),
        'total_project_slots': len(project_slots),
        'total_existing_confirmed_allocations': len(existing_allocations),
        'total_approved_leaves': len(leaves),
        'objective': objective,
        'developers': [{'id': d.id, 'name': d.name, 'cost': float(d.hourly_cost)} for d in developers],
        'slots': [{'id': s.id, 'role': s.role_title, 'priority': s.priority, 'headcount': s.headcount_needed} for s in project_slots]
    }

    solver_run = SolverRun.objects.create(
        objective_used=objective,
        status='pending',
        input_snapshot=input_snapshot
    )

    try:
        # Run Google OR-Tools CP-SAT Solver with existing allocation & leave exclusion
        cpsat_result = solve_cpsat_staffing(
            developers, project_slots, 
            objective=objective, 
            time_limit_seconds=time_limit_seconds,
            existing_allocations=existing_allocations,
            leaves=leaves
        )

        comparison_results = {}
        if run_comparison:
            greedy_result = solve_greedy_staffing(
                developers, project_slots, 
                objective=objective,
                existing_allocations=existing_allocations,
                leaves=leaves
            )
            scipy_result = solve_scipy_staffing(
                developers, project_slots, 
                objective=objective,
                existing_allocations=existing_allocations,
                leaves=leaves
            )

            cpsat_score = cpsat_result['total_score']
            greedy_score = greedy_result['total_score']
            scipy_score = scipy_result['total_score']

            score_diff_vs_greedy = round(cpsat_score - greedy_score, 2)
            pct_gain_vs_greedy = round(((cpsat_score - greedy_score) / max(1.0, greedy_score)) * 100, 1)

            comparison_results = {
                'cpsat': cpsat_result,
                'greedy': greedy_result,
                'scipy': scipy_result,
                'gain_vs_greedy_pct': pct_gain_vs_greedy,
                'score_diff_vs_greedy': score_diff_vs_greedy
            }

        # Calculate high-priority slot fulfillment rate for CP-SAT
        high_prio_slots = [s for s in project_slots if s.priority >= 4]
        assigned_slot_ids = {a['project_slot_id'] for a in cpsat_result['assignments']}
        high_prio_fulfilled = sum(1 for s in high_prio_slots if s.id in assigned_slot_ids)
        high_prio_rate = round((high_prio_fulfilled / max(1, len(high_prio_slots))) * 100, 1)

        # Calculate bench count (developers without an assigned slot or existing allocation)
        assigned_dev_ids = {a['developer_id'] for a in cpsat_result['assignments']}
        confirmed_dev_ids = {a.developer_id for a in existing_allocations}
        active_working_devs = assigned_dev_ids.union(confirmed_dev_ids)
        bench_count = len(developers) - len(active_working_devs)

        summary_metrics = {
            'assigned_developers': len(assigned_dev_ids),
            'confirmed_existing_developers': len(confirmed_dev_ids),
            'bench_developers': max(0, bench_count),
            'total_slots': len(project_slots),
            'staffed_assignments': len(cpsat_result['assignments']),
            'high_priority_fulfillment_pct': high_prio_rate,
            'comparison': comparison_results
        }

        # Create AllocationProposal instances for CP-SAT algorithm and auto-expire prior proposals
        proposals = []
        with transaction.atomic():
            # Auto-expire any active proposed proposals from prior SolverRuns
            AllocationProposal.objects.filter(status='proposed').update(
                status='expired',
                notes=f"Superseded by SolverRun #{solver_run.id}"
            )

            for a in cpsat_result['assignments']:
                proposal = AllocationProposal.objects.create(
                    solver_run=solver_run,
                    developer_id=a['developer_id'],
                    project_slot_id=a['project_slot_id'],
                    fit_score=a['fit_score'],
                    solver_algorithm='cpsat',
                    status='proposed',
                    notes=f"Auto-generated by CP-SAT solver ({objective} objective)"
                )
                proposals.append(proposal)

            solver_run.total_score = cpsat_result['total_score']
            solver_run.runtime_seconds = cpsat_result['runtime_seconds']
            solver_run.status = 'completed'
            solver_run.summary_metrics = summary_metrics
            solver_run.save()

        return {
            'solver_run_id': solver_run.id,
            'status': 'completed',
            'total_score': solver_run.total_score,
            'runtime_seconds': solver_run.runtime_seconds,
            'proposals_count': len(proposals),
            'summary_metrics': summary_metrics
        }

    except Exception as e:
        solver_run.status = 'failed'
        solver_run.summary_metrics = {'error': str(e)}
        solver_run.save()
        raise e
