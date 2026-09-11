"""Tests for the reporting API (analytics + per-course report exports).

Two layers:

* Pure-Python helpers in ``admin_portal.reporting`` are tested directly (no
  mocks) — the interesting logic (month windowing, zero-fill, delta math,
  download-URL matching) lives here by design.
* The API views are tested with every edx-platform read patched at the
  ``edxapp`` seam (the single mock point), so the suite runs standalone without
  edx-platform installed. We assert the gate, response shapes and passthrough.
"""
from datetime import datetime, timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from admin_portal import edxapp
from admin_portal.reporting import analytics
from admin_portal.reporting import courses as courses_service

User = get_user_model()


# ---------------------------------------------------------------------------
# Pure helpers (no mocks, no DB)
# ---------------------------------------------------------------------------

class WindowHelperTests(SimpleTestCase):
    def test_window_start_gives_exactly_n_buckets(self):
        now = datetime(2026, 8, 15, 9, 30, tzinfo=dt_timezone.utc)
        start = analytics.window_start(12, now)
        # 12 whole buckets including August 2026 -> starts September 2025.
        self.assertEqual((start.year, start.month, start.day), (2025, 9, 1))
        self.assertEqual((start.hour, start.minute, start.second), (0, 0, 0))

    def test_window_start_single_month(self):
        now = datetime(2026, 1, 20, tzinfo=dt_timezone.utc)
        start = analytics.window_start(1, now)
        self.assertEqual((start.year, start.month, start.day), (2026, 1, 1))

    def test_clamp_months(self):
        self.assertEqual(analytics.clamp_months(0), 1)
        self.assertEqual(analytics.clamp_months(99), 24)
        self.assertEqual(analytics.clamp_months('7'), 7)
        self.assertEqual(analytics.clamp_months('nonsense'), 12)
        self.assertEqual(analytics.clamp_months(None), 12)

    def test_delta_percentage(self):
        self.assertIsNone(analytics._delta_percentage(5, 0))
        self.assertEqual(analytics._delta_percentage(150, 100), 50.0)
        self.assertEqual(analytics._delta_percentage(50, 100), -50.0)

    def test_dense_series_zero_fills(self):
        now = datetime(2026, 3, 10, tzinfo=dt_timezone.utc)
        start = analytics.window_start(3, now)  # 2026-01
        series = analytics._dense_series({'2026-02': 4}, start, now)
        self.assertEqual(series, [
            {'period': '2026-01', 'value': 0},
            {'period': '2026-02', 'value': 4},
            {'period': '2026-03', 'value': 0},
        ])


class DownloadUrlMatchTests(SimpleTestCase):
    ISO = '2026-05-04T09:07:00+00:00'  # -> 2026-05-04-0907

    def _abs(self, url):
        return f'https://lms.test{url}'

    def test_matches_by_keyword_and_minute(self):
        links = {'Org_Course_grade_report_2026-05-04-0907.csv': '/media/g.csv'}
        url = courses_service.find_download_url(
            'grade_course', self.ISO, links, 'grade_report', self._abs)
        self.assertEqual(url, 'https://lms.test/media/g.csv')

    def test_grade_report_excludes_problem_grade_collision(self):
        links = {'Org_problem_grade_report_2026-05-04-0907.csv': '/media/p.csv'}
        url = courses_service.find_download_url(
            'grade_course', self.ISO, links, 'grade_report', self._abs)
        self.assertIsNone(url)

    def test_matches_when_worker_starts_a_few_minutes_after_queueing(self):
        # The filename timestamp is stamped when the Celery worker starts the
        # task, not when it was queued (task_created_iso) — a short delay
        # crossing a minute boundary must still match.
        links = {'Org_grade_report_2026-05-04-0910.csv': '/media/g.csv'}
        url = courses_service.find_download_url(
            'grade_course', self.ISO, links, 'grade_report', self._abs)
        self.assertEqual(url, 'https://lms.test/media/g.csv')

    def test_no_match_before_task_was_created(self):
        links = {'Org_grade_report_2026-05-04-0900.csv': '/media/g.csv'}
        url = courses_service.find_download_url(
            'grade_course', self.ISO, links, 'grade_report', self._abs)
        self.assertIsNone(url)

    def test_no_match_beyond_max_queue_delay(self):
        links = {'Org_grade_report_2026-05-04-1010.csv': '/media/g.csv'}
        url = courses_service.find_download_url(
            'grade_course', self.ISO, links, 'grade_report', self._abs)
        self.assertIsNone(url)

    def test_prefers_earliest_match_over_a_later_unrelated_report(self):
        links = {
            'Org_grade_report_2026-05-04-0907.csv': '/media/first.csv',
            'Org_grade_report_2026-05-04-0930.csv': '/media/second.csv',
        }
        url = courses_service.find_download_url(
            'grade_course', self.ISO, links, 'grade_report', self._abs)
        self.assertEqual(url, 'https://lms.test/media/first.csv')

    def test_absolute_url_left_untouched(self):
        links = {'grade_report_2026-05-04-0907.csv': 'https://s3/g.csv'}
        url = courses_service.find_download_url(
            'grade_course', self.ISO, links, 'grade_report', self._abs)
        self.assertEqual(url, 'https://s3/g.csv')

    def test_none_keyword_returns_none(self):
        self.assertIsNone(courses_service.find_download_url('x', self.ISO, {}, None, self._abs))


