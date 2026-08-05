"""Shared base classes for admin_portal REST views."""
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from admin_portal.auth import get_authentication_classes
from admin_portal.permissions import IsEdlAdmin


class AdminPortalAPIView(APIView):
    """Base API view: authenticated EDL admins only.

    Subclass this for every panel endpoint so the EDL-admin gate is applied
    consistently. Non-admins receive a 403.
    """

    authentication_classes = get_authentication_classes()
    permission_classes = (IsAuthenticated, IsEdlAdmin)

    def finalize_response(self, request, response, *args, **kwargs):
        """Mark every admin/PII response non-cacheable (e.g. the one-time
        password on create, learner emails on list). Prevents browsers/proxies
        from retaining sensitive data."""
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store'
        return response
