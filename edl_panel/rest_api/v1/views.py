"""v1 API views for the edl_panel plugin."""
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from edl_panel import __version__


class HealthView(APIView):
    """
    Unauthenticated liveness probe.

    Confirms the plugin is installed and its URLs are mounted. Intentionally
    public (``AllowAny``); the EDL-admin permission gate that protects every
    real endpoint is introduced in EDL-2.
    """

    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):  # noqa: D102
        return Response(
            {'status': 'ok', 'service': 'edl-panel', 'version': __version__},
            status=status.HTTP_200_OK,
        )
