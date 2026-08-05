from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

class Skill(models.Model):
    CATEGORY_CHOICES = [
        ('frontend', 'Frontend'),
        ('backend', 'Backend'),
        ('database', 'Database & Cloud'),
        ('ai_ml', 'AI / ML & Data'),
        ('devops', 'DevOps & Security'),
        ('mobile', 'Mobile Development'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='backend')
    description = models.TextField(blank=True, default='')

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class Developer(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    title = models.CharField(max_length=150, default='Senior Software Engineer')
    hourly_cost = models.DecimalField(max_digits=8, decimal_places=2, default=75.00)
    max_weekly_hours = models.IntegerField(default=40)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    skills = models.ManyToManyField(Skill, through='DeveloperSkill', related_name='developers')

    def __str__(self):
        return f"{self.name} - {self.title}"


class DeveloperSkill(models.Model):
    developer = models.ForeignKey(Developer, on_delete=models.CASCADE, related_name='developer_skills')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='developer_skills')
    proficiency_level = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        default=3,
        help_text="Proficiency scale from 1 (Novice) to 5 (Expert)"
    )

    class Meta:
        unique_together = ('developer', 'skill')

    def __str__(self):
        return f"{self.developer.name} - {self.skill.name} (Lvl {self.proficiency_level})"


class Project(models.Model):
    name = models.CharField(max_length=200)
    client = models.CharField(max_length=150)
    priority = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        default=3,
        help_text="Priority scale from 1 (Low) to 5 (Critical)"
    )
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=50000.00)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.client}) [P{self.priority}]"


class ProjectSlot(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='slots')
    role_title = models.CharField(max_length=150)
    start_date = models.DateField()
    end_date = models.DateField()
    priority = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        default=3
    )
    headcount_needed = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    weekly_hours_required = models.IntegerField(default=40)
    required_skills = models.ManyToManyField(Skill, through='SlotSkillRequirement', related_name='slots')

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(end_date__gte=models.F('start_date')), name='slot_end_after_start')
        ]

    def __str__(self):
        return f"{self.project.name} - {self.role_title} ({self.start_date} to {self.end_date})"


class SlotSkillRequirement(models.Model):
    project_slot = models.ForeignKey(ProjectSlot, on_delete=models.CASCADE, related_name='skill_requirements')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='slot_requirements')
    min_proficiency = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        default=2
    )
    is_mandatory = models.BooleanField(default=True)

    class Meta:
        unique_together = ('project_slot', 'skill')

    def __str__(self):
        return f"{self.project_slot.role_title} requires {self.skill.name} >= Lvl {self.min_proficiency}"


