"""Shared base classes for edl_panel REST views."""
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from edl_panel.auth import get_authentication_classes
from edl_panel.permissions import IsEdlAdmin


class EdlPanelAPIView(APIView):
    """Base API view: authenticated EDL admins only.

    Subclass this for every panel endpoint so the EDL-admin gate is applied
    consistently. Non-admins receive a 403.
    """

    authentication_classes = get_authentication_classes()
    permission_classes = (IsAuthenticated, IsEdlAdmin)
