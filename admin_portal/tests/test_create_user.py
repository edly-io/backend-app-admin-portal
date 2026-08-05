"""Tests for the create-user endpoint (EDL-5).

The platform seam (``admin_portal.edxapp``) is patched so the suite runs without
edx-platform. A fake ``do_create_account`` creates a real ``User`` row so we
can assert persistence, activation and password state.
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from admin_portal import edxapp
from admin_portal.models import EdlAdminAuditLog

User = get_user_model()

GENERATED_PW = 'GenPw123456!'


def _fake_account_creation_form(data):
    # In the real flow this is an AccountCreationForm; here the dict is enough
    # because the fake do_create_account reads the fields directly.
    return data


def _fake_do_create_account(form):
    """Create a real (inactive) user, mirroring do_create_account's contract."""
    user = User.objects.create(username=form['username'], email=form['email'], is_active=False)
    user.set_password(form['password'])
    user.save()

    registration = mock.Mock()

    def _activate():
        user.is_active = True
        user.save(update_fields=['is_active'])

    registration.activate.side_effect = _activate
    profile = mock.Mock()
    return user, profile, registration


class CreateUserGateTests(APITestCase):
    def test_anonymous_is_forbidden(self):
        response = self.client.post(reverse('admin_portal:v1:users'), {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CreateUserTests(APITestCase):
    def setUp(self):
        self.url = reverse('admin_portal:v1:users')
        self.admin = User.objects.create_user('admin', email='admin@e.com', password='pw')
        self.admin.groups.add(Group.objects.get(name='edl_admin'))
        self.client.force_login(self.admin)
        self.payload = {'username': 'learner1', 'email': 'learner1@e.com', 'name': 'Learner One'}

        patcher_form = mock.patch.object(edxapp, 'account_creation_form', side_effect=_fake_account_creation_form)
        patcher_create = mock.patch.object(edxapp, 'do_create_account', side_effect=_fake_do_create_account)
        patcher_pw = mock.patch.object(edxapp, 'generate_password', return_value=GENERATED_PW)
        patcher_email = mock.patch.object(edxapp, 'send_set_password_email')
        self.mock_form = patcher_form.start()
        self.mock_create = patcher_create.start()
        self.mock_pw = patcher_pw.start()
        self.mock_email = patcher_email.start()
        for p in (patcher_form, patcher_create, patcher_pw, patcher_email):
            self.addCleanup(p.stop)

    # --- link mode (default) ---
    def test_link_mode_creates_pending_user_and_sends_link(self):
        response = self.client.post(self.url, self.payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'pending')
        self.assertFalse(response.data['is_active'])
        self.assertNotIn('password', response.data)  # admin never sees it

        user = User.objects.get(username='learner1')
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.mock_email.assert_called_once()

    def test_link_mode_writes_audit_entry(self):
        self.client.post(self.url, self.payload, format='json')
        entry = EdlAdminAuditLog.objects.get()
        self.assertEqual(entry.action, EdlAdminAuditLog.Action.CREATE_USER)
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.target_user.username, 'learner1')
        self.assertEqual(entry.detail, {'password_mode': 'link'})

    # --- copy mode ---
    @override_settings(ADMIN_PORTAL_PASSWORD_MODE='copy')
    def test_copy_mode_activates_and_returns_password(self):
        response = self.client.post(self.url, self.payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'active')
        self.assertTrue(response.data['is_active'])
        self.assertEqual(response.data['password'], GENERATED_PW)

        user = User.objects.get(username='learner1')
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password(GENERATED_PW))
        self.mock_email.assert_not_called()

    # --- duplicates / atomicity ---
    def test_duplicate_username_returns_409_inline_no_partial_account(self):
        self.mock_create.side_effect = edxapp.AccountValidationError(
            'An account with this username already exists.',
            field='username', error_code='duplicate-username',
        )
        response = self.client.post(self.url, self.payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('username', response.data)
        self.assertFalse(User.objects.filter(username='learner1').exists())
        self.assertEqual(EdlAdminAuditLog.objects.count(), 0)

    def test_duplicate_email_returns_409(self):
        self.mock_create.side_effect = edxapp.AccountValidationError(
            'An account with this email already exists.',
            field='email', error_code='duplicate-email',
        )
        response = self.client.post(self.url, self.payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('email', response.data)

    # --- input validation ---
    def test_missing_email_is_400_inline(self):
        response = self.client.post(
            self.url, {'username': 'x', 'name': 'X'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)
        self.mock_create.assert_not_called()

    def test_malformed_email_is_400_inline(self):
        payload = dict(self.payload, email='not-an-email')
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)
