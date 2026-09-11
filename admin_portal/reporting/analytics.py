"""Analytics composition. Pure Python: platform reads live in admin_portal.edxapp.

Every function here composes primitives returned by the edxapp seam; nothing in
this module imports an edx-platform model, so it imports and unit-tests
standalone. The pure helpers (window_start, clamp_months, _delta_percentage,
_dense_series) are tested directly; the edxapp seams are mocked in view tests.
"""
import hashlib
import json
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from admin_portal import edxapp
from admin_portal.reporting import constants


def clamp_months(months):
    """Return a sane month count for a trend window (1..MAX_TREND_MONTHS)."""
    try:
        value = int(months)
    except (TypeError, ValueError):
        return constants.DEFAULT_TREND_MONTHS
    return max(1, min(value, constants.MAX_TREND_MONTHS))


def window_start(months, now=None):
    """First day of the month ``months - 1`` back, at midnight.

    Calendar arithmetic (exact across month lengths and year boundaries), so
    window_start(12) always yields exactly 12 whole monthly buckets including
    the current one.
    """
    now = now or timezone.now()
    total_months = now.year * 12 + (now.month - 1) - (months - 1)
    year, month_index = divmod(total_months, 12)
    return now.replace(year=year, month=month_index + 1, day=1,
                       hour=0, minute=0, second=0, microsecond=0)


def _month_bounds(now=None):
    """Return (this_month_start, previous_month_start)."""
    now = now or timezone.now()
    this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    previous_month = (this_month - timedelta(days=1)).replace(day=1)
    return this_month, previous_month


def _delta_percentage(current, previous):
    """Percentage change previous->current, or None when there is no baseline."""
    if not previous:
        return None
    return round(((current - previous) / previous) * 100, 1)


def _dense_series(counts_by_month, start, now=None):
    """Zero-filled ``[{period:'YYYY-MM', value:int}]`` from a ``{'YYYY-MM': int}`` dict."""
    now = now or timezone.now()
    series = []
    cursor = start
    while cursor <= now:
        key = cursor.strftime("%Y-%m")
        series.append({"period": key, "value": counts_by_month.get(key, 0)})
        # Step to the first day of the next month without dateutil.
        cursor = (cursor.replace(day=28) + timedelta(days=7)).replace(day=1)
    return series


def _service_accounts():
    """Usernames excluded from learner counts (settings override or default set)."""
    return frozenset(
        getattr(settings, "ADMIN_PORTAL_ANALYTICS_SERVICE_ACCOUNTS", None)
        or constants.DEFAULT_SERVICE_ACCOUNT_USERNAMES
    )


def get_summary(org=None):
    """The KPI row: cheap counts only, no time bucketing."""
    now = timezone.now()
    this_month, previous_month = _month_bounds(now)
    raw = edxapp.reporting_summary_counts(
        this_month=this_month, previous_month=previous_month,
        now=now, service_accounts=_service_accounts(),
        suffixes=constants.SERVICE_ACCOUNT_SUFFIXES, org=org,
    )
    return {
        "total_learners": raw["total_learners"],
        "new_registrations_this_month": raw["registrations_this_month"],
        "new_registrations_previous_month": raw["registrations_previous_month"],
        "new_registrations_delta_pct": _delta_percentage(
            raw["registrations_this_month"], raw["registrations_previous_month"]),
        "total_courses": raw["total_courses"],
        "running_courses": raw["running_courses"],
        "active_enrollments": raw["active_enrollments"],  # may be None
    }


def get_trends(months=constants.DEFAULT_TREND_MONTHS, org=None):
    """Enrollment and registration series over a bounded, zero-filled window."""
    months = clamp_months(months)
    now = timezone.now()
    start = window_start(months, now)
    enroll_counts = edxapp.reporting_enrollment_month_counts(start=start, org=org)
    reg_counts = edxapp.reporting_registration_month_counts(
        start=start, service_accounts=_service_accounts(),
        suffixes=constants.SERVICE_ACCOUNT_SUFFIXES, org=org,
    )
    return {
        "months": months,
        "enrollments": _dense_series(enroll_counts, start, now),
        "registrations": _dense_series(reg_counts, start, now),
    }


def get_breakdowns(org=None):
    """Non-time-series breakdowns (lean cut: course lifecycle only)."""
    now = timezone.now()
    return {"course_lifecycle": edxapp.reporting_course_lifecycle_counts(now=now, org=org)}


def cached(section, builder, force_refresh=False, **key_parts):
    """Return ``builder()``'s result, cached briefly, with a ``generated_at`` stamp.

    generated_at is captured when the value is built, so a cached response
    reports the age of its data honestly. force_refresh skips the cache read but
    still writes the fresh result back.
    """
    ttl = getattr(settings, "ADMIN_PORTAL_REPORTING_CACHE_TTL", constants.CACHE_TTL_SECONDS)
    fingerprint = json.dumps(
        {k: v for k, v in key_parts.items() if v is not None},
        sort_keys=True, default=str)
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:32]
    cache_key = f"{constants.CACHE_PREFIX}:{section}:{digest}"
    if ttl and not force_refresh:
        hit = cache.get(cache_key)
        if hit is not None:
            return hit
    payload = builder()
    payload["generated_at"] = timezone.now().isoformat()
    if ttl:
        cache.set(cache_key, payload, timeout=ttl)
    return payload
