"""v1 API views for the admin_portal plugin."""
from django.conf import settings
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_portal import __version__
from admin_portal.accounts import CreateUserError, create_learner
from admin_portal.audit import record_action
from admin_portal.directory import list_users, serialize_user
from admin_portal.enrollment import ACTION_ENROLL, ACTION_UNENROLL, EnrollmentError, update_enrollments
from admin_portal.models import EdlAdminAuditLog
from admin_portal.rest_api.base import AdminPortalAPIView
from admin_portal.rest_api.v1.serializers import (
    CreateUserSerializer,
    EnrollmentSerializer,
    RoleActionSerializer,
    UserListQuerySerializer,
)
from admin_portal.roles import ACTION_ALLOW, RoleActionError, change_course_role, role_catalog
from admin_portal.standing import UserNotFound, set_account_disabled


class UserListPagination(PageNumberPagination):
    """Page-number pagination for the user directory."""

    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100


class HealthView(APIView):
    """
    Unauthenticated liveness probe.

    Confirms the plugin is installed and its URLs are mounted. Intentionally
    public (``AllowAny``); every other endpoint is gated by ``AdminPortalAPIView``.
    """

    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):  # noqa: D102
        return Response(
            {'status': 'ok', 'service': 'admin-portal', 'version': __version__},
            status=status.HTTP_200_OK,
        )


class MeView(AdminPortalAPIView):
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


class UsersView(AdminPortalAPIView):
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

        password_mode = getattr(settings, 'ADMIN_PORTAL_PASSWORD_MODE', 'link')
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


class _SetStandingView(AdminPortalAPIView):
    """Base for deactivate/reactivate; subclasses set ``disabled`` + ``action``."""

    disabled = None
    action = None

    def post(self, request, username):  # noqa: D102
        try:
            user = set_account_disabled(actor=request.user, username=username, disabled=self.disabled)
        except UserNotFound:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        record_action(request.user, self.action, target_user=user)
        return Response(
            {'username': user.username, 'is_disabled': self.disabled},
            status=status.HTTP_200_OK,
        )


class DeactivateUserView(_SetStandingView):
    """Block login and course access while retaining enrollments/grades."""

    disabled = True
    action = EdlAdminAuditLog.Action.DEACTIVATE_USER


class ReactivateUserView(_SetStandingView):
    """Restore access for a previously deactivated account."""

    disabled = False
    action = EdlAdminAuditLog.Action.REACTIVATE_USER


class _EnrollmentActionView(AdminPortalAPIView):
    """Base for enroll/unenroll; subclasses set ``enroll_action`` + ``audit_action``."""

    enroll_action = None
    audit_action = None

    def post(self, request):  # noqa: D102
        serializer = EnrollmentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            result = update_enrollments(
                actor=request.user,
                request=request,
                course_id=data['course_id'],
                identifiers=data['identifiers'],
                action=self.enroll_action,
                email_students=data['email_students'],
                auto_enroll=data['auto_enroll'],
                reason=data.get('reason', ''),
            )
        except EnrollmentError as exc:
            return Response(exc.field_errors, status=exc.status_code)

        record_action(
            request.user,
            self.audit_action,
            course_id=data['course_id'],
            detail={
                'identifiers': result.get('total_students'),
                'successful': result.get('successful_operations'),
                'failed': result.get('failed_operations'),
                'email_students': data['email_students'],
                'auto_enroll': data['auto_enroll'],
            },
        )
        return Response(result, status=status.HTTP_200_OK)


class EnrollView(_EnrollmentActionView):
    """Enroll one or many learners into a published course run."""

    enroll_action = ACTION_ENROLL
    audit_action = EdlAdminAuditLog.Action.ENROLL


class UnenrollView(_EnrollmentActionView):
    """Unenroll one or many learners (soft; submission/grade data retained)."""

    enroll_action = ACTION_UNENROLL
    audit_action = EdlAdminAuditLog.Action.UNENROLL


class RolesView(AdminPortalAPIView):
    """
    Course-scoped role management (EDL-10).

    ``GET``  — the catalog of grantable roles with one-line descriptions.
    ``POST`` — grant or revoke a role for a user in a course. Global/site roles
    are not grantable; grants require an active user and auto-enroll the grantee.
    """

    def get(self, request):  # noqa: D102
        return Response({'roles': role_catalog()}, status=status.HTTP_200_OK)

    def post(self, request):  # noqa: D102
        serializer = RoleActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            user = change_course_role(
                actor=request.user,
                course_id=data['course_id'],
                identifier=data['identifier'],
                role=data['role'],
                action=data['action'],
            )
        except RoleActionError as exc:
            return Response(exc.field_errors, status=exc.status_code)

        is_grant = data['action'] == ACTION_ALLOW
        record_action(
            request.user,
            EdlAdminAuditLog.Action.ROLE_GRANT if is_grant else EdlAdminAuditLog.Action.ROLE_REVOKE,
            target_user=user,
            course_id=data['course_id'],
            detail={'role': data['role']},
        )
        return Response(
            {
                'username': user.username,
                'role': data['role'],
                'action': data['action'],
            },
            status=status.HTTP_200_OK,
        )
