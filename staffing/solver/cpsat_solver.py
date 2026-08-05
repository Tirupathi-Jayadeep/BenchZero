import time
from ortools.sat.python import cp_model
from .eligibility import is_developer_eligible, check_date_overlap
from .fit_score import compute_fit_score

def solve_cpsat_staffing(developers, project_slots, objective='balanced', time_limit_seconds=10.0, existing_allocations=None, leaves=None):
    """
    Solves the staffing allocation problem using Google OR-Tools CP-SAT Constraint Solver.
    Enforces linear weekly-hour capacity constraints, headcount limits, leaves, and existing allocations.
    """
    # Server-side time limit capping (max 60 seconds)
    time_limit_seconds = min(max(float(time_limit_seconds), 0.5), 60.0)

    model = cp_model.CpModel()
    assign = {}
    eligible_devs_by_slot = {s.id: [] for s in project_slots}
    eligible_slots_by_dev = {d.id: [] for d in developers}
    fit_scores = {}

    dev_dict = {d.id: d for d in developers}
    slot_dict = {s.id: s for s in project_slots}

    # Dynamic cost statistics
    costs = [float(d.hourly_cost) for d in developers if d.hourly_cost is not None]
    cost_stats = {'min': min(costs), 'max': max(costs)} if costs else None

    # 1. Decision Variables & Hard Skill + Existing Allocation + Leave Filters
    for d in developers:
        for s in project_slots:
            if is_developer_eligible(d, s, existing_allocations=existing_allocations, leaves=leaves):
                var = model.NewBoolVar(f"assign_d{d.id}_s{s.id}")
                assign[(d.id, s.id)] = var
                eligible_devs_by_slot[s.id].append(d.id)
                eligible_slots_by_dev[d.id].append(s.id)
                fit_scores[(d.id, s.id)] = compute_fit_score(d, s, objective, cost_stats=cost_stats)

    num_constraints = 0

    # 2. Linear Weekly Hours Capacity Constraint per Developer across all timeline dates
    all_dates = set()
    for s in project_slots:
        all_dates.add(s.start_date)
        all_dates.add(s.end_date)

    if existing_allocations:
        for a in existing_allocations:
            all_dates.add(a.start_date)
            all_dates.add(a.end_date)

    for d in developers:
        dev_max_hours = getattr(d, 'max_weekly_hours', 40)
        
        # Existing confirmed allocation hours per date
        d_allocs = [a for a in (existing_allocations or []) if a.developer_id == d.id and getattr(a, 'status', 'confirmed') == 'confirmed']

        for date_pt in all_dates:
            # Find candidate slots active on this date_pt
            active_slots = [
                s for s in eligible_slots_by_dev[d.id]
                if check_date_overlap(slot_dict[s].start_date, slot_dict[s].end_date, date_pt, date_pt)
            ]
            if active_slots:
                committed_hours = sum(
                    getattr(a, 'allocated_hours', 40) for a in d_allocs
                    if check_date_overlap(a.start_date, a.end_date, date_pt, date_pt)
                )
                avail_hours = max(0, dev_max_hours - committed_hours)

                terms = [assign[(d.id, s_id)] * slot_dict[s_id].weekly_hours_required for s_id in active_slots]
                model.Add(sum(terms) <= avail_hours)
                num_constraints += 1

    # 3. Headcount Constraint: Each slot gets at most `headcount_needed` developers
    for s in project_slots:
        vars_for_slot = [assign[(d_id, s.id)] for d_id in eligible_devs_by_slot[s.id]]
        if vars_for_slot:
            model.Add(sum(vars_for_slot) <= s.headcount_needed)
            num_constraints += 1

    # 4. Objective Function Maximization
    objective_terms = []
    for (d_id, s_id), var in assign.items():
        score_scaled = int(round(fit_scores[(d_id, s_id)] * 100))
        objective_terms.append(score_scaled * var)

    if objective_terms:
        model.Maximize(sum(objective_terms))

    # 5. Execute Solver
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    start_time = time.time()
    status = solver.Solve(model)
    runtime = round(time.time() - start_time, 4)

    status_name = solver.StatusName(status)
    assignments = []
    total_score = 0.0

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for (d_id, s_id), var in assign.items():
            if solver.Value(var) == 1:
                score = fit_scores[(d_id, s_id)]
                assignments.append({
                    'developer_id': d_id,
                    'project_slot_id': s_id,
                    'fit_score': score,
                    'developer_name': dev_dict[d_id].name,
                    'role_title': slot_dict[s_id].role_title,
                    'project_name': slot_dict[s_id].project.name
                })
                total_score += score

    return {
        'algorithm': 'cpsat',
        'status': status_name,
        'assignments': assignments,
        'total_score': round(total_score, 2),
        'runtime_seconds': runtime,
        'num_variables': len(assign),
        'num_constraints': num_constraints,
        'total_eligible_pairs': len(assign)
    }
