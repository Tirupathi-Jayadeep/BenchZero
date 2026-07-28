from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DashboardView, SkillViewSet, DeveloperViewSet, ProjectViewSet,
    ProjectSlotViewSet, AllocationViewSet, SolverRunViewSet, AllocationProposalViewSet
)

router = DefaultRouter()
router.register(r'skills', SkillViewSet, basename='skill')
router.register(r'developers', DeveloperViewSet, basename='developer')
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'slots', ProjectSlotViewSet, basename='projectslot')
router.register(r'allocations', AllocationViewSet, basename='allocation')
router.register(r'solver-runs', SolverRunViewSet, basename='solverrun')
router.register(r'proposals', AllocationProposalViewSet, basename='proposal')

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('api/', include(router.urls)),
]
