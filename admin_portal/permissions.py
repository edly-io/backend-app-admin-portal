"""Access control for the admin_portal plugin (EDL-2).

Everything the panel exposes — the browser landing page and every REST
endpoint — is restricted to members of the EDL-admin group. Non-admins get a
403; anonymous browser users are redirected to login. Superusers optionally
bypass the check (``ADMIN_PORTAL_SUPERUSER_BYPASS``).
"""
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden
from rest_framework.permissions import BasePermission

FORBIDDEN_MESSAGE = 'You do not have EDL admin access.'


def user_is_edl_admin(user):
    """Return True if ``user`` may access the EDL panel."""
    if not (user and user.is_authenticated):
        return False
    if getattr(settings, 'ADMIN_PORTAL_SUPERUSER_BYPASS', True) and user.is_superuser:
        return True
    group_name = getattr(settings, 'ADMIN_PORTAL_ADMIN_GROUP', 'edl_admin')
    return user.groups.filter(name=group_name).exists()


class IsEdlAdmin(BasePermission):
    """DRF permission: allow only EDL admins (used with ``IsAuthenticated``)."""

    message = FORBIDDEN_MESSAGE

    def has_permission(self, request, view):
        return user_is_edl_admin(request.user)


class EdlAdminRequiredMixin:
    """Gate a Django (non-DRF) view behind the EDL-admin check.

    Anonymous users are redirected to the login page; authenticated non-admins
    receive a 403.
    """

    def dispatch(self, request, *args, **kwargs):
        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated):
            return redirect_to_login(request.get_full_path())
        if not user_is_edl_admin(user):
            return HttpResponseForbidden(FORBIDDEN_MESSAGE)
        return super().dispatch(request, *args, **kwargs)
