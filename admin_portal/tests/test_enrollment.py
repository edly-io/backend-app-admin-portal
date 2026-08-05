"""Tests for enroll (EDL-8) and unenroll (EDL-9).

The platform enrollment helpers are patched at the ``edxapp`` seam; we assert
course/identifier validation, the passthrough of action/email/auto-enroll, and
the summary audit entry.
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from admin_portal import edxapp
from admin_portal.models import EdlAdminAuditLog

User = get_user_model()

BATCH_RESULT = {
    'action': 'enroll',
    'auto_enroll': False,
    'results': [{'identifier': 'a@e.com', 'success': True}],
    'successful_operations': 1,
    'failed_operations': 0,
    'total_students': 1,
}


class EnrollmentGateTests(APITestCase):
    def test_anonymous_is_forbidden(self):
        self.assertEqual(
            self.client.post(reverse('admin_portal:v1:enroll'), {}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )


class EnrollmentTests(APITestCase):
    COURSE = 'course-v1:Org+Course+Run'

    def setUp(self):
        self.admin = User.objects.create_user('admin', email='admin@e.com', password='pw')
        self.admin.groups.add(Group.objects.get(name='edl_admin'))
        self.client.force_login(self.admin)

        patch_key = mock.patch.object(edxapp, 'parse_course_key', side_effect=lambda c: c)
        patch_exists = mock.patch.object(edxapp, 'course_exists', return_value=True)
        patch_batch = mock.patch.object(edxapp, 'process_enrollment_batch', return_value=dict(BATCH_RESULT))
        self.mock_key = patch_key.start()
        self.mock_exists = patch_exists.start()
        self.mock_batch = patch_batch.start()
        for p in (patch_key, patch_exists, patch_batch):
            self.addCleanup(p.stop)

    def _payload(self, **over):
        payload = {'course_id': self.COURSE, 'identifiers': ['a@e.com', 'bob']}
        payload.update(over)
        return payload

    def test_enroll_passes_action_and_flags_and_audits(self):
        response = self.client.post(
            reverse('admin_portal:v1:enroll'),
            self._payload(email_students=True, auto_enroll=True),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        _, kwargs = self.mock_batch.call_args
        self.assertEqual(kwargs['action'], 'enroll')
        self.assertTrue(kwargs['email_students'])
        self.assertTrue(kwargs['auto_enroll'])
        self.assertEqual(kwargs['identifiers'], ['a@e.com', 'bob'])

        entry = EdlAdminAuditLog.objects.get()
        self.assertEqual(entry.action, EdlAdminAuditLog.Action.ENROLL)
        self.assertEqual(entry.course_id, self.COURSE)
        self.assertTrue(entry.detail['email_students'])

    def test_unenroll_passes_unenroll_action_and_audits(self):
        response = self.client.post(
            reverse('admin_portal:v1:unenroll'), self._payload(), format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        _, kwargs = self.mock_batch.call_args
        self.assertEqual(kwargs['action'], 'unenroll')
        self.assertEqual(EdlAdminAuditLog.objects.get().action, EdlAdminAuditLog.Action.UNENROLL)

    def test_email_toggle_defaults_off(self):
        self.client.post(reverse('admin_portal:v1:enroll'), self._payload(), format='json')
        _, kwargs = self.mock_batch.call_args
        self.assertFalse(kwargs['email_students'])

    def test_invalid_course_id_is_400(self):
        self.mock_key.side_effect = ValueError('bad key')
        response = self.client.post(reverse('admin_portal:v1:enroll'), self._payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('course_id', response.data)
        self.mock_batch.assert_not_called()

    def test_unknown_course_is_404(self):
        self.mock_exists.return_value = False
        response = self.client.post(reverse('admin_portal:v1:enroll'), self._payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.mock_batch.assert_not_called()

    def test_empty_identifiers_is_400(self):
        response = self.client.post(
            reverse('admin_portal:v1:enroll'),
            {'course_id': self.COURSE, 'identifiers': []},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('identifiers', response.data)
