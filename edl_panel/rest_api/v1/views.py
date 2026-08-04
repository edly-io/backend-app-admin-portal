"""v1 API views for the edl_panel plugin."""
from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from edl_panel import __version__
from edl_panel.accounts import CreateUserError, create_learner
from edl_panel.audit import record_action
from edl_panel.models import EdlAdminAuditLog
from edl_panel.rest_api.base import EdlPanelAPIView
from edl_panel.rest_api.v1.serializers import CreateUserSerializer


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


class CreateUserView(EdlPanelAPIView):
    """
    Create a single learner/staff account.

    Reuses the platform's ``do_create_account``; provisions the password per
    ``EDL_PANEL_PASSWORD_MODE`` (``link`` default, ``copy`` optional).
    Duplicate email/username are returned as inline field errors (409) with no
    partial account created.
    """

    def post(self, request):  # noqa: D102
        serializer = CreateUserSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        password_mode = getattr(settings, 'EDL_PANEL_PASSWORD_MODE', 'link')
        try:
            user, password = create_learner(
                actor=request.user,
                request=request,
                password_mode=password_mode,
                **serializer.validated_data,
            )
        except CreateUserError as exc:
            return Response(exc.field_errors, status=exc.status_code)

        record_action(
            request.user,
            EdlAdminAuditLog.Action.CREATE_USER,
            target_user=user,
            detail={'password_mode': password_mode},
        )

        body = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_active': user.is_active,
            'status': 'active' if user.is_active else 'pending',
        }
        if password:
            body['password'] = password
        return Response(body, status=status.HTTP_201_CREATED)
