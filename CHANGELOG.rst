==========
Change Log
==========

Unreleased
----------

* EDL-10: Course-scoped role management (``GET/POST /edl-panel/api/v1/roles/``).
  GET returns the grantable-role catalog (Course Admin / Course Staff / Limited
  Staff) with one-line descriptions. POST grants/revokes via ``allow_access`` /
  ``revoke_access`` behind an allow-list — global/site roles are not grantable.
  Granting mirrors the dashboard: the target must be active (409 otherwise) and
  is auto-enrolled if not already enrolled. Writes a role_grant/role_revoke
  audit entry.

* EDL-8 / EDL-9: Enroll and unenroll endpoints
  (``POST /edl-panel/api/v1/enrollments/enroll/`` and ``.../unenroll/``).
  Enroll or unenroll one or many identifiers (email or username) into a
  published course run, reusing the platform's
  ``process_student_enrollment_batch`` (notification-email toggle,
  ``CourseEnrollmentAllowed`` for pending users, soft data-retaining unenroll,
  per-student ``ManualEnrollmentAudit``). Validates the course run and
  identifiers; writes a summary audit entry.

* EDL-7: Deactivate/reactivate endpoints
  (``POST /edl-panel/api/v1/users/<username>/deactivate|reactivate/``). Sets
  ``UserStanding`` so login/course access is blocked while enrollments,
  submissions and grades are retained (not retirement). 404 for unknown user;
  writes an audit entry.

* EDL-6: User directory (``GET /edl-panel/api/v1/users/``). Paginated
  list with partial search over username/email (and ``UserProfile.name``
  in-platform) and a ``pending``/``active``/``disabled`` status filter. Status
  derives from ``is_active`` + ``UserStanding``. Platform-only relations engage
  via capability checks so the endpoint runs standalone. (The core account API
  only does exact-match lookups, so this is net-new query logic.)

* EDL-5: Create-user endpoint (``POST /edl-panel/api/v1/users/``). Reuses the
  platform's ``do_create_account`` atomically; duplicate email/username return
  inline field errors (409) with no partial account. Password provisioning
  follows ``EDL_PANEL_PASSWORD_MODE``: ``link`` (default) creates an
  unusable-password account and emails a set-password link; ``copy`` sets a
  generated password, activates the account and returns it once. Platform
  calls are isolated behind ``edxapp.py`` so the suite runs standalone. Writes
  a create_user audit entry.

* EDL-3: Audit log. Adds the append-only ``EdlAdminAuditLog`` model (actor,
  action, target, course, detail, timestamp), a ``record_action`` helper that
  also emits an ``eventtracking`` event (best-effort), and a read-only Django
  admin. Enrollment actions continue to reuse the platform's own
  ``ManualEnrollmentAudit``.

* EDL-2: EDL-admin access gate. Adds the ``edl_admin`` Django group (via data
  migration), an ``IsEdlAdmin`` DRF permission + ``EdlPanelAPIView`` base, and
  an ``EdlAdminRequiredMixin`` for the browser landing page. Non-admins get a
  403 (anonymous browser users are redirected to login); superusers bypass by
  default (``EDL_PANEL_SUPERUSER_BYPASS``). Adds a gated ``api/v1/me/`` endpoint.

0.1.0
-----

* EDL-1: Initial ``lms.djangoapp`` plugin scaffold — app registration, plugin
  settings (common/production/test), URL wiring at ``^edl-panel/`` with a
  browser landing page at ``/edl-panel/`` and a public REST health endpoint at
  ``/edl-panel/api/v1/health/``, with tests.
