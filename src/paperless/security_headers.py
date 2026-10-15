from django.conf import settings


class SecurityHeadersMiddleware:
    """Adds the RentShield baseline security headers to every response.

    Deterministic and side-effect free: it reads a handful of settings once
    and stamps fixed header values on each response. It deliberately does NOT
    set X-Frame-Options -- Django's XFrameOptionsMiddleware already emits
    SAMEORIGIN, which the document viewer needs (it embeds same-origin PDF
    previews in iframes; DENY would break that), so we leave that header to
    Django and only fill the gaps.

    Content-Security-Policy ships in Report-Only mode by default so local
    development, WebAuthn/passkey ceremonies and the OIDC redirects can be
    audited for violations before the policy is enforced. Set
    PAPERLESS_CSP_ENFORCE=true to switch to the enforcing header.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._csp = getattr(settings, "RS_CSP_POLICY", "")
        self._csp_enforce = getattr(settings, "RS_CSP_ENFORCE", False)
        self._csp_header = (
            "Content-Security-Policy"
            if self._csp_enforce
            else "Content-Security-Policy-Report-Only"
        )

    def __call__(self, request):
        response = self.get_response(request)

        # setdefault so we never clobber a header a more specific view set.
        response.setdefault("X-Content-Type-Options", "nosniff")
        response.setdefault("X-XSS-Protection", "1; mode=block")
        response.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")

        if self._csp and "Content-Security-Policy" not in response:
            response.setdefault(self._csp_header, self._csp)

        return response
