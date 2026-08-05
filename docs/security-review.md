# Security Review — admin-portal

**Scope:** the `admin-portal` LMS plugin (REST API + Django landing) and the
`admin-portal` MFE (`frontend-app-admin-portal`).
**Method:** manual code review of every endpoint, the permission gate, input
handling, sensitive-data flows, privilege boundaries, and the MFE.
**Verdict:** No high/critical findings. Posture is strong (admin-gated, ORM-only,
React-escaped, role allow-list enforced). Two medium hardening items were fixed
in this pass (see *Fixes applied*).

## Authentication & authorization

- **Every feature endpoint is gated.** All views extend `AdminPortalAPIView`
  (`IsAuthenticated` + `IsEdlAdmin`); verified route-by-route in
  `rest_api/v1/urls.py`. Only `GET /health/` is public (liveness, returns no
  data). ✅
- Anonymous → **401**; authenticated non-admin → **403**. The Django landing
  page (`PanelIndexView`) is gated by `EdlAdminRequiredMixin` (anonymous →
  login redirect, non-admin → 403). ✅
- `ADMIN_PORTAL_SUPERUSER_BYPASS` (default `True`) lets superusers pass the group
  check — documented; set `False` for strict group-only access. ⚠️ (config)

## Privilege escalation (the key control)

- The course-role endpoint **allow-lists** `instructor` / `staff` /
  `limited_staff` via a serializer `ChoiceField` **and** a second check in
  `roles.py`. Site Admin / Global Staff / org-wide / `is_staff` / `is_superuser`
  are **not grantable** through this API — an EDL admin cannot escalate anyone
  (or themselves) to global privileges. ✅
- Grants require an active target and auto-enroll (mirrors the platform's Course
  Team dashboard); revocation is allowed on inactive users. ✅

## Input validation & injection

- All persistence is via the Django ORM (parameterized) — **no SQL injection**.
  Directory search uses `__icontains` (parameterized). ✅
- Course keys parsed via `opaque_keys`; malformed → 400. ✅
- No `eval`/`exec`/`pickle`/shell execution anywhere. ✅
- **Bulk input bounded** (fix): enroll/unenroll `identifiers` capped at 1000 per
  request; `course_id`/`reason` length-limited — guards against a
  large-payload DoS.

## Sensitive-data handling

- **Passwords:** *link* mode never exposes a password; *copy* mode returns a
  generated password once in the API response (HTTPS) and is **never logged or
  stored in plaintext**. Passwords come from the platform's `generate_password`
  (CSPRNG). ✅
- **No-store (fix):** all gated responses now send `Cache-Control: no-store`, so
  the one-time password and learner PII are not retained by browsers/proxies.
- **Audit log** records actor / action / target / timestamp (intended); it holds
  **no passwords**. Emitted tracking events carry identifiers for audit only. ✅
- No secrets in URLs. Usernames appear in deactivate/reactivate paths (public
  identifiers, over HTTPS) — acceptable.

## CSRF

- The MFE authenticates with **JWT** (CSRF-exempt by design). `SessionAuthentication`
  still enforces CSRF on unsafe methods for session-based callers. ✅

## Frontend (admin-portal MFE)

- All API data is rendered through React (auto-escaped); **no
  `dangerouslySetInnerHTML`**, no raw HTML injection. ✅
- JWT is handled by `frontend-platform`'s `getAuthenticatedHttpClient` — **no
  manual token storage** in app code. ✅
- A 403 renders the access-denied shell; no privileged data is fetched or shown
  before the gate check. ✅

## Fixes applied in this review

1. `Cache-Control: no-store` on all gated responses (`rest_api/base.py`).
2. Bulk-input caps on enroll/unenroll and bounded `course_id`/`reason`
   (`rest_api/v1/serializers.py`).
3. Tests for both (`tests/test_security.py`).

## Recommendations (non-blocking / ops)

- **Rate-limiting** on create/enroll for defense-in-depth (low risk today —
  admin-gated). Use edx-platform's ratelimit or an upstream WAF.
- **Security headers / CSP** for the Django landing page — best handled at the
  proxy (platform-wide).
- Choose `ADMIN_PORTAL_SUPERUSER_BYPASS` per environment.
- Confirm `UserStandingMiddleware` is enabled — deactivation enforcement
  depends on it.
- Define an audit-log **retention** policy.
