"""v1 API views for the edl_panel plugin."""
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from edl_panel import __version__
from edl_panel.rest_api.base import EdlPanelAPIView


class HealthView(APIView):
    """
    Unauthenticated liveness probe.

    Confirms the plugin is installed and its URLs are mounted. Intentionally
    public (``AllowAny``); every other endpoint is gated by ``EdlPanelAPIView``.
    """

    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):  # noqa: D102
        return Response(
            {'status': 'ok', 'service': 'edl-panel', 'version': __version__},
            status=status.HTTP_200_OK,
        )


class MeView(EdlPanelAPIView):
    """
    Identity of the current EDL admin.

    First gated endpoint — reaching it at all proves the caller passed the
    EDL-admin gate. The MFE uses it to confirm access on load.
    """

    def get(self, request):  # noqa: D102
        user = request.user
        return Response(
            {
                'username': user.get_username(),
                'email': user.email,
                'is_edl_admin': True,
            },
            status=status.HTTP_200_OK,
        )
