"""Serializers for the edl_panel v1 REST API."""
from rest_framework import serializers

from edl_panel.directory import STATUS_CHOICES
from edl_panel.roles import ACTION_ALLOW, ACTION_REVOKE, GRANTABLE_ROLES


class CreateUserSerializer(serializers.Serializer):
    """Input for creating a single learner/staff account."""

    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    name = serializers.CharField(max_length=255)


class UserListQuerySerializer(serializers.Serializer):
    """Query params for the user directory list."""

    search = serializers.CharField(required=False, allow_blank=True, default='')
    status = serializers.ChoiceField(choices=STATUS_CHOICES, required=False)


class EnrollmentSerializer(serializers.Serializer):
    """Input for enroll/unenroll of one or many identifiers into a course run."""

    course_id = serializers.CharField()
    identifiers = serializers.ListField(
        child=serializers.CharField(), allow_empty=False,
        help_text='Emails or usernames.',
    )
    email_students = serializers.BooleanField(default=False)
    auto_enroll = serializers.BooleanField(default=False)
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class RoleActionSerializer(serializers.Serializer):
    """Input for granting/revoking a course-scoped role."""

    course_id = serializers.CharField()
    identifier = serializers.CharField(help_text='Email or username.')
    role = serializers.ChoiceField(choices=list(GRANTABLE_ROLES))
    action = serializers.ChoiceField(choices=[ACTION_ALLOW, ACTION_REVOKE])
