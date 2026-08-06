"""Regression coverage for ``edxapp.process_enrollment_batch`` (EDL-8/9).

The enroll/unenroll batch runs entirely against edx-platform primitives that
are absent from the standalone test env, so the rest of the suite mocks the
``edxapp`` seam and never exercises this code. That gap let a bad import
(``lms.djangoapps.instructor.utils.process_student_enrollment_batch``, which
does not exist in the target release) reach production and 500 every enroll.

Here we inject lightweight stubs for the platform modules the function imports,
then drive it end to end: we assert it loops over identifiers, resolves each,
writes one audit row per success, and returns the aggregate result shape the
API/MFE depend on.
"""
import sys
import types
from contextlib import contextmanager

from django.contrib.auth import get_user_model
from django.test import TestCase

from admin_portal import edxapp

User = get_user_model()


class _FakeState:
    """Stand-in for the platform's CourseEnrollmentState (its .to_dict())."""

    def __init__(self, *, user, enrollment, allowed):
        self._d = {'user': user, 'enrollment': enrollment, 'allowed': allowed, 'auto_enroll': False}

    def to_dict(self):
        return dict(self._d)


def _make_module(dotted_name, **attrs):
    mod = types.ModuleType(dotted_name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


@contextmanager
def _platform_stubs(*, known_email, audit_calls):
    """Register fake edx-platform modules for the duration of a call."""
    known_user = User(username='known', email=known_email)

    def get_user_by_username_or_email(identifier):
        if identifier in (known_email, 'known'):
            return known_user
        raise User.DoesNotExist()

    class ManualEnrollmentAudit:
        @staticmethod
        def create_manual_enrollment_audit(actor, email, transition, reason, enrollment_obj):
            audit_calls.append((email, transition))

    class CourseEnrollment:
        @staticmethod
        def get_enrollment(user, course_key):
            return None

    class EnrollStatusChange:
        enroll = 'enroll'
        unenroll = 'unenroll'

    def enroll_email(course_key, email, auto_enroll, email_students, email_params, language=None):
        before = _FakeState(user=True, enrollment=False, allowed=False)
        after = _FakeState(user=True, enrollment=True, allowed=False)
        return before, after, object()

    def unenroll_email(course_key, email, email_students, email_params, language=None):
        before = _FakeState(user=True, enrollment=True, allowed=False)
        after = _FakeState(user=True, enrollment=False, allowed=False)
        return before, after

    student_models = _make_module(
        'common.djangoapps.student.models',
        ALLOWEDTOENROLL_TO_ENROLLED='a2e', ALLOWEDTOENROLL_TO_UNENROLLED='a2u',
        DEFAULT_TRANSITION_STATE='default', ENROLLED_TO_ENROLLED='e2e',
        ENROLLED_TO_UNENROLLED='e2u', UNENROLLED_TO_ALLOWEDTOENROLL='u2a',
        UNENROLLED_TO_ENROLLED='u2e', UNENROLLED_TO_UNENROLLED='u2u',
        CourseEnrollment=CourseEnrollment, EnrollStatusChange=EnrollStatusChange,
        ManualEnrollmentAudit=ManualEnrollmentAudit,
        get_user_by_username_or_email=get_user_by_username_or_email,
    )
    instructor_enrollment = _make_module(
        'lms.djangoapps.instructor.enrollment',
        enroll_email=enroll_email, unenroll_email=unenroll_email,
        get_email_params=lambda course, auto_enroll, secure=True: {},
        get_user_email_language=lambda user: 'en',
    )
    courses = _make_module('openedx.core.lib.courses', get_course_by_id=lambda ck: object())

    # Register the leaves plus every parent package so `from a.b.c import x` resolves.
    modules = {
        'common': _make_module('common'),
        'common.djangoapps': _make_module('common.djangoapps'),
        'common.djangoapps.student': _make_module('common.djangoapps.student'),
        'common.djangoapps.student.models': student_models,
        'lms': _make_module('lms'),
        'lms.djangoapps': _make_module('lms.djangoapps'),
        'lms.djangoapps.instructor': _make_module('lms.djangoapps.instructor'),
        'lms.djangoapps.instructor.enrollment': instructor_enrollment,
        'openedx': _make_module('openedx'),
        'openedx.core': _make_module('openedx.core'),
        'openedx.core.lib': _make_module('openedx.core.lib'),
        'openedx.core.lib.courses': courses,
    }
    saved = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)
    try:
        yield
    finally:
        for name, prev in saved.items():
            if prev is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prev


class EnrollmentBatchTests(TestCase):
    """Drive process_enrollment_batch against stubbed platform primitives."""

    def test_enroll_batch_mixed_results(self):
        audit_calls = []
        with _platform_stubs(known_email='known@example.com', audit_calls=audit_calls):
            result = edxapp.process_enrollment_batch(
                request_user=User(username='admin'),
                course_key='course-v1:Org+C+R',
                action='enroll',
                identifiers=['known@example.com', 'not-an-email'],
                auto_enroll=False,
                email_students=False,
                reason='',
                secure=True,
            )

        self.assertEqual(result['action'], 'enroll')
        self.assertEqual(result['total_students'], 2)
        self.assertEqual(result['successful_operations'], 1)
        self.assertEqual(result['failed_operations'], 1)

        ok, bad = result['results']
        self.assertEqual(ok['identifier'], 'known@example.com')
        self.assertTrue(ok['success'])
        self.assertEqual(ok['state_transition'], 'u2e')  # UNENROLLED_TO_ENROLLED
        self.assertEqual(bad['identifier'], 'not-an-email')
        self.assertFalse(bad['success'])
        self.assertTrue(bad['invalidIdentifier'])

        # Exactly one audit row — only the successful enrollment.
        self.assertEqual(audit_calls, [('known@example.com', 'u2e')])

    def test_unenroll_batch_success(self):
        audit_calls = []
        with _platform_stubs(known_email='known@example.com', audit_calls=audit_calls):
            result = edxapp.process_enrollment_batch(
                request_user=User(username='admin'),
                course_key='course-v1:Org+C+R',
                action='unenroll',
                identifiers=['known@example.com'],
                auto_enroll=False,
                email_students=False,
                reason='cleanup',
                secure=True,
            )

        self.assertEqual(result['successful_operations'], 1)
        self.assertEqual(result['results'][0]['state_transition'], 'e2u')  # ENROLLED_TO_UNENROLLED
        self.assertEqual(audit_calls, [('known@example.com', 'e2u')])
