"""Tests for the public health endpoint (EDL-1)."""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from edl_panel import __version__


class HealthViewTests(APITestCase):
    """The health endpoint is public and proves the API URLs are mounted."""

    def test_health_returns_ok(self):
        response = self.client.get(reverse('edl_panel:v1:health'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'ok')
        self.assertEqual(response.data['service'], 'edl-panel')
        self.assertEqual(response.data['version'], __version__)

    def test_health_url_under_api_v1(self):
        self.assertEqual(reverse('edl_panel:v1:health'), '/edl-panel/api/v1/health/')

    def test_health_is_public(self):
        response = self.client.get(reverse('edl_panel:v1:health'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
