=========
admin-portal
=========

EDL self-serve admin panel for **user and course enrollment management** on
Open edX. Packaged as an ``lms.djangoapp`` plugin: install it into the LMS and
it auto-registers at ``/admin-portal/``:

* ``/admin-portal/``            — browser-facing panel (Admin MFE mount point)
* ``/admin-portal/api/v1/``     — REST API the panel consumes

A separate Admin MFE (frontend) renders into the landing route; this
repository is the backend plugin only.

Scope
=====

* Learner management — create, search/filter, deactivate/reactivate.
* Enrollment — enroll/unenroll one or many into published course runs.
* Staff management — assign/change/remove course-scoped roles.
* Every mutating action is gated behind a dedicated EDL-admin role and written
  to an audit log.

Status
======

Pre-alpha. The backend is feature-complete (EDL-1…EDL-10): access gate, audit
log, create / list-search-filter / deactivate-reactivate users, enroll /
unenroll, and course-scoped role management. All endpoints are covered by a
standalone test suite; end-to-end verification against a live LMS is pending.
The Admin MFE (frontend) is a separate repository.

Installation
============

.. code-block:: bash

    pip install -e /path/to/admin-portal

Inside a Tutor deployment, add the package as a private requirement and rebuild
the ``openedx`` image, then restart the LMS.

Verify it loaded
================

.. code-block:: bash

    ./manage.py lms print_setting INSTALLED_APPS | grep admin_portal
    curl -sS https://<lms-host>/admin-portal/api/v1/health/

Expected response::

    {"status": "ok", "service": "admin-portal", "version": "0.1.0"}

Development
===========

Run the standalone test suite (outside edx-platform):

.. code-block:: bash

    pip install -r requirements/test.in
    pip install -e .
    pytest

Configuration
=============

``ADMIN_PORTAL_ADMIN_GROUP`` (default ``edl_admin``)
    Django group whose members are treated as EDL admins.

``ADMIN_PORTAL_PASSWORD_MODE`` (default ``link``)
    ``link`` emails a set-password link on account creation; ``copy`` generates
    a password surfaced once to the admin.

``ADMIN_PORTAL_SUPERUSER_BYPASS`` (default ``True``)
    When ``True``, Django superusers pass the access gate without being in the
    admin group.

API reference
=============

Base URL: ``/admin-portal/api/v1/``. All paths below are relative to it.

Authentication & access
------------------------

Every endpoint except ``health/`` requires an authenticated request **and**
membership of the EDL-admin group (``ADMIN_PORTAL_ADMIN_GROUP``); superusers pass
when ``ADMIN_PORTAL_SUPERUSER_BYPASS`` is on. Authenticate with a JWT
(``Authorization: JWT <token>``) or a logged-in session.

* Not an EDL admin (or anonymous) → ``403`` on API routes.
* The browser landing page ``/admin-portal/`` redirects anonymous users to login
  and returns ``403`` for authenticated non-admins.

Validation errors use DRF's field-keyed shape, e.g.
``{"email": ["This field is required."]}``. Examples use ``curl`` with a JWT.

health
------

``GET health/`` — public liveness probe (no auth).

.. code-block:: bash

    curl -sS https://<lms>/admin-portal/api/v1/health/

::

    200  {"status": "ok", "service": "admin-portal", "version": "0.1.0"}

me
--

``GET me/`` — identity of the current admin; the MFE calls it on load to
confirm access.

::

    200  {"username": "admin", "email": "admin@example.com", "is_edl_admin": true}

List users
----------

``GET users/`` — paginated directory.

Query params:

* ``search`` — partial match on username / email (and full name in-platform).
* ``status`` — one of ``pending`` | ``active`` | ``disabled``.
* ``page``, ``page_size`` (default 25, max 100).

.. code-block:: bash

    curl -sS "https://<lms>/admin-portal/api/v1/users/?search=ali&status=active" \
         -H "Authorization: JWT <token>"

::

    200
    {
      "count": 1, "next": null, "previous": null,
      "results": [
        {"id": 42, "username": "alice", "email": "alice@example.com",
         "name": "Alice Adams", "is_active": true, "status": "active"}
      ]
    }

Status meanings: ``pending`` = invited, not yet activated; ``active`` = active
and enabled; ``disabled`` = account standing disabled.

