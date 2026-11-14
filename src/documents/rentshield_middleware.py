"""RentShield: stop the browser serving stale copies of the custom
server-rendered pages.

The custom RentShield screens (dashboard, contacts, notices, properties,
verification, disputes, compliance, settings, ...) are plain server-rendered
HTML with no cache headers, so a browser could serve an old copy from its
disk cache after the templates change. This middleware marks those page
responses `no-store` so every visit re-fetches. It deliberately touches
ONLY the custom RentShield page prefixes -- never /api/, /assets/, the
Angular SPA, or static files.
"""

from __future__ import annotations

# Prefixes served by the custom RentShield function views (see paperless/urls.py).
_RS_PAGE_PREFIXES = (
    "/overview", "/contacts", "/records", "/properties",
    "/verification", "/disputes", "/compliance", "/account",
)


class RentShieldNoStoreMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            path = request.path or ""
            ctype = response.get("Content-Type", "")
            if (
                request.method in ("GET", "HEAD")
                and "text/html" in ctype
                and any(path == p or path.startswith(p + "/") for p in _RS_PAGE_PREFIXES)
            ):
                response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                response["Pragma"] = "no-cache"
                response["Expires"] = "0"
        except Exception:
            pass
        return response
