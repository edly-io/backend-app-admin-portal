"""Browser-facing views for the admin_portal plugin."""
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views import View

from admin_portal import __version__
from admin_portal.permissions import EdlAdminRequiredMixin

_LANDING_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Admin Portal</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
           margin: 0; display: grid; place-items: center; min-height: 100vh;
           background: #0f1f2e; color: #e8eef4; }}
    .card {{ text-align: center; padding: 2rem 2.5rem; }}
    h1 {{ margin: 0 0 .25rem; font-size: 1.8rem; }}
    p {{ margin: .25rem 0; color: #9fb3c6; }}
    code {{ background: #1c3145; padding: .15rem .4rem; border-radius: 4px; color: #cfe3f5; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Admin Portal</h1>
    <p>User &amp; course enrollment management</p>
    <p>Backend v{version} is live. API at <code>/admin-portal/api/v1/</code>.</p>
  </div>
</body>
</html>"""


class PanelIndexView(EdlAdminRequiredMixin, View):
    """
    Landing at ``/admin-portal/`` on the LMS host.

    Gated to EDL admins (EDL-2): anonymous users are redirected to login and
    authenticated non-admins get a 403. The actual admin UI is the Admin Portal
    MFE on the ``apps.`` host, so for admins we redirect there instead of
    showing this LMS-host page (which would otherwise be a dead-end placeholder).

    The redirect target is ``ADMIN_PORTAL_MFE_URL`` when set; otherwise we derive
    ``<scheme>://apps.<lms-host>/admin-portal/`` (the tutor MFE-host convention).
    The static page below is only a fallback for when the MFE URL cannot be
    determined (e.g. an unusual host layout with no override configured).
    """

    def get(self, request):  # noqa: D102
        mfe_url = getattr(settings, 'ADMIN_PORTAL_MFE_URL', '') or self._derive_mfe_url(request)
        if mfe_url:
            return redirect(mfe_url)
        return HttpResponse(_LANDING_HTML.format(version=__version__))

    @staticmethod
    def _derive_mfe_url(request):
        """Best-effort MFE URL from the request host (``apps.<lms-host>/admin-portal/``)."""
        host = (request.get_host() or '').split(':')[0]
        if not host or host.startswith('apps.'):
            return ''  # already on the MFE host, or no usable host — fall back
        scheme = 'https' if request.is_secure() else 'http'
        return f'{scheme}://apps.{host}/admin-portal/'
