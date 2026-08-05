"""
Permission classes for BenchZero.

BenchZero ships as a zero-config local demo (see README), so by default all
endpoints are open (AllowAny) to make it easy to run without setting up
accounts. That is not safe to expose beyond localhost.

These classes let an operator flip ONE setting -- REQUIRE_AUTH_FOR_WRITES --
to lock down every mutating endpoint (POST/PUT/PATCH/DELETE and the custom
accept/reject/cancel/approve actions) behind Django authentication, without
touching every view. Reads stay open either way so the dashboard keeps
working without a login.

To turn this on:
    export REQUIRE_AUTH_FOR_WRITES=True
and create at least one user (e.g. `python manage.py createsuperuser`) so
SessionAuthentication / BasicAuthentication have someone to authenticate as.
"""

from django.conf import settings
from rest_framework.permissions import SAFE_METHODS, BasePermission


class DemoAwarePermission(BasePermission):
    """Read access is always open. Write access requires login once
    REQUIRE_AUTH_FOR_WRITES=True."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        if not getattr(settings, "REQUIRE_AUTH_FOR_WRITES", False):
            return True
        return bool(request.user and request.user.is_authenticated)


class DemoAwareAdminPermission(BasePermission):
    """Like DemoAwarePermission, but for actions that should only ever be
    done by staff once auth is enforced (e.g. approving leave requests).
    Reads still stay open; the elevated check only applies to write
    methods/actions, and only once REQUIRE_AUTH_FOR_WRITES=True."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        if not getattr(settings, "REQUIRE_AUTH_FOR_WRITES", False):
            return True
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
