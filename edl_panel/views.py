"""Browser-facing views for the edl_panel plugin."""
from django.http import HttpResponse
from django.views import View

from edl_panel import __version__
from edl_panel.permissions import EdlAdminRequiredMixin

_LANDING_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EDL Panel</title>
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
    <h1>EDL Panel</h1>
    <p>User &amp; course enrollment management</p>
    <p>Backend v{version} is live. API at <code>/edl-panel/api/v1/</code>.</p>
  </div>
</body>
</html>"""


class PanelIndexView(EdlAdminRequiredMixin, View):
    """
    Landing page at ``/edl-panel/``.

    Gated to EDL admins (EDL-2): anonymous users are redirected to login and
    authenticated non-admins get a 403. This is the entry point the Admin MFE
    will render into.
    """

    def get(self, request):  # noqa: D102
        return HttpResponse(_LANDING_HTML.format(version=__version__))
