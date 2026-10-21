"""Tests for resending the set-password email (EDL-52).

The platform email seam is patched; we assert the call, the old password hash
being replaced (which invalidates earlier links) and the audit entry.
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from admin_portal import edxapp
from admin_portal.models import EdlAdminAuditLog
from admin_portal.settings import common

User = get_user_model()


class ResendInviteGateTests(APITestCase):
    def test_anonymous_is_forbidden(self):
        url = reverse('admin_portal:v1:user-resend-invite', args=['someone'])
        self.assertIn(self.client.post(url).status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_non_admin_is_forbidden(self):
        user = User.objects.create_user('plain', email='p@e.com', password='pw')
        self.client.force_login(user)
        url = reverse('admin_portal:v1:user-resend-invite', args=['plain'])
        self.assertEqual(self.client.post(url).status_code, status.HTTP_403_FORBIDDEN)


class ResendInviteTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', email='admin@e.com', password='pw')
        self.admin.groups.add(Group.objects.get(name='edl_admin'))
        self.client.force_login(self.admin)
        self.pending = User.objects.create_user('pending', email='p@e.com', password='pw', is_active=False)
        self.pending.set_unusable_password()
        self.pending.save()

        patcher = mock.patch.object(edxapp, 'send_set_password_email')
        self.mock_send = patcher.start()
        self.addCleanup(patcher.stop)

    def _url(self, username):
        return reverse('admin_portal:v1:user-resend-invite', args=[username])

    def test_resend_sends_email_rotates_password_and_audits(self):
        old_hash = self.pending.password
        response = self.client.post(self._url('pending'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'pending')
        self.mock_send.assert_called_once()
        self.assertEqual(self.mock_send.call_args.args[0], self.pending)
        self.pending.refresh_from_db()
        self.assertNotEqual(self.pending.password, old_hash)
        self.assertFalse(self.pending.has_usable_password())

        entry = EdlAdminAuditLog.objects.get()
        self.assertEqual(entry.action, EdlAdminAuditLog.Action.RESEND_INVITE)
        self.assertEqual(entry.target_user, self.pending)
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(response.data['invite_sent_at'], entry.created)

    def test_unknown_user_is_404(self):
        response = self.client.post(self._url('ghost'))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.mock_send.assert_not_called()
        self.assertEqual(EdlAdminAuditLog.objects.count(), 0)

    def test_active_user_is_400_and_untouched(self):
        active = User.objects.create_user('active', email='a@e.com', password='pw')
        old_hash = active.password
        response = self.client.post(self._url('active'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.mock_send.assert_not_called()
        active.refresh_from_db()
        self.assertEqual(active.password, old_hash)
        self.assertEqual(EdlAdminAuditLog.objects.count(), 0)

    def test_disabled_user_is_400(self):
        with mock.patch('admin_portal.accounts.get_standing_status', return_value='disabled'):
            response = self.client.post(self._url('pending'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.mock_send.assert_not_called()


class PasswordResetTimeoutTests(APITestCase):
    def test_plugin_settings_sets_seven_days(self):
        settings = mock.Mock()
        common.plugin_settings(settings)
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT, 7 * 24 * 60 * 60)
