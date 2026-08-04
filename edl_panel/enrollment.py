"""Enrollment service for the edl_panel plugin (EDL-8 enroll / EDL-9 unenroll).

Thin wrapper over the platform's ``process_student_enrollment_batch``: validates
the course run and identifiers, then delegates. The core helper handles
identifier resolution, the notification-email toggle, ``CourseEnrollmentAllowed``
for pending users, soft (data-retaining) unenroll, and per-student
``ManualEnrollmentAudit`` rows.
"""
from edl_panel import edxapp

ACTION_ENROLL = 'enroll'
ACTION_UNENROLL = 'unenroll'


class EnrollmentError(Exception):
    """Validation error carrying inline field errors and a status code."""

    def __init__(self, field_errors, status_code=400):
        super().__init__(str(field_errors))
        self.field_errors = field_errors
        self.status_code = status_code


def _normalize_identifiers(identifiers):
    if isinstance(identifiers, str):
        identifiers = edxapp.split_identifiers(identifiers)
    return [str(item).strip() for item in identifiers if str(item).strip()]


def update_enrollments(*, actor, request, course_id, identifiers, action,
                       email_students=False, auto_enroll=False, reason=''):
    """
    Enroll or unenroll ``identifiers`` in ``course_id``.

    Returns the platform batch-result dict. Raises :class:`EnrollmentError`
    (400/404) for a malformed/unknown course or empty identifier list.
    """
    try:
        course_key = edxapp.parse_course_key(course_id)
    except Exception as exc:  # noqa: BLE001 - InvalidKeyError et al.
        raise EnrollmentError({'course_id': ['Invalid course id.']}, 400) from exc

    if not edxapp.course_exists(course_key):
        raise EnrollmentError({'course_id': ['Course run not found or not published.']}, 404)

    idents = _normalize_identifiers(identifiers)
    if not idents:
        raise EnrollmentError({'identifiers': ['At least one identifier is required.']}, 400)

    secure = bool(request is not None and request.is_secure())
    return edxapp.process_enrollment_batch(
        request_user=actor,
        course_key=course_key,
        action=action,
        identifiers=idents,
        auto_enroll=auto_enroll,
        email_students=email_students,
        reason=reason,
        secure=secure,
    )
