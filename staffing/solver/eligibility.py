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


def is_developer_eligible(developer, slot, existing_allocations=None):
    """
    Check if developer meets hard requirements for project slot:
    1. Must possess all mandatory required skills with proficiency >= min_proficiency.
    2. Must NOT have any confirmed allocations that overlap with slot date range.
    """
    dev_skill_map = {ds.skill_id: ds.proficiency_level for ds in developer.developer_skills.all()}
    
    # 1. Skill prerequisite filter
    for req in slot.skill_requirements.all():
        if req.is_mandatory:
            dev_level = dev_skill_map.get(req.skill_id, 0)
            if dev_level < req.min_proficiency:
                return False

    # 2. Existing confirmed allocation overlap filter
    if existing_allocations:
        dev_allocs = [a for a in existing_allocations if a.developer_id == developer.id and a.status == 'confirmed']
        for alloc in dev_allocs:
            if check_date_overlap(alloc.start_date, alloc.end_date, slot.start_date, slot.end_date):
                return False

    return True
