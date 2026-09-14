"""Course reporting composition helpers (pure Python).

The download-URL matcher operates on the ``{filename_key: url}`` dict the edxapp
seam returns, so it holds no platform import and is unit-testable directly.
"""
import re
from datetime import datetime, timedelta, timezone as dt_timezone

_FILENAME_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2}-\d{4})")

# Filenames are timestamped in UTC when the worker starts executing the task,
# not when the task was queued (task_created_iso) — bound how long a queue
# delay we'll tolerate when matching, so we don't ever pick up an unrelated
# later report of the same type/keyword for the same course.
_MAX_QUEUE_DELAY = timedelta(hours=1)


def find_download_url(task_type, task_created_iso, links, keyword, build_absolute):
    """Find the ReportStore download URL for a completed task.

    task_output never carries the filename, so we match by (1) the filename
    keyword for the task type and (2) the ``YYYY-MM-DD-HHMM`` timestamp in the
    filename. The filename timestamp is stamped when the Celery worker starts
    executing the task, not when it was queued (``task_created_iso``), so a
    task that sits in the queue across a minute boundary would never match on
    an exact-minute comparison. Instead we take the earliest matching filename
    timestamped at or after the task's creation minute (a report can't have
    been generated before its task was created). When several candidate files
    share a timestamp we prefer the shortest key (no random suffix). Relative
    URLs (local filesystem store) are made absolute via ``build_absolute``.

    Args:
        task_type: unused directly; kept for call-site symmetry / future use.
        task_created_iso: ISO-8601 string of the task's ``created`` timestamp.
        links: ``{filename_key: url}`` from the ReportStore seam.
        keyword: the filename keyword for this task type (may be None).
        build_absolute: callable turning a relative URL absolute (request.build_absolute_uri).
    """
    if not keyword:
        return None

    created = datetime.fromisoformat(task_created_iso)
    if created.tzinfo is not None:
        created = created.astimezone(dt_timezone.utc).replace(tzinfo=None)
    created = created.replace(second=0, microsecond=0)

    best_key = None
    best_url = None
    best_delta = None
    for key, url in links.items():
        if keyword not in key:
            continue
        # "grade_report" is a substring of "problem_grade_report" — exclude it.
        if keyword == "grade_report" and "problem_grade_report" in key:
            continue
        match = _FILENAME_TS_RE.search(key)
        if not match:
            continue
        try:
            candidate = datetime.strptime(match.group(1), "%Y-%m-%d-%H%M")
        except ValueError:
            continue
        delta = candidate - created
        if delta < timedelta(0) or delta > _MAX_QUEUE_DELAY:
            continue
        is_better = (
            best_delta is None
            or delta < best_delta
            or (delta == best_delta and len(key) < len(best_key))
        )
        if is_better:
            best_key = key
            best_url = url
            best_delta = delta

    if best_url and best_url.startswith("/"):
        best_url = build_absolute(best_url)
    return best_url
