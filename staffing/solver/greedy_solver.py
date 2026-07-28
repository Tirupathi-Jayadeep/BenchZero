import time
from .eligibility import is_developer_eligible, check_date_overlap
from .fit_score import compute_fit_score

def solve_greedy_staffing(developers, project_slots, objective='balanced', existing_allocations=None):
    """
    Solves the staffing allocation problem using a Naive Greedy Assignment Algorithm.
    Iteratively picks the highest scoring eligible (developer, slot) pair without global optimization.
    Respects existing confirmed database allocations.
    """
    start_time = time.time()
    
    dev_dict = {d.id: d for d in developers}
    slot_dict = {s.id: s for s in project_slots}

    # 1. Collect all eligible candidate pairs with their fit scores
    candidate_pairs = []
    for d in developers:
        for s in project_slots:
            if is_developer_eligible(d, s, existing_allocations=existing_allocations):
                score = compute_fit_score(d, s, objective)
                candidate_pairs.append({
                    'developer_id': d.id,
                    'project_slot_id': s.id,
                    'score': score,
                    'start_date': s.start_date,
                    'end_date': s.end_date
                })

    # 2. Sort candidate pairs greedily by score descending
    candidate_pairs.sort(key=lambda x: x['score'], reverse=True)

    assigned_slots_count = {s.id: 0 for s in project_slots}
    dev_assigned_ranges = {d.id: [] for d in developers}

    # Pre-populate busy ranges from existing confirmed allocations
    if existing_allocations:
        for alloc in existing_allocations:
            if alloc.status == 'confirmed' and alloc.developer_id in dev_assigned_ranges:
                dev_assigned_ranges[alloc.developer_id].append((alloc.start_date, alloc.end_date))

    assignments = []
    total_score = 0.0

    # 3. Naively assign best available match first
    for candidate in candidate_pairs:
        d_id = candidate['developer_id']
        s_id = candidate['project_slot_id']
        slot = slot_dict[s_id]

        # Check if slot needs more headcount
        if assigned_slots_count[s_id] >= slot.headcount_needed:
            continue

        # Check if developer is already booked during an overlapping time window
        has_overlap = False
        for start_date, end_date in dev_assigned_ranges[d_id]:
            if check_date_overlap(candidate['start_date'], candidate['end_date'], start_date, end_date):
                has_overlap = True
                break

        if not has_overlap:
            # Commit greedy assignment
            assigned_slots_count[s_id] += 1
            dev_assigned_ranges[d_id].append((candidate['start_date'], candidate['end_date']))
            score = candidate['score']
            total_score += score
            assignments.append({
                'developer_id': d_id,
                'project_slot_id': s_id,
                'fit_score': score,
                'developer_name': dev_dict[d_id].name,
                'role_title': slot.role_title,
                'project_name': slot.project.name
            })

    runtime = round(time.time() - start_time, 4)

    return {
        'algorithm': 'greedy',
        'status': 'COMPLETED',
        'assignments': assignments,
        'total_score': round(total_score, 2),
        'runtime_seconds': runtime,
        'num_variables': len(candidate_pairs),
        'num_constraints': len(developers) + len(project_slots),
        'total_eligible_pairs': len(candidate_pairs)
    }
