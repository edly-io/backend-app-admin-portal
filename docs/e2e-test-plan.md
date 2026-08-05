# End-to-End Test Plan — admin-portal (backend ↔ admin-portal MFE)

Exercises the full stack: the `admin-portal` MFE → JWT → the gated `admin-portal`
REST API → edx-platform → DB, against a **running** platform. Each case maps to
an acceptance criterion.

## Prerequisites

- Platform up (`tutor local start -d`); `admin-portal` MFE built.
- URLs: LMS `http://local.openedx.io`, MFE `http://apps.local.openedx.io/admin-portal/`, API base `http://local.openedx.io/admin-portal/api/v1/`.
- Accounts: one **EDL admin** (member of `edl_admin`, or a superuser) and one
  **non-admin** learner.
- A **published** course run id for the enrollment cases.

## API smoke (fast, pre-UI)

```bash
# Public health
curl -sS http://local.openedx.io/admin-portal/api/v1/health/           # -> {"status":"ok",...}
# Gate: unauthenticated -> 401
curl -sS -o /dev/null -w "%{http_code}\n" http://local.openedx.io/admin-portal/api/v1/me/   # -> 401
```

## UI cases

| # | Case (AC) | Steps | Expected |
|---|-----------|-------|----------|
| 1 | **Gate — anonymous** | Open `/admin-portal/` logged out | Redirected to LMS login |
| 2 | **Gate — non-admin** (403) | Log in as the non-admin; open `/admin-portal/` | "Access denied" shell; no data |
| 3 | **Gate — admin** | Log in as EDL admin; open `/admin-portal/` | Users table loads; header nav shows Users / Enrollment / Staff |
| 4 | **Create — link mode** (L1) | Users → Create user; fill username/email/name; submit | 201; "created", status *pending*; **set-password link emailed** (check `tutor local logs lms`/SMTP); learner receives link, sets password, can log in |
| 5 | **Duplicate rejected** (L2) | Create user with an existing email/username | Inline field error (409); **no partial account** (re-list shows none created) |
| 6 | **Create — copy mode** (L1) | Set `ADMIN_PORTAL_PASSWORD_MODE=copy`, rebuild; create user | 201, status *active*, one-time password shown once; login works with it |
| 7 | **List / search / filter** (L4) | Type in search; change status filter; paginate | Results match; badges Active/Pending/Disabled |
| 8 | **Deactivate** (L5) | Row → Deactivate → confirm | User blocked from LMS login/courses; **enrollments & grades retained** (verify in Django admin); audit entry written |
| 9 | **Reactivate** (L5) | Row → Reactivate | Login restored |
| 10 | **Enroll many + email toggle** (L6) | Enrollment → paste emails+usernames, pick run, toggle email on → Enroll | Per-identifier results; enrolled in run; unregistered emails become pending (CourseEnrollmentAllowed); notification sent when toggled |
| 11 | **Unenroll + confirm** (L7) | Enrollment → Unenroll → confirm | Removed from roster; **submissions/grades retained**; re-enroll restores |
| 12 | **Roles — grant/change/remove** (S2) | Staff → pick run + user + role → Grant; then Remove | Role applied (verify course team); grantee auto-enrolled; audit entry |
| 13 | **Roles — no global roles** (S3) | Inspect the role picker | Only Course Admin / Staff / Limited Staff; **no Site Admin / Global Staff** |
| 14 | **Audit** (cross-cutting) | Django admin → EDL admin audit log | One row per create/deactivate/enroll/unenroll/role change (actor, action, target, timestamp) |

## Pass criteria

All 14 cases behave as "Expected". Focus checks: gate returns 403/redirect for
non-admins (#1–2); duplicates leave no partial account (#5); deactivate/unenroll
**retain** data (#8, #11); global roles are never grantable (#13).

## Automating this (recommended next)

Add Cypress to `frontend-app-admin-portal` (`docs` + `cypress/e2e/*.cy.js`) driving
cases #1–13 against a deployed instance, with a session-bootstrap login step, run
nightly in CI. The API-level checks above can also run as a lightweight
authenticated smoke job. (Not committed here — needs a live target + test creds.)
