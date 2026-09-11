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


# ---------------------------------------------------------------------------
# Reporting seams (EDL Reporting).
#
# Every function below is the single place a given edx-platform model is
# touched, and each returns plain Python primitives (int, dict, list-of-dicts)
# — never a queryset or model instance. That keeps the reporting *service*
# layer (admin_portal.reporting.*) free of platform imports so it imports and
# unit-tests standalone, and it makes these functions the one mock point in the
# reporting test suite.
# ---------------------------------------------------------------------------

# Student profile columns for the platform report tasks (features CSV inputs).
_STUDENT_FEATURES = [
    'id', 'username', 'name', 'email', 'language', 'location',
    'year_of_birth', 'gender', 'level_of_education', 'mailing_address',
    'goals', 'mode', 'is_active', 'date',
]
_INACTIVE_FEATURES = [
    'id', 'username', 'name', 'email', 'mode', 'is_active', 'date',
]


def _learner_queryset(service_accounts, suffixes):
    """Active accounts that represent actual people (excludes staff/service accounts)."""
    from django.contrib.auth import get_user_model
    queryset = get_user_model().objects.filter(
        is_active=True, is_staff=False, is_superuser=False,
    ).exclude(username__in=list(service_accounts))
    for suffix in suffixes:
        queryset = queryset.exclude(username__endswith=suffix)
    return queryset


def _active_enrollment_count(org=None):
    """Enrollments whose learner has a StudentModule row, or None if unavailable.

    Returns None (not 0) when courseware is absent from this process (CMS
    context) or its table is missing — "we cannot see activity" and "no
    activity" are different facts.
    """
    try:
        from lms.djangoapps.courseware.models import StudentModule
    except Exception:  # noqa: BLE001 - courseware absent in this process
        return None
    from django.db import DatabaseError
    from django.db.models import Exists, OuterRef

    from common.djangoapps.student.models import CourseEnrollment
    queryset = CourseEnrollment.objects.filter(is_active=True)
    if org:
        queryset = queryset.filter(course__org=org)
    try:
        return queryset.filter(
            Exists(StudentModule.objects.filter(
                student_id=OuterRef('user_id'), course_id=OuterRef('course_id'),
            ))
        ).count()
    except DatabaseError:
        return None


def reporting_summary_counts(*, this_month, previous_month, now,
                             service_accounts, suffixes, org=None):
    """Cheap headline counts for the KPI row. Returns a dict of ints (+ maybe None).

    ``org`` scopes the course and enrollment figures only. Learner and
    registration counts are always platform-wide by design: Open edX accounts
    are not owned by an organization, so there is no correct way to attribute a
    learner to one org. A future org-scoped dashboard must source those two
    figures differently (e.g. via enrollment in the org's courses).
    """
    from django.db.models import Q

    from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
    learners = _learner_queryset(service_accounts, suffixes)
    courses = CourseOverview.objects.all()
    if org:
        courses = courses.filter(org=org)
    running = Q(start__lte=now) & (Q(end__isnull=True) | Q(end__gte=now))
    return {
        'total_learners': learners.count(),
        'registrations_this_month': learners.filter(date_joined__gte=this_month).count(),
        'registrations_previous_month': learners.filter(
            date_joined__gte=previous_month, date_joined__lt=this_month,
        ).count(),
        'total_courses': courses.count(),
        'running_courses': courses.filter(running).count(),
        'active_enrollments': _active_enrollment_count(org),
    }


def _month_counts(queryset, date_field, start):
    """Group a queryset by month on ``date_field`` from ``start``: ``{'YYYY-MM': int}``."""
    from django.db.models import Count
    from django.db.models.functions import TruncMonth
    rows = (
        queryset.filter(**{f'{date_field}__gte': start})
        .annotate(period=TruncMonth(date_field))
        .values('period')
        .annotate(value=Count('pk'))
    )
    return {row['period'].strftime('%Y-%m'): row['value'] for row in rows if row['period']}


def reporting_enrollment_month_counts(*, start, org=None):
    """Active-enrollment counts bucketed by creation month: ``{'YYYY-MM': int}``."""
    from common.djangoapps.student.models import CourseEnrollment
    queryset = CourseEnrollment.objects.filter(is_active=True)
    if org:
        queryset = queryset.filter(course__org=org)
    return _month_counts(queryset, 'created', start)


def reporting_registration_month_counts(*, start, service_accounts, suffixes, org=None):
    """Learner-registration counts bucketed by join month: ``{'YYYY-MM': int}``.

    Always platform-wide: ``org`` is accepted for call-site symmetry but not
    applied, because learners are not owned by an org (see
    ``reporting_summary_counts``).
    """
    return _month_counts(_learner_queryset(service_accounts, suffixes), 'date_joined', start)


def reporting_course_lifecycle_counts(*, now, org=None):
    """Mutually exclusive course-run state counts (no_dates/upcoming/running/ended)."""
    from django.db.models import Q

    from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
    courses = CourseOverview.objects.all()
    if org:
        courses = courses.filter(org=org)
    running = Q(start__lte=now) & (Q(end__isnull=True) | Q(end__gte=now))
    return {
        'no_dates': courses.filter(start__isnull=True).count(),
        'upcoming': courses.filter(start__gt=now).count(),
        'running': courses.filter(running).count(),
        'ended': courses.filter(start__lte=now, end__lt=now).count(),
    }


