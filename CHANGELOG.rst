==========
Change Log
==========

Unreleased
----------

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
