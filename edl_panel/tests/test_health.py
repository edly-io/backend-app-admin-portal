"""Tests for the edl_panel scaffold (EDL-1): landing page + health endpoint."""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from edl_panel import __version__


class PanelIndexTests(APITestCase):
    """The panel landing page is reachable at /edl-panel/."""

    def test_index_reachable(self):
        response = self.client.get(reverse('edl_panel:index'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'EDL Panel')

    def test_index_url_is_edl_panel_root(self):
        self.assertEqual(reverse('edl_panel:index'), '/edl-panel/')


class HealthViewTests(APITestCase):
    """The health endpoint proves the plugin's API URLs are mounted."""

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
