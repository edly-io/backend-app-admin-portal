"""Tests for the user directory list/search/filter (EDL-6).

Standalone (no student app) covers username/email search, is_active-based
status, pagination and the gate. Name search (UserProfile) and the disabled
status (UserStanding) engage only in-platform; the pure status mapping is
tested directly via ``derive_status``.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from admin_portal.directory import (
    STATUS_ACTIVE,
    STATUS_DISABLED,
    STATUS_PENDING,
    derive_status,
)

User = get_user_model()


class DeriveStatusUnitTests(APITestCase):
    def test_disabled_wins_over_active(self):
        self.assertEqual(derive_status(True, 'disabled'), STATUS_DISABLED)
        self.assertEqual(derive_status(False, 'disabled'), STATUS_DISABLED)

    def test_active_when_active_and_not_disabled(self):
        self.assertEqual(derive_status(True, None), STATUS_ACTIVE)
        self.assertEqual(derive_status(True, 'enabled'), STATUS_ACTIVE)

    def test_pending_when_inactive_and_not_disabled(self):
        self.assertEqual(derive_status(False, None), STATUS_PENDING)


class UserListGateTests(APITestCase):
    def test_anonymous_is_forbidden(self):
        response = self.client.get(reverse('admin_portal:v1:users'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class UserListTests(APITestCase):
    def setUp(self):
        self.url = reverse('admin_portal:v1:users')
        self.admin = User.objects.create_user('admin', email='admin@e.com', password='pw')
        self.admin.groups.add(Group.objects.get(name='edl_admin'))
        self.client.force_login(self.admin)
        # admin is active; add one more active and one pending (inactive) user.
        self.alice = User.objects.create_user('alice', email='alice@example.com', password='pw')
        self.bob = User.objects.create_user('bob', email='bob@sample.org', password='pw', is_active=False)

    def test_paginated_envelope(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for key in ('count', 'next', 'previous', 'results'):
            self.assertIn(key, response.data)
        self.assertEqual(response.data['count'], 3)  # admin + alice + bob

    def test_result_shape(self):
        response = self.client.get(self.url, {'search': 'alice'})
        row = response.data['results'][0]
        self.assertEqual(
            set(row.keys()),
            {'id', 'username', 'email', 'name', 'is_active', 'status', 'lms_role'},
        )
        self.assertEqual(row['username'], 'alice')
        self.assertEqual(row['status'], STATUS_ACTIVE)
        self.assertEqual(row['lms_role'], 'learner')

    def test_lms_role_reflects_platform_flags(self):
        staffer = User.objects.create_user('sam', email='sam@e.com', password='pw', is_staff=True)
        root = User.objects.create_user('root', email='root@e.com', password='pw', is_superuser=True)
        roles = {
            r['username']: r['lms_role']
            for r in self.client.get(self.url).data['results']
        }
        self.assertEqual(roles['alice'], 'learner')
        self.assertEqual(roles[staffer.username], 'staff')
        self.assertEqual(roles[root.username], 'admin')

    def test_search_by_username(self):
        response = self.client.get(self.url, {'search': 'ali'})
        usernames = [r['username'] for r in response.data['results']]
        self.assertEqual(usernames, ['alice'])

    def test_search_by_email_domain(self):
        response = self.client.get(self.url, {'search': 'sample.org'})
        usernames = [r['username'] for r in response.data['results']]
        self.assertEqual(usernames, ['bob'])

    def test_filter_status_active_excludes_pending(self):
        response = self.client.get(self.url, {'status': STATUS_ACTIVE})
        usernames = {r['username'] for r in response.data['results']}
        self.assertEqual(usernames, {'admin', 'alice'})

    def test_filter_status_pending_only(self):
        response = self.client.get(self.url, {'status': STATUS_PENDING})
        usernames = [r['username'] for r in response.data['results']]
        self.assertEqual(usernames, ['bob'])

    def test_invalid_status_is_400(self):
        response = self.client.get(self.url, {'status': 'bogus'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', response.data)

    def test_page_size_param(self):
        response = self.client.get(self.url, {'page_size': 2})
        self.assertEqual(len(response.data['results']), 2)
        self.assertIsNotNone(response.data['next'])
