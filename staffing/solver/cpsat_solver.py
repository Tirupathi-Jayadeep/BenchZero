import time
from ortools.sat.python import cp_model
from .eligibility import is_developer_eligible, check_date_overlap
from .fit_score import compute_fit_score

def solve_cpsat_staffing(developers, project_slots, objective='balanced', time_limit_seconds=10.0, existing_allocations=None):
    """
    Solves the staffing allocation problem using Google OR-Tools CP-SAT Constraint Solver.
    Guards against both internal slot overlaps AND previously confirmed database allocations.
    """
    model = cp_model.CpModel()
    assign = {}
    eligible_devs_by_slot = {s.id: [] for s in project_slots}
    eligible_slots_by_dev = {d.id: [] for d in developers}
    fit_scores = {}

    dev_dict = {d.id: d for d in developers}
    slot_dict = {s.id: s for s in project_slots}

    # 1. Decision Variables & Hard Skill + Existing Allocation Overlap Filters
    for d in developers:
        for s in project_slots:
            if is_developer_eligible(d, s, existing_allocations=existing_allocations):
                var = model.NewBoolVar(f"assign_d{d.id}_s{s.id}")
                assign[(d.id, s.id)] = var
                eligible_devs_by_slot[s.id].append(d.id)
                eligible_slots_by_dev[d.id].append(s.id)
                fit_scores[(d.id, s.id)] = compute_fit_score(d, s, objective)

    num_constraints = 0

    # 2. Overlap Constraint: A developer cannot be double-booked across overlapping slots
    slot_list = list(project_slots)
    for i in range(len(slot_list)):
        s1 = slot_list[i]
        for j in range(i + 1, len(slot_list)):
            s2 = slot_list[j]
            if check_date_overlap(s1.start_date, s1.end_date, s2.start_date, s2.end_date):
                for d in developers:
                    v1 = assign.get((d.id, s1.id))
                    v2 = assign.get((d.id, s2.id))
                    if v1 is not None and v2 is not None:
                        model.Add(v1 + v2 <= 1)
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
