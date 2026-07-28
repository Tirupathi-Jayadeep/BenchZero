import time
import numpy as np
from scipy.optimize import linear_sum_assignment
from .eligibility import is_developer_eligible, check_date_overlap
from .fit_score import compute_fit_score

def solve_scipy_staffing(developers, project_slots, objective='balanced', existing_allocations=None):
    """
    Solves staffing allocation using SciPy linear_sum_assignment (Hungarian Algorithm).
    Expands multi-headcount slots into individual 1:1 slot instances.
    Respects existing confirmed database allocations.
    """
    start_time = time.time()
    
    dev_dict = {d.id: d for d in developers}

    # Expand project slots into individual slot demand units
    expanded_slots = []
    for s in project_slots:
        for unit in range(s.headcount_needed):
            expanded_slots.append({
                'slot_id': s.id,
                'unit_index': unit,
                'slot_obj': s
            })

    num_devs = len(developers)
    num_slots = len(expanded_slots)

    if num_devs == 0 or num_slots == 0:
        return {
            'algorithm': 'scipy',
            'status': 'COMPLETED',
            'assignments': [],
            'total_score': 0.0,
            'runtime_seconds': round(time.time() - start_time, 4),
            'num_variables': 0,
            'num_constraints': 0,
            'total_eligible_pairs': 0
        }

    # Build cost matrix (SciPy minimizes cost, so cost = max_score - fit_score)
    MAX_PENALTY = 1e6
    cost_matrix = np.full((num_devs, num_slots), MAX_PENALTY)

    fit_scores_grid = {}

    for i, dev in enumerate(developers):
        for j, slot_item in enumerate(expanded_slots):
            s = slot_item['slot_obj']
            if is_developer_eligible(dev, s, existing_allocations=existing_allocations):
                score = compute_fit_score(dev, s, objective)
                cost_matrix[i, j] = 1000.0 - score  # invert score to cost
                fit_scores_grid[(dev.id, j)] = (score, s)

    row_ind, col_ind = linear_sum_assignment(cost_matrix)

    assignments = []
    total_score = 0.0
    dev_assigned_ranges = {d.id: [] for d in developers}

    # Pre-populate busy ranges from existing confirmed allocations
    if existing_allocations:
        for alloc in existing_allocations:
            if alloc.status == 'confirmed' and alloc.developer_id in dev_assigned_ranges:
                dev_assigned_ranges[alloc.developer_id].append((alloc.start_date, alloc.end_date))

    for r, c in zip(row_ind, col_ind):
        if cost_matrix[r, c] < MAX_PENALTY / 2:
            dev = developers[r]
            slot_item = expanded_slots[c]
            s = slot_item['slot_obj']
            
            # Post-check date overlap constraint for 1:1 Hungarian matching
            has_overlap = False
            for start_d, end_d in dev_assigned_ranges[dev.id]:
                if check_date_overlap(s.start_date, s.end_date, start_d, end_d):
                    has_overlap = True
                    break

            if not has_overlap:
                dev_assigned_ranges[dev.id].append((s.start_date, s.end_date))
                score, _ = fit_scores_grid[(dev.id, c)]
                total_score += score
                assignments.append({
                    'developer_id': dev.id,
                    'project_slot_id': s.id,
                    'fit_score': score,
                    'developer_name': dev.name,
                    'role_title': s.role_title,
                    'project_name': s.project.name
                })

    runtime = round(time.time() - start_time, 4)

    return {
        'algorithm': 'scipy',
        'status': 'COMPLETED',
        'assignments': assignments,
        'total_score': round(total_score, 2),
        'runtime_seconds': runtime,
        'num_variables': num_devs * num_slots,
        'num_constraints': num_devs + num_slots,
        'total_eligible_pairs': int(np.sum(cost_matrix < MAX_PENALTY / 2))
    }
