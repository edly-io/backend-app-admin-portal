"""Reporting API views.

Analytics (summary / trends / breakdowns) plus per-course report exports. Every
view subclasses ``AdminPortalAPIView`` so the EDL-admin gate and the
``Cache-Control: no-store`` header apply automatically. Views are thin: they
validate input, call an edxapp seam or a reporting service, and shape a
Response. All aggregation/query logic lives in ``admin_portal.edxapp`` (platform
reads, returns primitives) and ``admin_portal.reporting.*`` (pure-Python
composition).
"""
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.response import Response

from admin_portal import edxapp
from admin_portal.reporting import analytics
from admin_portal.reporting import courses as courses_service
from admin_portal.reporting.constants import (
    DEFAULT_TREND_MONTHS,
    REPORT_LABELS,
    REPORT_TYPES,
    TASK_TYPE_FILENAME_KEYWORD,
    TASK_TYPE_TO_SLUG,
)
from admin_portal.rest_api.base import AdminPortalAPIView
from admin_portal.rest_api.v1.serializers import ReportingTrendsQuerySerializer

PAGE_SIZE = 25


def _org(request):
    """Return the requested org short_name, or None for platform-wide."""
    return (request.query_params.get('org') or '').strip() or None


def _force_refresh(request):
    """True when the caller explicitly requests a cache bypass."""
    return request.query_params.get('force_refresh') in ('1', 'true', 'True')


def _validate_course(course_id):
    """Return (course_key, None) on success, or (None, Response(400)) on a bad key."""
    try:
        return edxapp.parse_course_key(course_id), None
    except Exception:  # noqa: BLE001 - InvalidKeyError/ValueError on malformed input
        return None, Response(
            {'detail': f'Invalid course id: {course_id!r}'},
            status=status.HTTP_400_BAD_REQUEST,
        )


class ReportingSummaryView(AdminPortalAPIView):
    """GET reporting/summary/ — the KPI row."""

    def get(self, request):
        org = _org(request)
        payload = analytics.cached(
            'summary', lambda: analytics.get_summary(org),
            force_refresh=_force_refresh(request), org=org,
        )
        return Response(payload)


class ReportingTrendsView(AdminPortalAPIView):
    """GET reporting/trends/?months=12 — bounded monthly series."""

    def get(self, request):
        query = ReportingTrendsQuerySerializer(data=request.query_params)
        if not query.is_valid():
            return Response(query.errors, status=status.HTTP_400_BAD_REQUEST)
        months = query.validated_data.get('months') or DEFAULT_TREND_MONTHS
        org = _org(request)
        payload = analytics.cached(
            'trends', lambda: analytics.get_trends(months, org),
            force_refresh=_force_refresh(request), org=org, months=months,
        )
        return Response(payload)


class ReportingBreakdownsView(AdminPortalAPIView):
    """GET reporting/breakdowns/ — grouped aggregates (lean cut: course lifecycle)."""

    def get(self, request):
        org = _org(request)
        payload = analytics.cached(
            'breakdowns', lambda: analytics.get_breakdowns(org),
            force_refresh=_force_refresh(request), org=org,
        )
        return Response(payload)


class ReportingCourseListView(AdminPortalAPIView):
    """GET reporting/courses/ — paginated, annotated course-run list."""

    def get(self, request):
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
        payload = edxapp.reporting_course_rows(
            search=request.query_params.get('search', '').strip(),
            org=_org(request),
            ordering=request.query_params.get('ordering', 'display_name'),
            limit=PAGE_SIZE,
            offset=(page - 1) * PAGE_SIZE,
            now=timezone.now(),
        )
        return Response(payload)  # {count, results}


@method_decorator(transaction.non_atomic_requests, name='dispatch')
class CourseReportTriggerView(AdminPortalAPIView):
    """POST reporting/courses/<course_id>/reports/trigger/ — queue an async report."""

    def post(self, request, course_id):
        report_type = request.data.get('report_type')
        if report_type not in REPORT_TYPES:
            return Response(
                {'detail': f'Unknown report_type. Valid: {sorted(REPORT_TYPES)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        course_key, err = _validate_course(course_id)
        if err:
            return err
        try:
            task_id = edxapp.submit_instructor_report(request, course_key, report_type)
        except Exception as exc:  # noqa: BLE001 - platform submission errors -> HTTP
            if 'AlreadyRunning' in type(exc).__name__:
                return Response(
                    {'detail': (
                        'A report of this type is already running. '
                        'Wait for it to finish before triggering another.'
                    )},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {'detail': 'Failed to submit report. Check LMS Celery connectivity.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(
            {'task_id': task_id, 'report_type': report_type},
            status=status.HTTP_202_ACCEPTED,
        )


def _rows_with_downloads(request, course_key, task_types):
    """Merge InstructorTask rows with fresh ReportStore download URLs + labels."""
    tasks = edxapp.report_tasks(course_key, task_types, limit=50)
    links = edxapp.report_store_links(course_key)
    rows = []
    for task in tasks:
        slug = TASK_TYPE_TO_SLUG.get(task['task_type'], task['task_type'])
        keyword = TASK_TYPE_FILENAME_KEYWORD.get(task['task_type'])
        task['report_type'] = slug
        task['report_label'] = REPORT_LABELS.get(slug, slug)
        task['download_url'] = courses_service.find_download_url(
            task['task_type'], task['created'], links, keyword, request.build_absolute_uri,
        )
        rows.append(task)
    return rows


class CourseReportDownloadsView(AdminPortalAPIView):
    """GET reporting/courses/<course_id>/reports/downloads/ — all report tasks + links."""

    def get(self, request, course_id):
        course_key, err = _validate_course(course_id)
        if err:
            return err
        return Response(
            {'results': _rows_with_downloads(request, course_key, list(REPORT_TYPES.values()))}
        )


class CourseReportTasksView(AdminPortalAPIView):
    """GET reporting/courses/<course_id>/reports/tasks/?report_type= — one type's tasks."""

    def get(self, request, course_id):
        report_type = request.query_params.get('report_type')
        if report_type not in REPORT_TYPES:
            return Response(
                {'detail': f'Unknown report_type. Valid: {sorted(REPORT_TYPES)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        course_key, err = _validate_course(course_id)
        if err:
            return err
        return Response(
            {'results': _rows_with_downloads(request, course_key, [REPORT_TYPES[report_type]])}
        )


class CourseGradingConfigView(AdminPortalAPIView):
    """GET reporting/courses/<course_id>/reports/grading-config/ — grader + cutoffs."""

    def get(self, request, course_id):
        course_key, err = _validate_course(course_id)
        if err:
            return err
        config = edxapp.course_grading_config(course_key)
        if config is None:
            return Response({'detail': 'Course not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'course_id': course_id, **config})


class CourseCertificatesView(AdminPortalAPIView):
    """GET reporting/courses/<course_id>/reports/certificates/ — issued certificates."""

    def get(self, request, course_id):
        course_key, err = _validate_course(course_id)
        if err:
            return err
        rows = edxapp.course_certificates(course_key)
        return Response({'count': len(rows), 'results': rows})