def reporting_course_rows(*, search, org, ordering, limit, offset, now):
    """One page of annotated course runs. Returns ``{'count': int, 'results': [dict]}``."""
    from django.db.models import Count, Q

    from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
    valid_orderings = {
        'display_name', '-display_name', 'start', '-start', 'end', '-end',
        'enrollment_count', '-enrollment_count', 'org', '-org',
    }
    queryset = CourseOverview.objects.annotate(
        enrollment_count=Count('courseenrollment', filter=Q(courseenrollment__is_active=True)),
        unenrolled_count=Count('courseenrollment', filter=Q(courseenrollment__is_active=False)),
    )
    if search:
        queryset = queryset.filter(
            Q(display_name__icontains=search)
            | Q(id__icontains=search)
            | Q(org__icontains=search)
        )
    if org:
        queryset = queryset.filter(org=org)
    queryset = queryset.order_by(ordering if ordering in valid_orderings else 'display_name')

    total = queryset.count()
    rows = []
    for course in queryset[offset:offset + limit]:
        if course.start is None:
            state = 'no_dates'
        elif course.start > now:
            state = 'upcoming'
        elif course.end and course.end < now:
            state = 'ended'
        else:
            state = 'running'
        rows.append({
            'course_id': str(course.id),
            'display_name': course.display_name or str(course.id),
            'org': course.org,
            'enrollment_count': course.enrollment_count,
            'unenrolled_count': course.unenrolled_count,
            'start': course.start.isoformat() if course.start else None,
            'end': course.end.isoformat() if course.end else None,
            'lifecycle_state': state,
        })
    return {'count': total, 'results': rows}


def submit_instructor_report(request, course_key, report_type):
    """Queue an async instructor report via the platform task API. Returns task_id (str).

    Reuses ``lms.djangoapps.instructor_task.api`` — the same machinery the
    instructor dashboard uses — so report generation, storage and download
    links behave identically to the platform's own report tools. Raises on
    submission failure (the view maps AlreadyRunning -> 400).
    """
    from lms.djangoapps.instructor_task import api as task_api
    dispatch = {
        'grade_csv': lambda: task_api.submit_calculate_grades_csv(request, course_key),
        'profile_info': lambda: task_api.submit_calculate_students_features_csv(
            request, course_key, _STUDENT_FEATURES),
        'problem_grade': lambda: task_api.submit_problem_grade_report(request, course_key),
        'may_enroll': lambda: task_api.submit_calculate_may_enroll_csv(
            request, course_key, _STUDENT_FEATURES),
        'inactive_learner': lambda: task_api.submit_calculate_inactive_enrolled_students_csv(
            request, course_key, _INACTIVE_FEATURES),
        'survey': lambda: task_api.submit_course_survey_report(request, course_key),
        'proctored_exam': lambda: task_api.submit_proctored_exam_results_report(request, course_key),
        'ora_data': lambda: task_api.submit_export_ora2_data(request, course_key),
        'ora_summary': lambda: task_api.submit_export_ora2_summary(request, course_key),
        'ora_submission_archive': lambda: task_api.submit_export_ora2_submission_files(
            request, course_key),
        'anon_ids': lambda: task_api.generate_anonymous_ids(request, course_key),
    }
    return dispatch[report_type]().task_id


def report_tasks(course_key, task_types, limit):
    """Recent InstructorTask rows for the given task types. Returns ``[dict]`` (primitives)."""
    import json as _json

    from lms.djangoapps.instructor_task.models import InstructorTask
    tasks = (
        InstructorTask.objects
        .filter(course_id=course_key, task_type__in=list(task_types))
        .order_by('-created')[:limit]
    )
    out = []
    for task in tasks:
        parsed = {}
        if task.task_output:
            try:
                candidate = _json.loads(task.task_output)
                if isinstance(candidate, dict):
                    parsed = candidate
            except (ValueError, TypeError):
                pass
        out.append({
            'task_id': task.task_id,
            'task_type': task.task_type,
            'state': task.task_state,
            'created': task.created.isoformat(),
            'modified': task.updated.isoformat() if task.updated is not None else None,
            'succeeded': parsed.get('succeeded'),
            'failed': parsed.get('failed'),
            'total': parsed.get('total'),
        })
    return out


def report_store_links(course_key):
    """Fresh ``{filename_key: url}`` from the grades ReportStore, or ``{}`` if unavailable."""
    try:
        from lms.djangoapps.instructor_task.models import ReportStore
        return dict(ReportStore.from_config('GRADES_DOWNLOAD').links_for(course_key))
    except Exception:  # noqa: BLE001 - store misconfigured/unavailable -> no links
        return {}


def course_grading_config(course_key):
    """Grader breakdown + grade cutoffs from the modulestore, or None if absent."""
    from xmodule.modulestore.django import modulestore
    course = modulestore().get_course(course_key)
    if course is None:
        return None
    grader = [
        {
            'type': entry.get('type'),
            'min_count': entry.get('min_count', 0),
            'drop_count': entry.get('drop_count', 0),
            'weight': entry.get('weight', 0),
            'short_label': entry.get('short_label', ''),
        }
        for entry in (course.raw_grader or [])
    ]
    return {'grader': grader, 'grade_cutoffs': course.grade_cutoffs}


def course_certificates(course_key):
    """Issued certificate rows for a course. Returns ``[dict]`` (primitives)."""
    from lms.djangoapps.certificates.models import GeneratedCertificate
    certs = (
        GeneratedCertificate.objects
        .filter(course_id=course_key)
        .select_related('user')
        .order_by('-created_date')
    )
    return [
        {
            'username': cert.user.username,
            'name': cert.name,
            'email': cert.user.email,
            'mode': cert.mode,
            'status': cert.status,
            'grade': cert.grade,
            'created_date': cert.created_date.isoformat() if cert.created_date else None,
            'download_url': cert.download_url or None,
            'verify_uuid': str(cert.verify_uuid) if cert.verify_uuid else None,
        }
        for cert in certs
    ]
