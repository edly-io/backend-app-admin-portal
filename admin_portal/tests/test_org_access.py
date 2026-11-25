"""Tests for organization access and Studio request handling."""
import importlib
from unittest.mock import Mock, patch

import pytest
import requests
from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from admin_portal import org_access, studio_client
from admin_portal.models import EdlAdminAuditLog

User = get_user_model()


@pytest.mark.django_db
def test_service_user_migration_idempotent():
    migration = importlib.import_module('admin_portal.migrations.0004_create_portal_service_user')
    with override_settings(ADMIN_PORTAL_SERVICE_USER='custom_service'):
        migration.create_service_user(apps, None)
        user = User.objects.get(username='custom_service')
        assert user.is_staff and user.is_active and not user.is_superuser and not user.has_usable_password()
        migration.create_service_user(apps, None)
        assert User.objects.filter(username='custom_service').count() == 1
        user.is_staff = False
        user.save()
        with pytest.raises(RuntimeError):
            migration.create_service_user(apps, None)
        user.refresh_from_db()
        assert not user.is_staff


@pytest.mark.django_db
def test_access_summary_and_global_creator():
    user = User.objects.create_user('partner')
    rows = [(user.id, 'org_course_creator_group', 'A'), (user.id, 'instructor', 'A'),
            (user.id, 'data_researcher', 'A'), (user.id, 'instructor', 'B'),
            (user.id, 'data_researcher', 'C'), (user.id, 'course_creator_group', '')]
    with patch.object(org_access.edxapp, 'org_role_rows', return_value=rows) as query:
        result = org_access.get_org_access(user.username)
    assert result['global_creator'] and result['org_admin'] and not result['visibility']
    assert result['organizations'] == ['A', 'B', 'C']
    assert result['partial_visibility_orgs'] == ['B', 'C']
    assert result['visibility_orgs'] == ['A']
    query.assert_called_once_with([user.id])


@pytest.mark.django_db
@pytest.mark.parametrize('url', ['organizations', 'user-org-access'])
def test_gate(url):
    kwargs = {'username': 'someone'} if url == 'user-org-access' else {}
    response = APIClient().get(reverse('admin_portal:v1:' + url, kwargs=kwargs))
    assert response.status_code == 403


@pytest.mark.django_db
def test_grant_and_lms_failure_restore():
    actor = User.objects.create_user('actor')
    User.objects.create_user('partner')
    snapshot = {'state': None, 'all_organizations': None, 'organizations': [], 'snapshot_token': 'signed'}
    with patch.object(org_access.edxapp, 'list_active_organizations', return_value=[{'short_name': 'A'}]), \
         patch.object(org_access.edxapp, 'org_role_rows', return_value=[]), \
         patch.object(org_access.studio_client, 'get_state', return_value=snapshot), \
         patch.object(org_access.studio_client, 'set_state', return_value={'changed': True, 'granted_orgs': ['A']}), \
         patch.object(org_access.studio_client, 'restore_state') as restore, \
         patch.object(org_access.edxapp, 'set_org_visibility', side_effect=RuntimeError('failure')):
        with pytest.raises(org_access.OrgAccessError) as error:
            org_access.set_org_access(actor=actor, username='partner', org_admin=True, organizations=['A'], visibility=True)
    assert error.value.code == 'lms_failed_undone'
    restore.assert_called_once_with('partner', 'signed', 'actor')
    assert EdlAdminAuditLog.objects.filter(detail__outcome='failed').exists()


@pytest.mark.django_db
def test_global_downgrade_requires_confirmation():
    actor = User.objects.create_user('actor')
    User.objects.create_user('partner')
    snapshot = {'state': 'granted', 'all_organizations': True, 'organizations': [], 'snapshot_token': 'signed'}
    with patch.object(org_access.edxapp, 'list_active_organizations', return_value=[{'short_name': 'A'}]), \
         patch.object(org_access.edxapp, 'org_role_rows', return_value=[]), \
         patch.object(org_access.studio_client, 'get_state', return_value=snapshot), \
         patch.object(org_access.studio_client, 'set_state') as write:
        with pytest.raises(org_access.OrgAccessError) as error:
            org_access.set_org_access(actor=actor, username='partner', org_admin=True, organizations=['A'], visibility=True)
    assert error.value.code == 'global_creator_downgrade'
    write.assert_not_called()


