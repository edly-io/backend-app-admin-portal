"""v1 URL routes for the admin_portal plugin."""
from django.urls import path, re_path

from admin_portal.rest_api.v1 import reporting_views as rv
from admin_portal.rest_api.v1 import views

app_name = 'v1'

# Course keys contain ':' and '+' but never '/', so a `<str:>`/path converter
# would either reject or over-match. An explicit `[^/]+` class keeps the key
# intact and still terminates at the first '/'. The `reporting/courses/` prefix
# is baked into each pattern because this urlpatterns list is flat (not a
# nested include).
_COURSE = r'(?P<course_id>[^/]+)'

urlpatterns = [
    path('health/', views.HealthView.as_view(), name='health'),
    path('me/', views.MeView.as_view(), name='me'),
    path('users/', views.UsersView.as_view(), name='users'),
    path('users/<str:username>/deactivate/', views.DeactivateUserView.as_view(), name='user-deactivate'),
    path('users/<str:username>/reactivate/', views.ReactivateUserView.as_view(), name='user-reactivate'),
    path('enrollments/enroll/', views.EnrollView.as_view(), name='enroll'),
    path('enrollments/unenroll/', views.UnenrollView.as_view(), name='unenroll'),
    path('roles/', views.RolesView.as_view(), name='roles'),

    # Reporting — analytics
    path('reporting/summary/', rv.ReportingSummaryView.as_view(), name='reporting-summary'),
    path('reporting/trends/', rv.ReportingTrendsView.as_view(), name='reporting-trends'),
    path('reporting/breakdowns/', rv.ReportingBreakdownsView.as_view(), name='reporting-breakdowns'),

    # Reporting — courses + per-course report exports
    path('reporting/courses/', rv.ReportingCourseListView.as_view(), name='reporting-courses'),
    re_path(rf'^reporting/courses/{_COURSE}/reports/trigger/$',
            rv.CourseReportTriggerView.as_view(), name='reporting-course-trigger'),
    re_path(rf'^reporting/courses/{_COURSE}/reports/tasks/$',
            rv.CourseReportTasksView.as_view(), name='reporting-course-tasks'),
    re_path(rf'^reporting/courses/{_COURSE}/reports/downloads/$',
            rv.CourseReportDownloadsView.as_view(), name='reporting-course-downloads'),
    re_path(rf'^reporting/courses/{_COURSE}/reports/grading-config/$',
            rv.CourseGradingConfigView.as_view(), name='reporting-course-grading-config'),
    re_path(rf'^reporting/courses/{_COURSE}/reports/certificates/$',
            rv.CourseCertificatesView.as_view(), name='reporting-course-certificates'),
]
