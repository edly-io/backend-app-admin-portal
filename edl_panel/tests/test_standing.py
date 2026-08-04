"""Tests for deactivate/reactivate (EDL-7).

The platform ``set_user_standing`` seam is patched; we assert it is called with
the right arguments and that the audit entry is written.
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from edl_panel import edxapp
from edl_panel.models import EdlAdminAuditLog

User = get_user_model()


class StandingGateTests(APITestCase):
    def test_anonymous_is_forbidden(self):
        url = reverse('edl_panel:v1:user-deactivate', args=['someone'])
        self.assertEqual(self.client.post(url).status_code, status.HTTP_403_FORBIDDEN)


class StandingTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', email='admin@e.com', password='pw')
        self.admin.groups.add(Group.objects.get(name='edl_admin'))
        self.client.force_login(self.admin)
        self.learner = User.objects.create_user('learner', email='l@e.com', password='pw')

        patcher = mock.patch.object(edxapp, 'set_user_standing')
        self.mock_standing = patcher.start()
        self.addCleanup(patcher.stop)

    def test_deactivate_calls_seam_and_audits(self):
        url = reverse('edl_panel:v1:user-deactivate', args=['learner'])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_disabled'])
        self.mock_standing.assert_called_once_with(self.learner, disabled=True, changed_by=self.admin)
        entry = EdlAdminAuditLog.objects.get()
        self.assertEqual(entry.action, EdlAdminAuditLog.Action.DEACTIVATE_USER)
        self.assertEqual(entry.target_user, self.learner)

    def test_reactivate_calls_seam_and_audits(self):
        url = reverse('edl_panel:v1:user-reactivate', args=['learner'])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_disabled'])
        self.mock_standing.assert_called_once_with(self.learner, disabled=False, changed_by=self.admin)
        self.assertEqual(EdlAdminAuditLog.objects.get().action, EdlAdminAuditLog.Action.REACTIVATE_USER)

    def test_unknown_user_is_404(self):
        url = reverse('edl_panel:v1:user-deactivate', args=['ghost'])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.mock_standing.assert_not_called()
        self.assertEqual(EdlAdminAuditLog.objects.count(), 0)
