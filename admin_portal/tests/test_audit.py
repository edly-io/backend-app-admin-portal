"""Tests for the audit helper and model (EDL-3)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APITestCase

from admin_portal.audit import record_action
from admin_portal.models import EdlAdminAuditLog

User = get_user_model()


class AuditLogTests(APITestCase):
    def test_record_action_writes_row_with_actor_and_target(self):
        actor = User.objects.create_user('admin', email='a@e.com', password='pw')
        target = User.objects.create_user('learner', email='l@e.com', password='pw')

        entry = record_action(
            actor, EdlAdminAuditLog.Action.CREATE_USER,
            target_user=target, detail={'source': 'panel'}, reason='onboarding',
        )

        self.assertEqual(EdlAdminAuditLog.objects.count(), 1)
        self.assertEqual(entry.actor, actor)
        self.assertEqual(entry.target_user, target)
        self.assertEqual(entry.action, 'create_user')
        self.assertEqual(entry.detail, {'source': 'panel'})
        self.assertEqual(entry.reason, 'onboarding')
        self.assertIsNotNone(entry.created)

    def test_anonymous_actor_stored_as_null(self):
        entry = record_action(
            AnonymousUser(), EdlAdminAuditLog.Action.ENROLL,
            target_identifier='new@e.com', course_id='course-v1:X+Y+Z',
        )
        self.assertIsNone(entry.actor)
        self.assertEqual(entry.target_identifier, 'new@e.com')
        self.assertEqual(entry.course_id, 'course-v1:X+Y+Z')

    def test_none_actor_stored_as_null(self):
        entry = record_action(None, EdlAdminAuditLog.Action.DEACTIVATE_USER)
        self.assertIsNone(entry.actor)

    def test_target_repr_prefers_username(self):
        target = User.objects.create_user('bob', email='b@e.com', password='pw')
        with_user = record_action(None, EdlAdminAuditLog.Action.UNENROLL, target_user=target)
        pending = record_action(None, EdlAdminAuditLog.Action.ENROLL, target_identifier='pending@e.com')
        self.assertEqual(with_user.target_repr, 'bob')
        self.assertEqual(pending.target_repr, 'pending@e.com')

    def test_default_detail_is_empty_dict(self):
        entry = record_action(None, EdlAdminAuditLog.Action.ROLE_GRANT, course_id='course-v1:X+Y+Z')
        self.assertEqual(entry.detail, {})
