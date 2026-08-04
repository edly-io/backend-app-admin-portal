"""Thin seam over edx-platform account/password APIs.

Every call into core lives here and imports lazily, so the plugin (and its
standalone test suite) imports cleanly without edx-platform present. Tests
patch these functions; in the LMS they delegate to the real platform helpers.

We deliberately *reuse* the platform's own account-creation, password and
email machinery rather than reimplementing any of it.
"""

try:  # AccountValidationError carries the structured duplicate-field info.
    from common.djangoapps.student.helpers import AccountValidationError
except Exception:  # pragma: no cover - standalone fallback (edx-platform absent)
    class AccountValidationError(Exception):
        """Standalone stand-in mirroring the platform exception's shape."""

        def __init__(self, message, field=None, error_code=None):
            super().__init__(message)
            self.field = field
            self.error_code = error_code


def account_creation_form(data):
    """Build the platform ``AccountCreationForm`` (terms not required for admin-created accounts)."""
    from openedx.core.djangoapps.user_authn.views.registration_form import AccountCreationForm
    return AccountCreationForm(data=data, tos_required=False)


def do_create_account(form):
    """Create User + UserProfile + Registration via the platform helper."""
    from common.djangoapps.student.helpers import do_create_account as _do_create_account
    return _do_create_account(form)


def generate_password(length=12):
    """Generate a validator-compliant random password (platform helper)."""
    from edx_django_utils.user import generate_password as _generate_password
    return _generate_password(length=length)


def send_set_password_email(user, request=None):
    """Email the user a single-use set-password link (activates on confirm)."""
    from openedx.core.djangoapps.user_authn.views.password_reset import (
        send_password_reset_email_for_user,
    )
    return send_password_reset_email_for_user(user, request)


def set_user_standing(user, disabled, changed_by):
    """
    Disable or re-enable an account via ``UserStanding`` (EDL-7).

    Mirrors the platform's ``disable_account_ajax``: disabled accounts are
    blocked by ``UserStandingMiddleware`` while enrollments, submissions and
    grades are retained. Returns the resulting standing status string.
    """
    from common.djangoapps.student.models import UserStanding
    status = UserStanding.ACCOUNT_DISABLED if disabled else UserStanding.ACCOUNT_ENABLED
    standing, _created = UserStanding.objects.get_or_create(
        user=user, defaults={'account_status': status, 'changed_by': changed_by},
    )
    standing.account_status = status
    standing.changed_by = changed_by
    standing.save()
    return status


def parse_course_key(course_id):
    """Parse a course-id string into a CourseKey (raises on malformed input)."""
    from opaque_keys.edx.keys import CourseKey
    return CourseKey.from_string(course_id)


def split_identifiers(raw):
    """Split a comma/newline-separated identifier string (platform helper)."""
    from lms.djangoapps.instructor.views.api import _split_input_list
    return _split_input_list(raw)


def course_exists(course_key):
    """True if the (published) course run exists in the LMS modulestore."""
    from openedx.core.lib.courses import get_course_by_id
    try:
        get_course_by_id(course_key)
        return True
    except Exception:  # noqa: BLE001 - Http404/ValueError when absent
        return False


def get_course(course_key):
    """Return the course object for ``course_key`` (raises if absent)."""
    from openedx.core.lib.courses import get_course_by_id
    return get_course_by_id(course_key)


def allow_course_role(course, user, level):
    """Grant a course-scoped role via the platform's ``allow_access`` (EDL-10)."""
    from lms.djangoapps.instructor.access import allow_access
    allow_access(course, user, level, send_email=False)


def revoke_course_role(course, user, level):
    """Revoke a course-scoped role via the platform's ``revoke_access`` (EDL-10)."""
    from lms.djangoapps.instructor.access import revoke_access
    revoke_access(course, user, level, send_email=False)


def is_enrolled(user, course_key):
    """True if ``user`` has an active enrollment in ``course_key``."""
    from common.djangoapps.student.models import CourseEnrollment
    return CourseEnrollment.is_enrolled(user, course_key)


def enroll_user(user, course_key):
    """Enroll ``user`` in ``course_key`` (used to auto-enroll on role grant)."""
    from common.djangoapps.student.models import CourseEnrollment
    return CourseEnrollment.enroll(user, course_key)


def process_enrollment_batch(*, request_user, course_key, action, identifiers,
                             auto_enroll, email_students, reason, secure):
    """
    Enroll/unenroll a batch of identifiers via the platform helper (EDL-8/9).

    Reuses ``process_student_enrollment_batch`` which resolves each identifier
    (email or username), toggles the notification email, creates
    ``CourseEnrollmentAllowed`` for not-yet-registered emails on enroll, does a
    soft (data-retaining) unenroll, and writes ``ManualEnrollmentAudit`` per
    student. Returns the platform's per-identifier results dict.
    """
    from lms.djangoapps.instructor.utils import process_student_enrollment_batch
    return process_student_enrollment_batch(
        request_user=request_user,
        course_key=course_key,
        action=action,
        identifiers=identifiers,
        auto_enroll=auto_enroll,
        email_students=email_students,
        reason=reason,
        secure=secure,
    )
