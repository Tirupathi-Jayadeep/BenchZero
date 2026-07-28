from rest_framework import serializers
from .models import (
    Skill, Developer, DeveloperSkill, Project, ProjectSlot, 
    SlotSkillRequirement, Allocation, SolverRun, AllocationProposal
)

class SkillSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = Skill
        fields = ['id', 'name', 'category', 'category_display', 'description']


class DeveloperSkillSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source='skill.name', read_only=True)
    skill_category = serializers.CharField(source='skill.get_category_display', read_only=True)

    class Meta:
        model = DeveloperSkill
        fields = ['id', 'developer', 'skill', 'skill_name', 'skill_category', 'proficiency_level']


class DeveloperSerializer(serializers.ModelSerializer):
    developer_skills = DeveloperSkillSerializer(many=True, read_only=True)

    class Meta:
        model = Developer
        fields = [
            'id', 'name', 'email', 'title', 'hourly_cost', 
            'max_weekly_hours', 'is_active', 'created_at', 'developer_skills'
        ]


class SlotSkillRequirementSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source='skill.name', read_only=True)

    class Meta:
        model = SlotSkillRequirement
        fields = ['id', 'project_slot', 'skill', 'skill_name', 'min_proficiency', 'is_mandatory']


class ProjectSlotSerializer(serializers.ModelSerializer):
    skill_requirements = SlotSkillRequirementSerializer(many=True, read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = ProjectSlot
        fields = [
            'id', 'project', 'project_name', 'role_title', 'start_date', 'end_date',
            'priority', 'headcount_needed', 'weekly_hours_required', 'skill_requirements'
        ]


class ProjectSerializer(serializers.ModelSerializer):
    slots = ProjectSlotSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = ['id', 'name', 'client', 'priority', 'budget', 'description', 'created_at', 'slots']


class AllocationSerializer(serializers.ModelSerializer):
    developer_name = serializers.CharField(source='developer.name', read_only=True)
    role_title = serializers.CharField(source='project_slot.role_title', read_only=True)
    project_name = serializers.CharField(source='project_slot.project.name', read_only=True)

    class Meta:
        model = Allocation
        fields = [
            'id', 'developer', 'developer_name', 'project_slot', 'role_title',
            'project_name', 'start_date', 'end_date', 'allocated_hours', 'status', 'created_at'
        ]


class AllocationProposalSerializer(serializers.ModelSerializer):
    developer_name = serializers.CharField(source='developer.name', read_only=True)
    developer_title = serializers.CharField(source='developer.title', read_only=True)
    role_title = serializers.CharField(source='project_slot.role_title', read_only=True)
    project_name = serializers.CharField(source='project_slot.project.name', read_only=True)

    class Meta:
        model = AllocationProposal
        fields = [
            'id', 'solver_run', 'developer', 'developer_name', 'developer_title',
            'project_slot', 'role_title', 'project_name', 'fit_score',
            'solver_algorithm', 'status', 'notes', 'created_at'
        ]


class SolverRunSerializer(serializers.ModelSerializer):
    proposals = AllocationProposalSerializer(many=True, read_only=True)

    class Meta:
        model = SolverRun
        fields = [
            'id', 'timestamp', 'objective_used', 'status', 'total_score',
            'runtime_seconds', 'input_snapshot', 'summary_metrics', 'proposals'
        ]
