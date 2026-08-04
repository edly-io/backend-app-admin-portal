=========
edl-panel
=========

EDL self-serve admin panel for **user and course enrollment management** on
Open edX. Packaged as an ``lms.djangoapp`` plugin: install it into the LMS and
it auto-registers at ``/edl-panel/``:

* ``/edl-panel/``            — browser-facing panel (Admin MFE mount point)
* ``/edl-panel/api/v1/``     — REST API the panel consumes

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

Pre-alpha. This is the **EDL-1 scaffold**: plugin registration, settings/URL
wiring, and a public health endpoint. Feature endpoints land in subsequent
stories (EDL-2 onward).

Installation
============

.. code-block:: bash

    pip install -e /path/to/edl-panel

Inside a Tutor deployment, add the package as a private requirement and rebuild
the ``openedx`` image, then restart the LMS.

Verify it loaded
================

.. code-block:: bash

    ./manage.py lms print_setting INSTALLED_APPS | grep edl_panel
    curl -sS https://<lms-host>/edl-panel/api/v1/health/

Expected response::

    {"status": "ok", "service": "edl-panel", "version": "0.1.0"}

Development
===========

Run the standalone test suite (outside edx-platform):

.. code-block:: bash

    pip install -r requirements/test.in
    pip install -e .
    pytest

Configuration
=============

``EDL_PANEL_ADMIN_GROUP`` (default ``edl_admin``)
    Django group whose members are treated as EDL admins.

``EDL_PANEL_PASSWORD_MODE`` (default ``link``)
    ``link`` emails a set-password link on account creation; ``copy`` generates
    a password surfaced once to the admin.

License
=======

AGPL-3.0 (matching the Open edX platform).