def test_retry_tracks_uncertain_attempts(settings):
    settings.ADMIN_PORTAL_STUDIO_BACKOFF = (1, 2)
    response = Mock(status_code=503)
    with patch.object(studio_client.edxapp, 'get_service_user'), \
         patch.object(studio_client.edxapp, 'mint_service_jwt', return_value='token'), \
         patch.object(studio_client.requests, 'request', side_effect=[requests.Timeout(), response, response]) as request, \
         patch.object(studio_client, '_sleep') as sleep:
        with pytest.raises(studio_client.StudioError) as error:
            studio_client.get_state('partner')
    assert error.value.kind == 'uncertain'
    assert request.call_count == 3 and sleep.call_count == 2
    assert request.call_args.kwargs['headers'] == {'Authorization': 'JWT token'}
    assert request.call_args.kwargs['timeout'] == 10


@pytest.mark.django_db
@pytest.mark.parametrize('failure, read_state, expected, restore_called', [
    ('unavailable', None, 'studio_unavailable', False),
    ('uncertain', {'state': None, 'all_organizations': None, 'organizations': []}, 'studio_unavailable', False),
    ('uncertain', None, 'studio_unavailable', True),
    ('uncertain', {'state': 'granted', 'all_organizations': False, 'organizations': ['A']}, None, False),
])
def test_studio_failures_and_readback(failure, read_state, expected, restore_called):
    actor = User.objects.create_user('actor')
    User.objects.create_user('partner')
    snapshot = {'state': None, 'all_organizations': None, 'organizations': [], 'snapshot_token': 'signed'}
    readback = read_state if read_state is not None else studio_client.StudioError('unavailable')
    with patch.object(org_access.edxapp, 'list_active_organizations', return_value=[{'short_name': 'A'}]), \
         patch.object(org_access.edxapp, 'org_role_rows', return_value=[]), \
         patch.object(org_access.studio_client, 'get_state', side_effect=[snapshot, readback]) as get, \
         patch.object(org_access.studio_client, 'set_state', side_effect=studio_client.StudioError(failure)), \
         patch.object(org_access.studio_client, 'restore_state') as restore, \
         patch.object(org_access.edxapp, 'set_org_visibility', return_value=(['A'], [])) as write:
        if expected:
            with pytest.raises(org_access.OrgAccessError) as error:
                org_access.set_org_access(actor=actor, username='partner', org_admin=True, organizations=['A'], visibility=True)
            assert error.value.code == expected
            write.assert_not_called()
        else:
            org_access.set_org_access(actor=actor, username='partner', org_admin=True, organizations=['A'], visibility=True)
            write.assert_called_once()
        assert restore.called == restore_called
        assert get.call_count == (1 if failure == 'unavailable' else 2)


@pytest.mark.django_db
def test_failed_undo_reports_out_of_sync():
    actor = User.objects.create_user('actor')
    User.objects.create_user('partner')
    snapshot = {'state': 'granted', 'all_organizations': True, 'organizations': [], 'snapshot_token': 'signed'}
    with patch.object(org_access.edxapp, 'list_active_organizations', return_value=[{'short_name': 'A'}]), \
         patch.object(org_access.edxapp, 'org_role_rows', return_value=[]), \
         patch.object(org_access.studio_client, 'get_state', side_effect=[snapshot, studio_client.StudioError('unavailable')]), \
         patch.object(org_access.studio_client, 'set_state', return_value={'changed': True}), \
         patch.object(org_access.studio_client, 'restore_state', side_effect=studio_client.StudioError('unavailable')), \
         patch.object(org_access.edxapp, 'set_org_visibility', side_effect=RuntimeError('failure')):
        with pytest.raises(org_access.OrgAccessError) as error:
            org_access.set_org_access(actor=actor, username='partner', org_admin=True, organizations=['A'], visibility=True,
                                      confirm_downgrade=True)
    assert error.value.code == 'out_of_sync'
    assert error.value.out_of_sync['studio'] == 'unknown'
    assert EdlAdminAuditLog.objects.filter(detail__outcome='out_of_sync').exists()


