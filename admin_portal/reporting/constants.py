"""Constants for the reporting feature (no platform imports)."""

DEFAULT_TREND_MONTHS = 12
MAX_TREND_MONTHS = 24
CACHE_PREFIX = "admin_portal_reporting"
CACHE_TTL_SECONDS = 300

# Default accounts excluded from learner counts (service/worker accounts).
DEFAULT_SERVICE_ACCOUNT_USERNAMES = frozenset({
    "app", "cms", "lms", "credentials", "discovery", "ecommerce",
    "insights", "registrar", "login_service_user",
})
SERVICE_ACCOUNT_SUFFIXES = ("_worker", "_service_user")

# Public report_type slug -> InstructorTask.task_type string.
REPORT_TYPES = {
    "grade_csv": "grade_course",
    "problem_grade": "grade_problems",
    "profile_info": "profile_info_csv",
    "may_enroll": "may_enroll_info_csv",
    "inactive_learner": "inactive_enrolled_students_info_csv",
    "survey": "course_survey_report",
    "proctored_exam": "proctored_exam_results_report",
    "ora_data": "export_ora2_data",
    "ora_summary": "export_ora2_summary",
    "ora_submission_archive": "export_ora2_submission_files",
    "anon_ids": "generate_anonymous_ids_for_course",
}
REPORT_LABELS = {
    "grade_csv": "Grade Report",
    "problem_grade": "Problem Grade Report",
    "profile_info": "Profile Information",
    "may_enroll": "Learners Who Can Enroll",
    "inactive_learner": "Learners, Account Not Activated",
    "survey": "Survey Results",
    "proctored_exam": "Proctored Exam Results",
    "ora_data": "ORA Data Report",
    "ora_summary": "ORA Summary Report",
    "ora_submission_archive": "ORA Submission Files Archive",
    "anon_ids": "Student Anonymized IDs",
}
# task_type -> filename keyword (to match InstructorTask rows to ReportStore files).
TASK_TYPE_FILENAME_KEYWORD = {
    "grade_course": "grade_report",
    "grade_problems": "problem_grade_report",
    "profile_info_csv": "profile_info",
    "may_enroll_info_csv": "may_enroll_info",
    "inactive_enrolled_students_info_csv": "inactive_enrolled_students",
    "course_survey_report": "course_survey_results",
    "proctored_exam_results_report": "proctored_exam_results_report",
    "export_ora2_data": "ORA_data",
    "export_ora2_summary": "ORA_summary",
    "export_ora2_submission_files": "submission_files",
    "generate_anonymous_ids_for_course": "anonymized_ids",
}
TASK_TYPE_TO_SLUG = {v: k for k, v in REPORT_TYPES.items()}
