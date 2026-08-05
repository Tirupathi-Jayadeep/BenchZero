import time
from .eligibility import is_developer_eligible, check_date_overlap
from .fit_score import compute_fit_score

def solve_greedy_staffing(developers, project_slots, objective='balanced', existing_allocations=None, leaves=None):
    """
    Solves the staffing allocation problem using a Naive Greedy Assignment Algorithm.
    Iteratively picks the highest scoring eligible (developer, slot) pair without global optimization.
    Respects existing confirmed database allocations, leaves, and weekly hour limits.
    """
    start_time = time.time()
    
    dev_dict = {d.id: d for d in developers}
    slot_dict = {s.id: s for s in project_slots}

    costs = [float(d.hourly_cost) for d in developers if d.hourly_cost is not None]
    cost_stats = {'min': min(costs), 'max': max(costs)} if costs else None

    # 1. Collect all eligible candidate pairs with their fit scores
    candidate_pairs = []
    for d in developers:
        for s in project_slots:
            if is_developer_eligible(d, s, existing_allocations=existing_allocations, leaves=leaves):
                score = compute_fit_score(d, s, objective, cost_stats=cost_stats)
                candidate_pairs.append({
                    'developer_id': d.id,
                    'project_slot_id': s.id,
                    'score': score,
                    'start_date': s.start_date,
                    'end_date': s.end_date,
                    'weekly_hours': s.weekly_hours_required
                })

    # 2. Sort candidate pairs greedily by score descending
    candidate_pairs.sort(key=lambda x: x['score'], reverse=True)

    assigned_slots_count = {s.id: 0 for s in project_slots}
    # dev_assigned_allocs maps dev_id -> list of {'start_date': d, 'end_date': d, 'hours': h}
    dev_assigned_allocs = {d.id: [] for d in developers}

    # Pre-populate busy ranges from existing confirmed allocations
    if existing_allocations:
        for alloc in existing_allocations:
            if getattr(alloc, 'status', 'confirmed') == 'confirmed' and alloc.developer_id in dev_assigned_allocs:
                dev_assigned_allocs[alloc.developer_id].append({
                    'start_date': alloc.start_date,
                    'end_date': alloc.end_date,
                    'hours': getattr(alloc, 'allocated_hours', 40)
                })

    assignments = []
    total_score = 0.0

    # 3. Naively assign best available match first
    for candidate in candidate_pairs:
        d_id = candidate['developer_id']
        s_id = candidate['project_slot_id']
        slot = slot_dict[s_id]
        dev = dev_dict[d_id]

        # Check if slot needs more headcount
        if assigned_slots_count[s_id] >= slot.headcount_needed:
            continue

        # Check developer weekly hours capacity across overlapping ranges
        candidate_hours = candidate['weekly_hours']
        overlapping = [
            a for a in dev_assigned_allocs[d_id]
            if check_date_overlap(candidate['start_date'], candidate['end_date'], a['start_date'], a['end_date'])
        ]

        exceeds_capacity = False
        if overlapping:
            boundary_dates = set([candidate['start_date'], candidate['end_date']])
            for a in overlapping:
                boundary_dates.add(a['start_date'])
                boundary_dates.add(a['end_date'])
            for date_pt in boundary_dates:
                day_hours = candidate_hours + sum(
                    a['hours'] for a in overlapping
                    if check_date_overlap(a['start_date'], a['end_date'], date_pt, date_pt)
                )
                if day_hours > dev.max_weekly_hours:
                    exceeds_capacity = True
                    break

        if not exceeds_capacity:
            # Commit greedy assignment
            assigned_slots_count[s_id] += 1
            dev_assigned_allocs[d_id].append({
                'start_date': candidate['start_date'],
                'end_date': candidate['end_date'],
                'hours': candidate_hours
            })
            score = candidate['score']
            total_score += score
            assignments.append({
                'developer_id': d_id,
                'project_slot_id': s_id,
                'fit_score': score,
                'developer_name': dev.name,
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