Create user
-----------

``POST users/`` — create one account. Body: ``username``, ``email``, ``name``.

.. code-block:: bash

    curl -sS -X POST https://<lms>/admin-portal/api/v1/users/ \
         -H "Authorization: JWT <token>" -H "Content-Type: application/json" \
         -d '{"username": "learner1", "email": "learner1@example.com", "name": "Learner One"}'

* ``201`` link mode (default)::

    {"id": 51, "username": "learner1", "email": "learner1@example.com",
     "is_active": false, "status": "pending"}

  A set-password link is emailed; the admin never sees a password.

* ``201`` copy mode (``ADMIN_PORTAL_PASSWORD_MODE=copy``) — adds a one-time
  ``"password"`` field and the account is ``active``.
* ``409`` duplicate — ``{"username": ["..."]}`` or ``{"email": ["..."]}``;
  no partial account is created.
* ``400`` invalid/missing field — field-keyed errors.

Deactivate / reactivate
-----------------------

``POST users/<username>/deactivate/`` and ``POST users/<username>/reactivate/``.
Deactivation blocks login and course access while retaining enrollments,
submissions and grades (it is **not** account retirement).

::

    200  {"username": "learner1", "is_disabled": true}     # deactivate
    200  {"username": "learner1", "is_disabled": false}    # reactivate
    404  {"detail": "User not found."}

Enroll / unenroll
-----------------

``POST enrollments/enroll/`` and ``POST enrollments/unenroll/``. Body:

* ``course_id`` (required) — course-run key.
* ``identifiers`` (required) — list of emails or usernames.
* ``email_students`` (default ``false``) — send the notification email.
* ``auto_enroll`` (default ``false``) — allow not-yet-registered emails
  (creates a pending ``CourseEnrollmentAllowed``).
* ``reason`` (optional).

.. code-block:: bash

    curl -sS -X POST https://<lms>/admin-portal/api/v1/enrollments/enroll/ \
         -H "Authorization: JWT <token>" -H "Content-Type: application/json" \
         -d '{"course_id": "course-v1:Org+Course+Run",
              "identifiers": ["a@example.com", "bob"],
              "email_students": true, "auto_enroll": true}'

::

    200
    {
      "action": "enroll", "auto_enroll": true,
      "results": [{"identifier": "a@example.com", "success": true, "...": "..."}],
      "successful_operations": 2, "failed_operations": 0, "total_students": 2
    }

Per-identifier failures are reported inside ``results`` (the request is still
``200``). Errors: ``400`` for a malformed ``course_id`` or empty
``identifiers``; ``404`` if the course run does not exist. Unenroll is soft —
submission and grade data are retained.

Roles
-----

``GET roles/`` — catalog of grantable, course-scoped roles.

::

    200
    {"roles": [
      {"role": "instructor",    "description": "Course Admin — ..."},
      {"role": "staff",         "description": "Course Staff — ..."},
      {"role": "limited_staff", "description": "Limited Staff — ..."}
    ]}

``POST roles/`` — grant or revoke. Body: ``course_id``, ``identifier`` (email
or username), ``role`` (one of the catalog keys), ``action``
(``allow`` | ``revoke``).

.. code-block:: bash

    curl -sS -X POST https://<lms>/admin-portal/api/v1/roles/ \
         -H "Authorization: JWT <token>" -H "Content-Type: application/json" \
         -d '{"course_id": "course-v1:Org+Course+Run",
              "identifier": "bob", "role": "staff", "action": "allow"}'

::

    200  {"username": "bob", "role": "staff", "action": "allow"}

Granting requires an active user and auto-enrolls the grantee if not already
enrolled. Site Admin / Global Staff and org-wide roles are **not** grantable.
Errors: ``400`` non-grantable role or malformed ``course_id``; ``404`` unknown
user or course; ``409`` granting to an inactive account. Change a role by
revoking the old one and allowing the new one.

Audit
-----

Every create, deactivate/reactivate, enroll/unenroll and role change writes an
``EdlAdminAuditLog`` row (actor, action, target, course, timestamp) and emits
an ``admin_portal.<action>`` tracking event. Enrollment actions additionally leave
the platform's own ``ManualEnrollmentAudit``. The audit log is browsable
read-only in Django admin.

License
=======

AGPL-3.0 (matching the Open edX platform).
