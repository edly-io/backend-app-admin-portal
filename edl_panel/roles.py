"""Course-scoped role management for the edl_panel plugin (EDL-10).

Only course-scoped roles are grantable — Site Admin / Global Staff and
org-wide roles are deliberately excluded. Granting mirrors the platform's
Course Team dashboard (``ModifyAccess``): the target must be active, and a
grantee is auto-enrolled in the course if not already enrolled — reusing
``allow_access`` alone would leave a "staff" member who can't see the course.
"""
from django.contrib.auth import get_user_model

from edl_panel import edxapp

User = get_user_model()

ACTION_ALLOW = 'allow'
ACTION_REVOKE = 'revoke'

# The allow-list. Keys are the platform role levels (lms/.../instructor/access.py
# ROLES); values are one-line descriptions for the UI.
GRANTABLE_ROLES = {
    'instructor': 'Course Admin — full control of the course team, content and settings.',
    'staff': 'Course Staff — manage content and learners, including Studio authoring.',
    'limited_staff': 'Limited Staff — course staff privileges in the LMS, without Studio access.',
}


class RoleActionError(Exception):
    """Validation/conflict error carrying inline field errors and a status code."""

    def __init__(self, field_errors, status_code=400):
        super().__init__(str(field_errors))
        self.field_errors = field_errors
        self.status_code = status_code


def role_catalog():
    """Return the grantable roles as ``[{role, description}, ...]``."""
    return [{'role': role, 'description': desc} for role, desc in GRANTABLE_ROLES.items()]


def _resolve_user(identifier):
    if '@' in identifier:
        return User.objects.filter(email__iexact=identifier).first()
    return User.objects.filter(username=identifier).first()


def change_course_role(*, actor, course_id, identifier, role, action):
    """
    Grant or revoke a course-scoped role.

    Returns the affected user. Raises :class:`RoleActionError` for a
    non-grantable role (400), malformed (400) / unknown (404) course, unknown
    user (404), or granting to an inactive account (409).
    """
    if role not in GRANTABLE_ROLES:
        raise RoleActionError({'role': ['Role is not grantable from this interface.']}, 400)

    try:
        course_key = edxapp.parse_course_key(course_id)
    except Exception as exc:  # noqa: BLE001
        raise RoleActionError({'course_id': ['Invalid course id.']}, 400) from exc

    try:
        course = edxapp.get_course(course_key)
    except Exception as exc:  # noqa: BLE001 - Http404/ValueError when absent
        raise RoleActionError({'course_id': ['Course run not found.']}, 404) from exc

    user = _resolve_user(identifier)
    if user is None:
        raise RoleActionError({'identifier': ['User not found.']}, 404)

    if action == ACTION_ALLOW:
        if not user.is_active:
            raise RoleActionError({'identifier': ['User account is not active.']}, 409)
        edxapp.allow_course_role(course, user, role)
        if not edxapp.is_enrolled(user, course_key):
            edxapp.enroll_user(user, course_key)
    else:
        edxapp.revoke_course_role(course, user, role)

    return user
