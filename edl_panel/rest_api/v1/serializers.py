"""Serializers for the edl_panel v1 REST API."""
from rest_framework import serializers

from edl_panel.directory import STATUS_CHOICES


class CreateUserSerializer(serializers.Serializer):
    """Input for creating a single learner/staff account."""

    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    name = serializers.CharField(max_length=255)


class UserListQuerySerializer(serializers.Serializer):
    """Query params for the user directory list."""

    search = serializers.CharField(required=False, allow_blank=True, default='')
    status = serializers.ChoiceField(choices=STATUS_CHOICES, required=False)
