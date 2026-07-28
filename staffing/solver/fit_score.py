def compute_fit_score(developer, slot, objective='balanced'):
    """
    Computes a numerical fit score for an eligible developer-slot pairing.
    Higher score indicates better suitability for the objective.
    """
    dev_skill_map = {ds.skill_id: ds.proficiency_level for ds in developer.developer_skills.all()}
    reqs = list(slot.skill_requirements.all())
    
    if reqs:
        skill_scores = []
        for req in reqs:
            dev_lvl = dev_skill_map.get(req.skill_id, 0)
            if dev_lvl >= req.min_proficiency:
                # Base score 50 + 15 points per proficiency level above requirement
                score = 50.0 + (dev_lvl - req.min_proficiency) * 15.0
            else:
                score = 10.0
            skill_scores.append(score)
        base_skill_score = sum(skill_scores) / len(skill_scores)
    else:
        base_skill_score = 60.0

    # Project slot priority multiplier (Priority 1..5)
    priority_mult = 1.0 + (slot.priority - 1) * 0.25

    # Hourly cost factor (lower cost gives slightly higher factor for cost-focused objectives)
    hourly_cost = float(developer.hourly_cost) if developer.hourly_cost else 75.0
    cost_factor = max(0.4, 2.0 - (hourly_cost / 75.0))

    if objective == 'maximize_fit':
        total_score = base_skill_score * 1.5 * priority_mult
    elif objective == 'maximize_priority':
        total_score = base_skill_score * (slot.priority ** 1.6)
    elif objective == 'minimize_cost':
        total_score = base_skill_score * cost_factor * priority_mult
    elif objective == 'minimize_bench':
        # Add bench allocation bonus to encourage staffing available developers
        total_score = (base_skill_score + 40.0) * priority_mult
    else:  # balanced
        total_score = base_skill_score * priority_mult

    return round(max(1.0, total_score), 2)
