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

    developer = models.ForeignKey(Developer, on_delete=models.CASCADE, related_name='allocations')
    project_slot = models.ForeignKey(ProjectSlot, on_delete=models.CASCADE, related_name='allocations')
    start_date = models.DateField()
    end_date = models.DateField()
    allocated_hours = models.IntegerField(default=40)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='confirmed')
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.status == 'confirmed':
            # Check for existing confirmed allocations for the same developer overlapping in date range
            qs = Allocation.objects.filter(
                developer=self.developer,
                status='confirmed',
                start_date__lte=self.end_date,
                end_date__gte=self.start_date
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            
            overlapping = qs.first()
            if overlapping:
                raise ValidationError({
                    'developer': f"Developer {self.developer.name} is already committed to an overlapping confirmed allocation ({overlapping.project_slot}) from {overlapping.start_date} to {overlapping.end_date}."
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Allocation: {self.developer.name} -> {self.project_slot} ({self.allocated_hours}h/wk)"



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
