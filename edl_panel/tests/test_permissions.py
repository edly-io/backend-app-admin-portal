"""Tests for the EDL-admin access gate (EDL-2)."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class GateMixin:
    """Helpers to build users at each access level."""

    def make_user(self, username, admin=False, superuser=False):
        user = User.objects.create_user(username=username, email=f'{username}@e.com', password='pw')
        if superuser:
            user.is_superuser = True
            user.save()
        if admin:
            user.groups.add(Group.objects.get(name=settings.EDL_PANEL_ADMIN_GROUP))
        return user


class AdminGroupMigrationTests(APITestCase):
    """The data migration seeds the EDL-admin group."""

    def test_group_exists(self):
        self.assertTrue(Group.objects.filter(name=settings.EDL_PANEL_ADMIN_GROUP).exists())


class MeEndpointGateTests(GateMixin, APITestCase):
    """The gated REST endpoint enforces EDL-admin access."""

    def setUp(self):
        self.url = reverse('edl_panel:v1:me')

    def test_anonymous_is_forbidden(self):
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)

    def test_authenticated_non_admin_is_forbidden(self):
        self.client.force_login(self.make_user('bob'))
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_is_allowed(self):
        self.client.force_login(self.make_user('alice', admin=True))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'alice')
        self.assertTrue(response.data['is_edl_admin'])

    def test_superuser_bypass(self):
        self.client.force_login(self.make_user('root', superuser=True))
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)


class LandingPageGateTests(GateMixin, APITestCase):
    """The browser landing page enforces EDL-admin access."""

    def setUp(self):
        self.url = reverse('edl_panel:index')

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

    def test_authenticated_non_admin_is_forbidden(self):
        self.client.force_login(self.make_user('bob'))
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_is_allowed(self):
        self.client.force_login(self.make_user('alice', admin=True))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'EDL Panel')