@pytest.mark.django_db
def test_out_of_sync_message_names_all_organizations():
    user = User.objects.create_user('partner')
    studio = {'state': 'granted', 'all_organizations': True, 'organizations': []}
    error = org_access._out_of_sync(user, studio)
    assert 'Run creation is set to: all organizations.' in error.detail


@pytest.mark.django_db
def test_service_user_migration_uses_unique_email():
    migration = importlib.import_module('admin_portal.migrations.0004_create_portal_service_user')
    User.objects.filter(username='edl_portal_service').delete()
    migration.create_service_user(apps, None)
    service = User.objects.get(username='edl_portal_service')
    assert service.email == 'edl_portal_service@service.invalid'
    assert service.is_staff and service.is_active


@pytest.mark.django_db
def test_list_queries_roles_once():
    from django.contrib.auth.models import Group
    actor = User.objects.create_user('actor')
    actor.groups.add(Group.objects.get(name='edl_admin'))
    client = APIClient()
    client.force_login(actor)
    with patch.object(org_access.edxapp, 'org_role_rows', return_value=[
        (actor.id, 'instructor', 'A'), (actor.id, 'data_researcher', 'A'),
        (actor.id, 'instructor', 'B'), (actor.id, 'course_creator_group', ''),
    ]) as query:
        response = client.get(reverse('admin_portal:v1:users'))
    row = next(item for item in response.data['results'] if item['username'] == 'actor')
    assert row['org_visibility_orgs'] == ['A'] and row['org_admin_all_orgs']
    assert query.call_count == 1


@pytest.mark.django_db
@pytest.mark.parametrize('body', [
    {'org_admin': True, 'organizations': [], 'visibility': False},
    {'org_admin': False, 'organizations': [], 'visibility': True},
    {'org_admin': True, 'organizations': ['a'], 'visibility': False},
])
def test_invalid_request_does_not_call_studio(body):
    actor = User.objects.create_user('actor')
    User.objects.create_user('partner')
    with patch.object(org_access.edxapp, 'list_active_organizations', return_value=[{'short_name': 'A'}]), \
         patch.object(org_access.studio_client, 'get_state') as get:
        with pytest.raises(org_access.OrgAccessError) as error:
            org_access.set_org_access(actor=actor, username='partner', **body)
    assert error.value.status == 400
    get.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize('flags, expected', [
    ({'is_active': False}, 'user_inactive'),
    ({'is_staff': True}, 'user_is_global_staff'),
])
def test_uneditable_user(flags, expected):
    actor = User.objects.create_user('actor')
    User.objects.create_user('partner', **flags)
    with patch.object(org_access.studio_client, 'get_state') as get:
        with pytest.raises(org_access.OrgAccessError) as error:
            org_access.set_org_access(actor=actor, username='partner', org_admin=False, organizations=[], visibility=False)
    assert error.value.code == expected
    get.assert_not_called()
    assert org_access.get_org_access('partner')['editable'] is False


@pytest.mark.django_db
def test_missing_service_account_is_audited():
    actor = User.objects.create_user('actor')
    User.objects.create_user('partner')
    with patch.object(org_access.edxapp, 'get_service_user', return_value=None), \
         patch.object(org_access.edxapp, 'list_active_organizations', return_value=[]), \
         patch.object(org_access.studio_client, 'get_state') as get:
        with pytest.raises(org_access.OrgAccessError) as error:
            org_access.set_org_access(actor=actor, username='partner', org_admin=False, organizations=[], visibility=False)
    assert error.value.code == 'service_account_not_set_up'
    assert EdlAdminAuditLog.objects.get().detail['failed_step'] == 'service_account'
    get.assert_not_called()


