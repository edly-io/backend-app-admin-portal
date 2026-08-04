"""Serializers for the edl_panel v1 REST API."""
from rest_framework import serializers


class CreateUserSerializer(serializers.Serializer):
    """Input for creating a single learner/staff account."""

    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    name = serializers.CharField(max_length=255)
