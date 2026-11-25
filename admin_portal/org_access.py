"""Organization access orchestration across Studio and the LMS."""
from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db import transaction

from admin_portal import edxapp, studio_client
from admin_portal.audit import record_action
from admin_portal.directory import ACCOUNT_DISABLED, get_profile_name, get_standing_status
from admin_portal.models import EdlAdminAuditLog


class OrgAccessError(Exception):
    """An error suitable for returning to the portal."""

    def __init__(self, code, detail, status, field_errors=None, out_of_sync=None):
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, status
        self.field_errors, self.out_of_sync = field_errors, out_of_sync


def list_organizations():
    """Return the active organization directory."""
    return edxapp.list_active_organizations()


def org_access_for_users(user_ids):
    """Summarize one query of organization-wide role rows."""
    groups = defaultdict(lambda: {'admin': set(), 'instructor': set(), 'data_researcher': set(), 'global': False})
    for user_id, role, org in edxapp.org_role_rows(user_ids):
        entry = groups[user_id]
        if role == 'course_creator_group' and not org:
            entry['global'] = True
        elif org and role == 'org_course_creator_group':
            entry['admin'].add(org)
        elif org and role in ('instructor', 'data_researcher'):
            entry[role].add(org)
    return {user_id: {
        'org_admin_orgs': sorted(entry['admin']),
        'org_admin_all_orgs': entry['global'],
        'org_visibility_orgs': sorted(entry['instructor'] & entry['data_researcher']),
        'partial_visibility_orgs': sorted(entry['instructor'] ^ entry['data_researcher']),
    } for user_id, entry in groups.items()}


def _user(username):
    user = get_user_model().objects.filter(username=username).first()
    if user is None:
        raise OrgAccessError('user_not_found', 'User not found.', 404)
    return user


def get_org_access(username):
    """Read access from current LMS role rows."""
    user = _user(username)
    entry = org_access_for_users([user.id]).get(user.id, {})
    admin = entry.get('org_admin_orgs', [])
    visible = entry.get('org_visibility_orgs', [])
    partial = entry.get('partial_visibility_orgs', [])
    global_creator = entry.get('org_admin_all_orgs', False)
    orgs = sorted(set(admin) | set(visible) | set(partial))
    if user.is_staff:
        reason = 'global_staff'
    elif not user.is_active:
        reason = 'inactive'
    elif get_standing_status(user) == ACCOUNT_DISABLED:
        reason = 'disabled'
    else:
        reason = None
    return {
        'username': user.username, 'name': get_profile_name(user), 'editable': reason is None,
        'not_editable_reason': reason, 'global_creator': global_creator,
        'org_admin': bool(admin or global_creator), 'org_admin_orgs': admin,
        'visibility_orgs': visible, 'partial_visibility_orgs': partial, 'organizations': orgs,
        'visibility': bool(orgs and not global_creator and set(orgs) <= set(visible)),
    }


def _studio_matches(state, org_admin, orgs):
    if org_admin:
        return (state.get('state') == 'granted' and state.get('all_organizations') is False
                and set(state.get('organizations') or []) == set(orgs))
    return state.get('state') != 'granted' and not state.get('organizations')


def _snapshot_matches(left, right):
    return all(left.get(key) == right.get(key) for key in ('state', 'all_organizations')) and (
        set(left.get('organizations') or []) == set(right.get('organizations') or [])
    )