@pytest.mark.parametrize('status_code, kind, attempts', [
    (503, 'unavailable', 3), (502, 'uncertain', 3), (504, 'uncertain', 3),
    (400, 'rejected', 1), (401, 'rejected', 1), (403, 'rejected', 1), (404, 'rejected', 1),
])
def test_studio_status_retry_policy(settings, status_code, kind, attempts):
    response = Mock(status_code=status_code)
    response.json.return_value = {'code': 'failure', 'detail': 'Failure'}
    with patch.object(studio_client.edxapp, 'get_service_user'), \
         patch.object(studio_client.edxapp, 'mint_service_jwt', return_value='token'), \
         patch.object(studio_client.requests, 'request', return_value=response) as request, \
         patch.object(studio_client, '_sleep'):
        with pytest.raises(studio_client.StudioError) as error:
            studio_client.get_state('partner')
    assert error.value.kind == kind
    assert request.call_count == attempts


@pytest.mark.django_db
@pytest.mark.parametrize('org_admin, organizations, visibility, studio_result, role_result, action', [
    (True, ['A'], True, {'changed': True, 'granted_orgs': ['A'], 'removed_orgs': []}, (['A'], []), 'org_access_grant'),
    (False, [], False, {'changed': True, 'granted_orgs': [], 'removed_orgs': ['A']}, ([], ['A']), 'org_access_revoke'),
    (True, ['A'], False, {'changed': False, 'granted_orgs': [], 'removed_orgs': []}, ([], []), None),
])
def test_success_audit_and_noop(org_admin, organizations, visibility, studio_result, role_result, action):
    actor = User.objects.create_user('actor')
    User.objects.create_user('partner')
    snapshot = {'state': 'unrequested', 'all_organizations': False, 'organizations': [], 'snapshot_token': 'signed'}
    with patch.object(org_access.edxapp, 'list_active_organizations', return_value=[{'short_name': 'A'}]), \
         patch.object(org_access.edxapp, 'org_role_rows', return_value=[]), \
         patch.object(org_access.studio_client, 'get_state', return_value=snapshot), \
         patch.object(org_access.studio_client, 'set_state', return_value=studio_result) as studio, \
         patch.object(org_access.edxapp, 'set_org_visibility', return_value=role_result) as lms:
        result = org_access.set_org_access(actor=actor, username='partner', org_admin=org_admin,
                                           organizations=organizations, visibility=visibility)
    studio.assert_called_once_with('partner', org_admin, organizations, 'actor', False)
    lms.assert_called_once()
    assert result['changes']['visibility_added'] == role_result[0]
    assert list(EdlAdminAuditLog.objects.values_list('action', flat=True)) == ([action] if action else [])


@pytest.mark.django_db
def test_organizations_endpoint_and_put_validation():
    from django.contrib.auth.models import Group
    actor = User.objects.create_user('actor')
    actor.groups.add(Group.objects.get(name='edl_admin'))
    client = APIClient()
    client.force_login(actor)
    with patch.object(org_access.edxapp, 'list_active_organizations', return_value=[{'short_name': 'A', 'name': 'Alpha'}]):
        response = client.get(reverse('admin_portal:v1:organizations'))
    assert response.data == {'results': [{'short_name': 'A', 'name': 'Alpha'}]}
    with patch.object(org_access.studio_client, 'get_state') as get:
        response = client.put(reverse('admin_portal:v1:user-org-access', kwargs={'username': 'partner'}),
                              {'org_admin': True, 'organizations': [], 'visibility': False}, format='json')
    assert response.status_code == 400 and response.data['code'] == 'validation_error'
    get.assert_not_called()


@pytest.mark.django_db
def test_deactivated_user_is_not_editable():
    actor = User.objects.create_user('actor')
    User.objects.create_user('partner')
    with patch.object(org_access, 'get_standing_status', return_value='disabled'), \
         patch.object(org_access.studio_client, 'get_state') as get:
        with pytest.raises(org_access.OrgAccessError) as error:
            org_access.set_org_access(actor=actor, username='partner', org_admin=False, organizations=[], visibility=False)
        state = org_access.get_org_access('partner')
    assert error.value.code == 'user_disabled'
    get.assert_not_called()
    assert state['editable'] is False and state['not_editable_reason'] == 'disabled'
