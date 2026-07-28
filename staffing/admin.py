from django.contrib import admin
from .models import (
    Skill, Developer, DeveloperSkill, Project, ProjectSlot,
    SlotSkillRequirement, Allocation, SolverRun, AllocationProposal
)

class DeveloperSkillInline(admin.TabularInline):
    model = DeveloperSkill
    extra = 1

class SlotSkillRequirementInline(admin.TabularInline):
    model = SlotSkillRequirement
    extra = 1

class ProjectSlotInline(admin.StackedInline):
    model = ProjectSlot
    extra = 1

class AllocationProposalInline(admin.TabularInline):
    model = AllocationProposal
    extra = 0
    readonly_fields = ('developer', 'project_slot', 'fit_score', 'solver_algorithm', 'status', 'notes')

@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'description')
    list_filter = ('category',)
    search_fields = ('name', 'description')

@admin.register(Developer)
class DeveloperAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'title', 'hourly_cost', 'max_weekly_hours', 'is_active', 'created_at')
    list_filter = ('is_active', 'title')
    search_fields = ('name', 'email', 'title')
    inlines = [DeveloperSkillInline]

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'client', 'priority', 'budget', 'created_at')
    list_filter = ('priority',)
    search_fields = ('name', 'client')
    inlines = [ProjectSlotInline]

@admin.register(ProjectSlot)
class ProjectSlotAdmin(admin.ModelAdmin):
    list_display = ('project', 'role_title', 'priority', 'headcount_needed', 'start_date', 'end_date')
    list_filter = ('priority', 'project')
    search_fields = ('role_title', 'project__name')
    inlines = [SlotSkillRequirementInline]

@admin.register(Allocation)
class AllocationAdmin(admin.ModelAdmin):
    list_display = ('developer', 'project_slot', 'start_date', 'end_date', 'allocated_hours', 'status', 'created_at')
    list_filter = ('status', 'start_date')
    search_fields = ('developer__name', 'project_slot__role_title', 'project_slot__project__name')

@admin.register(SolverRun)
class SolverRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'timestamp', 'objective_used', 'status', 'total_score', 'runtime_seconds')
    list_filter = ('status', 'objective_used')
    readonly_fields = ('timestamp', 'objective_used', 'status', 'total_score', 'runtime_seconds', 'input_snapshot', 'summary_metrics')
    inlines = [AllocationProposalInline]

@admin.register(AllocationProposal)
class AllocationProposalAdmin(admin.ModelAdmin):
    list_display = ('id', 'solver_run', 'developer', 'project_slot', 'fit_score', 'solver_algorithm', 'status', 'created_at')
    list_filter = ('status', 'solver_algorithm')
    search_fields = ('developer__name', 'project_slot__role_title')