def set_org_access(*, actor, username, org_admin, organizations, visibility, confirm_downgrade=False):
    """Apply a desired state, compensating Studio if the LMS write fails."""
    user = _user(username)
    if not user.is_active:
        raise OrgAccessError('user_inactive', 'This account is not active. Activate it before giving organization access.', 409)
    if get_standing_status(user) == ACCOUNT_DISABLED:
        raise OrgAccessError('user_disabled', 'This account is deactivated. Reactivate it before giving organization access.', 409)
    if user.is_staff:
        raise OrgAccessError('user_is_global_staff', 'This user is global staff and already has access to every course.', 409)
    organizations = list(dict.fromkeys(organizations))
    if visibility and not org_admin:
        raise OrgAccessError('validation_error', 'Course visibility needs org admin to be on.', 400)
    if org_admin and not organizations:
        raise OrgAccessError('validation_error', 'Choose at least one organization.', 400)
    if not org_admin and organizations:
        raise OrgAccessError('validation_error', 'Organizations must be empty when org admin is off.', 400)
    unknown = sorted(set(organizations) - {org['short_name'] for org in list_organizations()})
    if unknown:
        raise OrgAccessError('unknown_organizations', f"These organizations do not exist: {', '.join(unknown)}. Names must match exactly, including capital letters.", 400)
    before = get_org_access(username)
    action = EdlAdminAuditLog.Action.ORG_ACCESS_GRANT if org_admin else EdlAdminAuditLog.Action.ORG_ACCESS_REVOKE
    requested = {'org_admin': org_admin, 'organizations': organizations, 'visibility': visibility,
                 'confirm_downgrade': confirm_downgrade}
    snapshot = None
    step = 'service_account'
    try:
        service = edxapp.get_service_user()
        if not service or not service.is_active or not service.is_staff:
            raise OrgAccessError('service_account_not_set_up', 'Service account is not set up. Nothing was changed.', 503)
        step = 'studio_snapshot'
        try:
            snapshot = studio_client.get_state(username)
        except studio_client.StudioError as exc:
            raise OrgAccessError('studio_unavailable', 'Studio did not respond. Nothing was changed. Please try again.', 502) from exc
        downgrade = snapshot.get('state') == 'granted' and snapshot.get('all_organizations') is True
        if downgrade and not confirm_downgrade:
            raise OrgAccessError('global_creator_downgrade', 'This user can create course runs in every organization. Confirm the change to limit or remove that.', 409)
        if downgrade:
            action = EdlAdminAuditLog.Action.ORG_ACCESS_REVOKE
        step = 'studio_write'
        try:
            studio_result = studio_client.set_state(username, org_admin, organizations, actor.username, confirm_downgrade)
        except studio_client.StudioError as exc:
            if exc.kind == 'rejected':
                mapped = {'user_not_found': (404, 'User not found.'),
                          'user_inactive': (409, 'This account is not active. Activate it before giving organization access.'),
                          'user_is_global_staff': (409, 'This user is global staff and already has access to every course.'),
                          'global_creator_downgrade': (409, 'This user can create course runs in every organization. Confirm the change to limit or remove that.'),
                          'service_account_not_set_up': (503, 'Service account is not set up. Nothing was changed.')}
                if exc.code == 'unknown_organizations':
                    raise OrgAccessError('unknown_organizations', exc.detail or 'These organizations do not exist.', 400) from exc
                if exc.code in ('organizations_required', 'organizations_not_allowed'):
                    raise OrgAccessError('validation_error', exc.detail or 'Check the organizations.', 400) from exc
                if exc.code in mapped:
                    status, detail = mapped[exc.code]
                    raise OrgAccessError(exc.code, detail, status) from exc
                raise OrgAccessError('studio_rejected', f'Studio refused the change: {exc.detail or exc.code or "Unknown error"}. Nothing was changed.', 502) from exc
            if exc.kind == 'uncertain':
                try:
                    current = studio_client.get_state(username)
                except studio_client.StudioError:
                    current = None
                if current and _studio_matches(current, org_admin, organizations):
                    studio_result = {}
                elif current and _snapshot_matches(current, snapshot):
                    raise OrgAccessError('studio_unavailable', 'Studio did not respond. Nothing was changed. Please try again.', 502) from exc
                else:
                    step = 'studio_undo'
                    try:
                        studio_client.restore_state(username, snapshot['snapshot_token'], actor.username)
                    except studio_client.StudioError as undo_exc:
                        raise _out_of_sync(user, 'unknown') from undo_exc
                    raise OrgAccessError('studio_unavailable', 'Studio did not respond. Nothing was changed. Please try again.', 502) from exc
            else:
                raise OrgAccessError('studio_unavailable', 'Studio did not respond. Nothing was changed. Please try again.', 502) from exc
        step = 'lms_write'
        try:
            with transaction.atomic():
                added, removed = edxapp.set_org_visibility(user, organizations if visibility else [])
        except Exception as exc:
            step = 'studio_undo'
            try:
                studio_client.restore_state(username, snapshot['snapshot_token'], actor.username)
            except studio_client.StudioError as undo_exc:
                try:
                    current = studio_client.get_state(username)
                    studio = {key: current.get(key) for key in ('state', 'all_organizations', 'organizations')}
                except studio_client.StudioError:
                    studio = 'unknown'
                raise _out_of_sync(user, studio) from undo_exc
            step = 'lms_write'
            raise OrgAccessError('lms_failed_undone', 'Course visibility could not be saved. Run creation was put back as it was. Nothing was changed.', 500) from exc
        after = get_org_access(username)
        granted = studio_result.get('granted_orgs', sorted(set(after['org_admin_orgs']) - set(before['org_admin_orgs'])))
        removed_orgs = studio_result.get('removed_orgs', sorted(set(before['org_admin_orgs']) - set(after['org_admin_orgs'])))
        changes = {'granted_orgs': granted, 'removed_orgs': removed_orgs, 'visibility_added': added, 'visibility_removed': removed}
        if granted or removed_orgs or added or removed or downgrade or studio_result.get('changed'):
            if not downgrade:
                action = EdlAdminAuditLog.Action.ORG_ACCESS_GRANT if granted or added else EdlAdminAuditLog.Action.ORG_ACCESS_REVOKE
            record_action(actor, action, target_user=user, detail={
                'outcome': 'success', 'orgs_before': before['org_admin_orgs'], 'orgs_after': after['org_admin_orgs'],
                'all_orgs_before': before['global_creator'], 'visibility_before': before['visibility_orgs'],
                'visibility_after': after['visibility_orgs'], **changes, 'downgrade': downgrade, 'studio_actor': service.username,
            })
        return {**after, 'changes': changes}
    except OrgAccessError as exc:
        if exc.code != 'global_creator_downgrade':
            record_action(actor, action, target_user=user, detail={
                'outcome': 'out_of_sync' if exc.code == 'out_of_sync' else 'failed', 'requested': requested,
                'failed_step': step, 'error': f'{exc.code}: {exc.detail}',
                'snapshot': {k: v for k, v in (snapshot or {}).items() if k != 'snapshot_token'},
                'out_of_sync': exc.out_of_sync,
            })
        raise


def _out_of_sync(user, studio):
    visibility = get_org_access(user.username)['visibility_orgs']
    if studio == 'unknown':
        run_creation = 'unknown'
    elif isinstance(studio, dict) and studio.get('all_organizations'):
        run_creation = 'all organizations'
    else:
        orgs = studio.get('organizations', []) if isinstance(studio, dict) else []
        run_creation = ', '.join(orgs) or 'off'
    message = (f"Access is only partly saved. Run creation is set to: {run_creation}. "
               f"Course visibility is set to: {', '.join(visibility) or 'off'}. Please save again or contact support.")
    return OrgAccessError('out_of_sync', message, 500, out_of_sync={'studio': studio, 'lms_visibility_orgs': visibility})