class Allocation(models.Model):
    STATUS_CHOICES = [
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    developer = models.ForeignKey(Developer, on_delete=models.PROTECT, related_name='allocations')
    project_slot = models.ForeignKey(ProjectSlot, on_delete=models.PROTECT, related_name='allocations')
    start_date = models.DateField()
    end_date = models.DateField()
    allocated_hours = models.IntegerField(default=40)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='confirmed')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(end_date__gte=models.F('start_date')), name='alloc_end_after_start')
        ]
        indexes = [
            models.Index(fields=['developer', 'status', 'start_date', 'end_date'], name='alloc_dev_stat_dates_idx'),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': f"end_date ({self.end_date}) cannot be before start_date ({self.start_date})."})

        if self.status == 'confirmed':
            # 1. Check headcount limit on project slot
            if self.project_slot_id:
                confirmed_allocs = Allocation.objects.filter(
                    project_slot=self.project_slot,
                    status='confirmed'
                )
                if self.pk:
                    confirmed_allocs = confirmed_allocs.exclude(pk=self.pk)
                if confirmed_allocs.count() >= self.project_slot.headcount_needed:
                    raise ValidationError({
                        'project_slot': f"Project slot '{self.project_slot.role_title}' already reached max headcount limit ({self.project_slot.headcount_needed})."
                    })

            # 2. Check skill prerequisites
            if self.developer_id and self.project_slot_id:
                dev_skills = {ds.skill_id: ds.proficiency_level for ds in self.developer.developer_skills.all()}
                for req in self.project_slot.skill_requirements.filter(is_mandatory=True):
                    dev_lvl = dev_skills.get(req.skill_id, 0)
                    if dev_lvl < req.min_proficiency:
                        raise ValidationError({
                            'developer': f"Developer {self.developer.name} does not meet mandatory skill requirement for {req.skill.name} (Requires Lvl {req.min_proficiency}, has Lvl {dev_lvl})."
                        })

            # 3. Check approved leave availability
            if self.developer_id and self.start_date and self.end_date:
                overlapping_leave = DeveloperLeave.objects.filter(
                    developer=self.developer,
                    is_approved=True,
                    start_date__lte=self.end_date,
                    end_date__gte=self.start_date
                ).first()
                if overlapping_leave:
                    raise ValidationError({
                        'developer': f"Developer {self.developer.name} is on approved leave from {overlapping_leave.start_date} to {overlapping_leave.end_date} ({overlapping_leave.reason})."
                    })

            # 4. Check weekly-hour capacity model
            if self.developer_id and self.start_date and self.end_date and self.allocated_hours:
                qs = Allocation.objects.filter(
                    developer=self.developer,
                    status='confirmed',
                    start_date__lte=self.end_date,
                    end_date__gte=self.start_date
                )
                if self.pk:
                    qs = qs.exclude(pk=self.pk)
                
                existing_allocs = list(qs)
                boundary_dates = set([self.start_date, self.end_date])
                for alloc in existing_allocs:
                    if self.start_date <= alloc.start_date <= self.end_date:
                        boundary_dates.add(alloc.start_date)
                    if self.start_date <= alloc.end_date <= self.end_date:
                        boundary_dates.add(alloc.end_date)
                
                max_dev_hours = self.developer.max_weekly_hours
                for d in boundary_dates:
                    day_hours = self.allocated_hours + sum(
                        a.allocated_hours for a in existing_allocs if a.start_date <= d <= a.end_date
                    )
                    if day_hours > max_dev_hours:
                        raise ValidationError({
                            'allocated_hours': f"Developer {self.developer.name} exceeds max weekly hours capacity ({day_hours}h/wk requested/committed vs max {max_dev_hours}h/wk)."
                        })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Allocation: {self.developer.name} -> {self.project_slot} ({self.allocated_hours}h/wk)"


class DeveloperLeave(models.Model):
    developer = models.ForeignKey(Developer, on_delete=models.CASCADE, related_name='leaves')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=200, default='Vacation')
    # Defaults to False: a leave request only blocks/unblocks a developer's
    # availability once someone with approval rights confirms it (see
    # DeveloperLeaveViewSet.approve / .revoke). Without this, anyone with
    # API access could self-approve a leave to free up a developer who is
    # actually unavailable, or vice versa.
    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_leaves'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(end_date__gte=models.F('start_date')), name='leave_end_after_start')
        ]

    def __str__(self):
        status_str = "Approved" if self.is_approved else "Pending"
        return f"{self.developer.name} Leave ({self.start_date} to {self.end_date}) [{status_str}]"


class AllocationAuditLog(models.Model):
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('accepted', 'Accepted Proposal'),
        ('cancelled', 'Cancelled'),
        ('reverted', 'Reverted'),
    ]

    allocation = models.ForeignKey(Allocation, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True, default='')

    def __str__(self):
        user_str = self.performed_by.username if self.performed_by else 'System'
        return f"AuditLog #{self.id}: Alloc #{self.allocation_id} {self.action} by {user_str} at {self.timestamp}"


class SolverRun(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    OBJECTIVE_CHOICES = [
        ('balanced', 'Balanced (Skill + Priority + Bench)'),
        ('maximize_fit', 'Maximize Skill Fit Quality'),
        ('maximize_priority', 'Prioritize High-Priority Projects'),
        ('minimize_bench', 'Minimize Bench Time'),
        ('minimize_cost', 'Minimize Hourly Cost'),
    ]

    timestamp = models.DateTimeField(auto_now_add=True)
    objective_used = models.CharField(max_length=50, choices=OBJECTIVE_CHOICES, default='balanced')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    total_score = models.FloatField(default=0.0)
    runtime_seconds = models.FloatField(default=0.0)
    input_snapshot = models.JSONField(default=dict, blank=True)
    summary_metrics = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"SolverRun #{self.id} ({self.objective_used}) - {self.status}"


class AllocationProposal(models.Model):
    STATUS_CHOICES = [
        ('proposed', 'Proposed'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ]

    ALGORITHM_CHOICES = [
        ('cpsat', 'Google OR-Tools CP-SAT Solver'),
        ('greedy', 'Naive Greedy Matcher'),
        ('scipy', 'SciPy Bipartite Matcher'),
    ]

    solver_run = models.ForeignKey(SolverRun, on_delete=models.CASCADE, related_name='proposals')
    developer = models.ForeignKey(Developer, on_delete=models.CASCADE, related_name='proposals')
    project_slot = models.ForeignKey(ProjectSlot, on_delete=models.CASCADE, related_name='proposals')
    fit_score = models.FloatField(default=0.0)
    solver_algorithm = models.CharField(max_length=20, choices=ALGORITHM_CHOICES, default='cpsat')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='proposed')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Proposal #{self.id}: {self.developer.name} -> {self.project_slot.role_title} (Score: {self.fit_score:.1f})"
