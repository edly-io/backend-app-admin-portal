"""Course reporting composition helpers (pure Python).

The download-URL matcher operates on the ``{filename_key: url}`` dict the edxapp
seam returns, so it holds no platform import and is unit-testable directly.
"""
import re
from datetime import datetime

_FILENAME_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2}-\d{4})")


def find_download_url(task_type, task_created_iso, links, keyword, build_absolute):
    """Find the ReportStore download URL for a completed task.

    task_output never carries the filename, so we match by (1) the filename
    keyword for the task type and (2) the ``YYYY-MM-DD-HHMM`` timestamp in the
    filename matching the task's creation minute. When several files share a
    minute we prefer the shortest key (no random suffix). Relative URLs (local
    filesystem store) are made absolute via ``build_absolute``.

    Args:
        task_type: unused directly; kept for call-site symmetry / future use.
        task_created_iso: ISO-8601 string of the task's ``created`` timestamp.
        links: ``{filename_key: url}`` from the ReportStore seam.
        keyword: the filename keyword for this task type (may be None).
        build_absolute: callable turning a relative URL absolute (request.build_absolute_uri).
    """
    if not keyword:
        return None

    minute = datetime.fromisoformat(task_created_iso).strftime("%Y-%m-%d-%H%M")
    best_key = None
    best_url = None
    for key, url in links.items():
        if keyword not in key:
            continue
        # "grade_report" is a substring of "problem_grade_report" — exclude it.
        if keyword == "grade_report" and "problem_grade_report" in key:
            continue
        match = _FILENAME_TS_RE.search(key)
        if not match or match.group(1) != minute:
            continue
        if best_key is None or len(key) < len(best_key):
            best_key = key
            best_url = url

    if best_url and best_url.startswith("/"):
        best_url = build_absolute(best_url)
    return best_url
