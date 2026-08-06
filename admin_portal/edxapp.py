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
    Enroll/unenroll a batch of identifiers (EDL-8/9).

    This deliberately does NOT use ``lms.djangoapps.instructor.utils.
    process_student_enrollment_batch``: that helper was only added upstream in
    PR #37216 and is absent from the Open edX release this plugin targets
    (importing it raises ``ModuleNotFoundError`` at runtime). Instead we build
    on the long-stable primitives ``enroll_email`` / ``unenroll_email`` /
    ``get_email_params`` + ``ManualEnrollmentAudit`` — the same ones the
    instructor bulk-enroll endpoint uses — so this works across versions.

    For each identifier it resolves the user (email or username), toggles the
    notification email, creates ``CourseEnrollmentAllowed`` for not-yet-
    registered emails on enroll, does a soft (data-retaining) unenroll, and
    writes one ``ManualEnrollmentAudit`` row. Returns a per-identifier results
    dict: ``{action, auto_enroll, results, successful_operations,
    failed_operations, total_students}``.
    """
    import logging

    from django.contrib.auth import get_user_model
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email
    from django.db import transaction

    from common.djangoapps.student.models import (
        ALLOWEDTOENROLL_TO_ENROLLED,
        ALLOWEDTOENROLL_TO_UNENROLLED,
        DEFAULT_TRANSITION_STATE,
        ENROLLED_TO_ENROLLED,
        ENROLLED_TO_UNENROLLED,
        UNENROLLED_TO_ALLOWEDTOENROLL,
        UNENROLLED_TO_ENROLLED,
        UNENROLLED_TO_UNENROLLED,
        CourseEnrollment,
        EnrollStatusChange,
        ManualEnrollmentAudit,
        get_user_by_username_or_email,
    )
    from lms.djangoapps.instructor.enrollment import (
        enroll_email,
        get_email_params,
        get_user_email_language,
        unenroll_email,
    )
    from openedx.core.lib.courses import get_course_by_id

    log = logging.getLogger(__name__)
    User = get_user_model()

    def _enroll_transition(before, after):
        if not before['user']:
            return UNENROLLED_TO_ALLOWEDTOENROLL if after['allowed'] else DEFAULT_TRANSITION_STATE
        if after['enrollment']:
            if before['enrollment']:
                return ENROLLED_TO_ENROLLED
            if before['allowed']:
                return ALLOWEDTOENROLL_TO_ENROLLED
            return UNENROLLED_TO_ENROLLED
        return DEFAULT_TRANSITION_STATE

    def _unenroll_transition(before):
        if before['enrollment']:
            return ENROLLED_TO_UNENROLLED
        if before['allowed']:
            return ALLOWEDTOENROLL_TO_UNENROLLED
        return UNENROLLED_TO_UNENROLLED

    def _process_single(identifier):
        enrollment_obj = None
        language = None
        try:
            identified_user = get_user_by_username_or_email(identifier)
        except User.DoesNotExist:
            email = identifier
        else:
            email = identified_user.email
            language = get_user_email_language(identified_user)

        try:
            validate_email(email)  # raises ValidationError for a bad address
            # Enrollment + audit are all-or-nothing.
            with transaction.atomic():
                if action == EnrollStatusChange.enroll:
                    before, after, enrollment_obj = enroll_email(
                        course_key, email, auto_enroll, email_students, dict(email_params), language=language,
                    )
                    before_state, after_state = before.to_dict(), after.to_dict()
                    state_transition = _enroll_transition(before_state, after_state)
                elif action == EnrollStatusChange.unenroll:
                    before, after = unenroll_email(
                        course_key, email, email_students, dict(email_params), language=language,
                    )
                    before_state, after_state = before.to_dict(), after.to_dict()
                    state_transition = _unenroll_transition(before_state)
                    enrollment_obj = (
                        CourseEnrollment.get_enrollment(identified_user, course_key)
                        if identified_user else None
                    )
                else:
                    raise ValueError(f'Unknown enrollment action: {action!r}')

                ManualEnrollmentAudit.create_manual_enrollment_audit(
                    request_user, email, state_transition, reason, enrollment_obj,
                )
            return {
                'identifier': identifier,
                'before': before_state,
                'after': after_state,
                'success': True,
                'state_transition': state_transition,
            }
        except ValidationError:
            return {
                'identifier': identifier,
                'invalidIdentifier': True,
                'success': False,
                'error_type': 'invalid_identifier',
                'error_message': 'Invalid email address.',
            }
        except Exception as exc:  # noqa: BLE001 - report per-learner, keep the batch going
            log.exception('admin_portal enrollment failed for %s: %s', identifier, exc)
            return {
                'identifier': identifier,
                'error': True,
                'success': False,
                'error_type': 'general_error',
                'error_message': 'Something went wrong while processing this learner. Please try again.',
            }

    email_params = {}
    if email_students:
        email_params = get_email_params(get_course_by_id(course_key), auto_enroll, secure=secure)

    results = []
    successful_operations = 0
    failed_operations = 0
    for identifier in identifiers:
        result = _process_single(identifier)
        results.append(result)
        if result['success']:
            successful_operations += 1
        else:
            failed_operations += 1

    return {
        'action': action,
        'auto_enroll': auto_enroll,
        'results': results,
        'successful_operations': successful_operations,
        'failed_operations': failed_operations,
        'total_students': len(identifiers),
    }