# ---------------------------------------------------------------------------
# Access gate
# ---------------------------------------------------------------------------

class ReportingGateTests(APITestCase):
    def test_anonymous_summary_is_forbidden(self):
        self.assertEqual(
            self.client.get(reverse('admin_portal:v1:reporting-summary')).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_non_admin_summary_is_forbidden(self):
        user = User.objects.create_user('nobody', email='n@e.com', password='pw')
        self.client.force_login(user)
        self.assertEqual(
            self.client.get(reverse('admin_portal:v1:reporting-summary')).status_code,
            status.HTTP_403_FORBIDDEN,
        )


# ---------------------------------------------------------------------------
# Admin-authenticated endpoint tests (seams mocked)
# ---------------------------------------------------------------------------

class ReportingAdminTestCase(APITestCase):
    def setUp(self):
        # Analytics responses are cached server-side; clear between tests so a
        # prior test's payload can't satisfy a later request on the same key.
        cache.clear()
        self.admin = User.objects.create_user('admin', email='admin@e.com', password='pw')
        self.admin.groups.add(Group.objects.get(name='edl_admin'))
        self.client.force_login(self.admin)


class SummaryViewTests(ReportingAdminTestCase):
    def test_summary_shape_and_generated_at(self):
        raw = {
            'total_learners': 100, 'registrations_this_month': 12,
            'registrations_previous_month': 8, 'total_courses': 20,
            'running_courses': 15, 'active_enrollments': 42,
        }
        with mock.patch.object(edxapp, 'reporting_summary_counts', return_value=raw):
            response = self.client.get(reverse('admin_portal:v1:reporting-summary'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_learners'], 100)
        self.assertEqual(response.data['new_registrations_this_month'], 12)
        self.assertEqual(response.data['new_registrations_previous_month'], 8)
        self.assertEqual(response.data['new_registrations_delta_pct'], 50.0)
        self.assertEqual(response.data['running_courses'], 15)
        self.assertIn('generated_at', response.data)
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_active_enrollments_may_be_null(self):
        raw = {
            'total_learners': 1, 'registrations_this_month': 0,
            'registrations_previous_month': 0, 'total_courses': 0,
            'running_courses': 0, 'active_enrollments': None,
        }
        with mock.patch.object(edxapp, 'reporting_summary_counts', return_value=raw):
            response = self.client.get(reverse('admin_portal:v1:reporting-summary'))
        self.assertIsNone(response.data['active_enrollments'])
        self.assertIsNone(response.data['new_registrations_delta_pct'])


class TrendsViewTests(ReportingAdminTestCase):
    def test_trends_zero_fills_and_reports_months(self):
        with mock.patch.object(edxapp, 'reporting_enrollment_month_counts', return_value={}), \
             mock.patch.object(edxapp, 'reporting_registration_month_counts', return_value={}):
            response = self.client.get(
                reverse('admin_portal:v1:reporting-trends'), {'months': 6})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['months'], 6)
        self.assertEqual(len(response.data['enrollments']), 6)
        self.assertTrue(all(point['value'] == 0 for point in response.data['enrollments']))
        self.assertIn('generated_at', response.data)

    def test_out_of_range_months_is_400(self):
        response = self.client.get(
            reverse('admin_portal:v1:reporting-trends'), {'months': 999})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class BreakdownsViewTests(ReportingAdminTestCase):
    def test_breakdowns_passes_through_lifecycle(self):
        lifecycle = {'no_dates': 1, 'upcoming': 2, 'running': 3, 'ended': 4}
        with mock.patch.object(edxapp, 'reporting_course_lifecycle_counts', return_value=lifecycle):
            response = self.client.get(reverse('admin_portal:v1:reporting-breakdowns'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['course_lifecycle'], lifecycle)


class CourseListViewTests(ReportingAdminTestCase):
    def test_passthrough_and_page_offset(self):
        payload = {'count': 3, 'results': [{'course_id': 'course-v1:A+B+C'}]}
        with mock.patch.object(edxapp, 'reporting_course_rows', return_value=payload) as m:
            response = self.client.get(
                reverse('admin_portal:v1:reporting-courses'), {'page': 2, 'search': 'math'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)
        _, kwargs = m.call_args
        self.assertEqual(kwargs['offset'], 25)
        self.assertEqual(kwargs['limit'], 25)
        self.assertEqual(kwargs['search'], 'math')


class ReportTriggerViewTests(ReportingAdminTestCase):
    COURSE = 'course-v1:Org+Course+Run'

    def _url(self):
        return reverse('admin_portal:v1:reporting-course-trigger', args=[self.COURSE])

    def test_trigger_returns_202(self):
        with mock.patch.object(edxapp, 'parse_course_key', side_effect=lambda c: c), \
             mock.patch.object(edxapp, 'submit_instructor_report', return_value='task-1') as m:
            response = self.client.post(self._url(), {'report_type': 'grade_csv'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data, {'task_id': 'task-1', 'report_type': 'grade_csv'})
        # Seam called as submit_instructor_report(request, course_key, report_type).
        self.assertEqual(m.call_args.args[2], 'grade_csv')

    def test_unknown_report_type_is_400(self):
        response = self.client.post(self._url(), {'report_type': 'nope'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_already_running_is_400(self):
        class AlreadyRunningError(Exception):
            pass

        with mock.patch.object(edxapp, 'parse_course_key', side_effect=lambda c: c), \
             mock.patch.object(edxapp, 'submit_instructor_report',
                               side_effect=AlreadyRunningError('busy')):
            response = self.client.post(self._url(), {'report_type': 'grade_csv'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submission_failure_is_500(self):
        with mock.patch.object(edxapp, 'parse_course_key', side_effect=lambda c: c), \
             mock.patch.object(edxapp, 'submit_instructor_report',
                               side_effect=RuntimeError('celery down')):
            response = self.client.post(self._url(), {'report_type': 'grade_csv'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


class ReportDownloadsViewTests(ReportingAdminTestCase):
    COURSE = 'course-v1:Org+Course+Run'

    def test_downloads_merge_links_and_labels(self):
        tasks = [{
            'task_id': 't1', 'task_type': 'grade_course', 'state': 'SUCCESS',
            'created': '2026-05-04T09:07:00+00:00', 'modified': None,
            'succeeded': 3, 'failed': 0, 'total': 3,
        }]
        links = {'Org_grade_report_2026-05-04-0907.csv': 'https://s3/g.csv'}
        url = reverse('admin_portal:v1:reporting-course-downloads', args=[self.COURSE])
        with mock.patch.object(edxapp, 'parse_course_key', side_effect=lambda c: c), \
             mock.patch.object(edxapp, 'report_tasks', return_value=tasks), \
             mock.patch.object(edxapp, 'report_store_links', return_value=links):
            response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.data['results'][0]
        self.assertEqual(row['report_type'], 'grade_csv')
        self.assertEqual(row['report_label'], 'Grade Report')
        self.assertEqual(row['download_url'], 'https://s3/g.csv')


class CertificatesViewTests(ReportingAdminTestCase):
    COURSE = 'course-v1:Org+Course+Run'

    def test_certificates_count_and_rows(self):
        rows = [{'username': 'u1', 'grade': '0.9', 'status': 'downloadable'}]
        url = reverse('admin_portal:v1:reporting-course-certificates', args=[self.COURSE])
        with mock.patch.object(edxapp, 'parse_course_key', side_effect=lambda c: c), \
             mock.patch.object(edxapp, 'course_certificates', return_value=rows):
            response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['username'], 'u1')


class GradingConfigViewTests(ReportingAdminTestCase):
    COURSE = 'course-v1:Org+Course+Run'

    def test_grading_config_ok(self):
        cfg = {'grader': [{'type': 'Homework'}], 'grade_cutoffs': {'Pass': 0.5}}
        url = reverse('admin_portal:v1:reporting-course-grading-config', args=[self.COURSE])
        with mock.patch.object(edxapp, 'parse_course_key', side_effect=lambda c: c), \
             mock.patch.object(edxapp, 'course_grading_config', return_value=cfg):
            response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['course_id'], self.COURSE)
        self.assertEqual(response.data['grade_cutoffs'], {'Pass': 0.5})

    def test_missing_course_is_404(self):
        url = reverse('admin_portal:v1:reporting-course-grading-config', args=[self.COURSE])
        with mock.patch.object(edxapp, 'parse_course_key', side_effect=lambda c: c), \
             mock.patch.object(edxapp, 'course_grading_config', return_value=None):
            response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
