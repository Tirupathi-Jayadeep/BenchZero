from datetime import datetime

def check_date_overlap(start1, end1, start2, end2):
    """Check if two date ranges [start1, end1] and [start2, end2] overlap."""
    if isinstance(start1, str):
        start1 = datetime.strptime(start1, "%Y-%m-%d").date()
    if isinstance(end1, str):
        end1 = datetime.strptime(end1, "%Y-%m-%d").date()
    if isinstance(start2, str):
        start2 = datetime.strptime(start2, "%Y-%m-%d").date()
    if isinstance(end2, str):
        end2 = datetime.strptime(end2, "%Y-%m-%d").date()
    return max(start1, start2) <= min(end1, end2)


def is_developer_eligible(developer, slot, existing_allocations=None, leaves=None):
    """
    Check if developer meets hard requirements for project slot:
    1. Must possess all mandatory required skills with proficiency >= min_proficiency.
    2. Must NOT have approved leave overlapping with slot date range.
    3. Must NOT exceed max_weekly_hours capacity with existing confirmed allocations.
    """
    # 1. Skill prerequisite filter
    # NOTE: Optional skill requirements (is_mandatory=False) are deliberately unenforced
    # during eligibility filtering. They do not disqualify candidates; instead, they
    # are weighted in fit_score.py to boost candidate ranking during optimization.
    dev_skill_map = {ds.skill_id: ds.proficiency_level for ds in developer.developer_skills.all()}
    for req in slot.skill_requirements.all():
        if req.is_mandatory:
            dev_level = dev_skill_map.get(req.skill_id, 0)
            if dev_level < req.min_proficiency:
                return False


    # 2. Leave availability filter
    if leaves is not None:
        dev_leaves = [l for l in leaves if l.developer_id == developer.id and getattr(l, 'is_approved', False)]
    elif hasattr(developer, 'leaves'):
        dev_leaves = list(developer.leaves.filter(is_approved=True))
    else:
        dev_leaves = []

    for l in dev_leaves:
        if check_date_overlap(l.start_date, l.end_date, slot.start_date, slot.end_date):
            return False

    # 3. Weekly hours capacity filter
    slot_hours = getattr(slot, 'weekly_hours_required', 40)
    dev_max_hours = getattr(developer, 'max_weekly_hours', 40)

    if slot_hours > dev_max_hours:
        return False

    if existing_allocations:
        dev_allocs = [
            a for a in existing_allocations 
            if a.developer_id == developer.id and getattr(a, 'status', 'confirmed') == 'confirmed'
        ]
        overlapping_allocs = [
            a for a in dev_allocs 
            if check_date_overlap(a.start_date, a.end_date, slot.start_date, slot.end_date)
        ]

        if overlapping_allocs:
            boundary_dates = set([slot.start_date, slot.end_date])
            for alloc in overlapping_allocs:
                if check_date_overlap(alloc.start_date, alloc.start_date, slot.start_date, slot.end_date):
                    boundary_dates.add(alloc.start_date)
                if check_date_overlap(alloc.end_date, alloc.end_date, slot.start_date, slot.end_date):
                    boundary_dates.add(alloc.end_date)

            for d in boundary_dates:
                committed_hours = sum(
                    getattr(a, 'allocated_hours', 40) for a in overlapping_allocs
                    if check_date_overlap(a.start_date, a.end_date, d, d)
                )
                if committed_hours + slot_hours > dev_max_hours:
                    return False

    return True
