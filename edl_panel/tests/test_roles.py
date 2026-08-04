"""Tests for course-scoped role management (EDL-10).

The platform access/enrollment calls are patched at the ``edxapp`` seam. These
cover the allow-list, the is_active guard, auto-enroll on grant, and audit.
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


class RolesGateTests(APITestCase):
    def test_anonymous_get_is_forbidden(self):
        self.assertEqual(self.client.get(reverse('edl_panel:v1:roles')).status_code,
                         status.HTTP_403_FORBIDDEN)

    def test_anonymous_post_is_forbidden(self):
        self.assertEqual(self.client.post(reverse('edl_panel:v1:roles'), {}, format='json').status_code,
                         status.HTTP_403_FORBIDDEN)


class RoleCatalogTests(APITestCase):
    def setUp(self):
        admin = User.objects.create_user('admin', email='admin@e.com', password='pw')
        admin.groups.add(Group.objects.get(name='edl_admin'))
        self.client.force_login(admin)

    def test_catalog_lists_only_course_roles(self):
        response = self.client.get(reverse('edl_panel:v1:roles'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        roles = {r['role'] for r in response.data['roles']}
        self.assertEqual(roles, {'instructor', 'staff', 'limited_staff'})
        # No global/site roles are ever offered.
        self.assertNotIn('global_staff', roles)
        for entry in response.data['roles']:
            self.assertTrue(entry['description'])


class RoleActionTests(APITestCase):
    COURSE = 'course-v1:Org+Course+Run'

    def setUp(self):
        self.url = reverse('edl_panel:v1:roles')
        self.admin = User.objects.create_user('admin', email='admin@e.com', password='pw')
        self.admin.groups.add(Group.objects.get(name='edl_admin'))
        self.client.force_login(self.admin)
        self.learner = User.objects.create_user('learner', email='learner@e.com', password='pw')
        self.inactive = User.objects.create_user('inactive', email='i@e.com', password='pw', is_active=False)

        patch_key = mock.patch.object(edxapp, 'parse_course_key', side_effect=lambda c: c)
        patch_course = mock.patch.object(edxapp, 'get_course', return_value=mock.Mock())
        patch_allow = mock.patch.object(edxapp, 'allow_course_role')
        patch_revoke = mock.patch.object(edxapp, 'revoke_course_role')
        patch_isenr = mock.patch.object(edxapp, 'is_enrolled', return_value=False)
        patch_enroll = mock.patch.object(edxapp, 'enroll_user')
        self.mock_key = patch_key.start()
        self.mock_course = patch_course.start()
        self.mock_allow = patch_allow.start()
        self.mock_revoke = patch_revoke.start()
        self.mock_isenr = patch_isenr.start()
        self.mock_enroll = patch_enroll.start()
        for p in (patch_key, patch_course, patch_allow, patch_revoke, patch_isenr, patch_enroll):
            self.addCleanup(p.stop)

    def _post(self, **over):
        payload = {'course_id': self.COURSE, 'identifier': 'learner', 'role': 'staff', 'action': 'allow'}
        payload.update(over)
        return self.client.post(self.url, payload, format='json')

    def test_grant_allows_role_auto_enrolls_and_audits(self):
        response = self._post(role='instructor', action='allow')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.mock_allow.assert_called_once()
        # allow_course_role(course, user, level)
        course_arg, user_arg, level_arg = self.mock_allow.call_args.args
        self.assertEqual(user_arg, self.learner)
        self.assertEqual(level_arg, 'instructor')
        self.mock_enroll.assert_called_once_with(self.learner, self.COURSE)  # auto-enroll
        entry = EdlAdminAuditLog.objects.get()
        self.assertEqual(entry.action, EdlAdminAuditLog.Action.ROLE_GRANT)
        self.assertEqual(entry.detail, {'role': 'instructor'})
        self.assertEqual(entry.course_id, self.COURSE)

    def test_grant_skips_enroll_when_already_enrolled(self):
        self.mock_isenr.return_value = True
        self._post(action='allow')
        self.mock_enroll.assert_not_called()

    def test_grant_to_inactive_user_is_409_and_no_role_change(self):
        response = self._post(identifier='inactive', action='allow')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.mock_allow.assert_not_called()
        self.mock_enroll.assert_not_called()
        self.assertEqual(EdlAdminAuditLog.objects.count(), 0)

    def test_revoke_calls_revoke_and_audits(self):
        response = self._post(action='revoke')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.mock_revoke.assert_called_once()
        self.mock_allow.assert_not_called()
        self.assertEqual(EdlAdminAuditLog.objects.get().action, EdlAdminAuditLog.Action.ROLE_REVOKE)

    def test_revoke_from_inactive_user_is_allowed(self):
        response = self._post(identifier='inactive', action='revoke')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.mock_revoke.assert_called_once()

    def test_non_grantable_role_is_400(self):
        response = self._post(role='global_staff', action='allow')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('role', response.data)
        self.mock_allow.assert_not_called()

    def test_unknown_user_is_404(self):
        response = self._post(identifier='ghost', action='allow')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.mock_allow.assert_not_called()

    def test_invalid_course_id_is_400(self):
        self.mock_key.side_effect = ValueError('bad')
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('course_id', response.data)

    def test_unknown_course_is_404(self):
        self.mock_course.side_effect = Exception('not found')
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('course_id', response.data)
