"""v1 API views for the edl_panel plugin."""
from django.conf import settings
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from edl_panel import __version__
from edl_panel.accounts import CreateUserError, create_learner
from edl_panel.audit import record_action
from edl_panel.directory import list_users, serialize_user
from edl_panel.models import EdlAdminAuditLog
from edl_panel.rest_api.base import EdlPanelAPIView
from edl_panel.rest_api.v1.serializers import CreateUserSerializer, UserListQuerySerializer


class UserListPagination(PageNumberPagination):
    """Page-number pagination for the user directory."""

    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100


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


class UsersView(EdlPanelAPIView):
    """
    User directory.

    ``GET``  — list/search/filter users (partial email/name/username search and
    pending/active/disabled status), paginated.
    ``POST`` — create a single learner/staff account (see below).
    """

    def get(self, request):  # noqa: D102
        query = UserListQuerySerializer(data=request.query_params)
        if not query.is_valid():
            return Response(query.errors, status=status.HTTP_400_BAD_REQUEST)

        queryset = list_users(
            search=query.validated_data.get('search', ''),
            status=query.validated_data.get('status'),
        )
        paginator = UserListPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([serialize_user(u) for u in page])

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
