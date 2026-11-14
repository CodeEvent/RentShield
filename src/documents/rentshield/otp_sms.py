# Pluggable phone-OTP SMS sender for the signup wizard.
#
# The signup wizard already mails a 6-digit email OTP (rentshield_views.
# signup_email_view) with the code held in the session, never the DB.
# This module is the *phone* counterpart: it only has to DELIVER a code
# the view already generated and stored in the session -- so it needs no
# model, no migration, and no state of its own.
#
# Delivery backend is chosen by settings.RENTSHIELD_SMS_BACKEND
# (default "console"):
#
#   "console"  -- dev/default. Logs the code and returns it so the verify
#                 page can SHOW it on screen (DEBUG only). No SIM, no
#                 network, no external server -- nothing leaves the
#                 machine. This is what ships until a real gateway is
#                 wired, and keeps the whole flow testable offline.
#
#   "smsgate"  -- real SMS via sms-gate.app (github.com/capcom6/
#                 android-sms-gateway, Apache-2.0): an Android phone + SIM
#                 you control becomes a REST SMS gateway. Set
#                 RENTSHIELD_SMS_GATE_URL / _USER / _PASS. Chosen as the
#                 Twilio alternative because it self-hosts, has an official
#                 Python client, and sends over YOUR phone's carrier
#                 connection (no third-party routing of the OTP). textbee
#                 (MIT) and httpSMS are drop-in alternatives behind this
#                 same send_sms_otp() seam.
#
# IMPORTANT: no backend here ever phones a third party by default; the
# "console" default is fully offline. A real backend is opt-in via
# settings, mirroring how every outbound integration in this codebase is
# off until explicitly configured.
from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger("rentshield.otp_sms")


class SmsOtpError(Exception):
    """Raised when a configured real SMS backend fails to accept the
    message, so the view can show 'could not send, try again' rather than
    silently pretending a code went out."""


def _backend() -> str:
    return getattr(settings, "RENTSHIELD_SMS_BACKEND", "console")


def send_sms_otp(phone: str, code: str) -> str | None:
    """Deliver `code` to `phone` (E.164, e.g. +9715...). Returns the code
    string when the console backend is active AND DEBUG is on (so the dev
    verify page can display it); returns None for any real delivery so the
    code is never surfaced to the browser in production.

    Raises SmsOtpError if a real backend rejects the send."""
    backend = _backend()
    if backend == "console":
        logger.info("rentshield phone OTP for %s: %s (console backend)", phone, code)
        # Only hand the code back for on-screen display in DEBUG; never in prod.
        return code if getattr(settings, "DEBUG", False) else None
    if backend == "smsgate":
        _send_via_smsgate(phone, code)
        return None
    raise SmsOtpError(f"Unknown RENTSHIELD_SMS_BACKEND: {backend!r}")


def _send_via_smsgate(phone: str, code: str) -> None:
    """sms-gate.app REST send. Kept minimal and dependency-free (plain
    requests + basic auth) so no new package is needed to turn it on; the
    official `android_sms_gateway` Python client can replace this body
    later without touching the view."""
    import requests

    base = getattr(settings, "RENTSHIELD_SMS_GATE_URL", "").rstrip("/")
    user = getattr(settings, "RENTSHIELD_SMS_GATE_USER", "")
    password = getattr(settings, "RENTSHIELD_SMS_GATE_PASS", "")
    if not base or not user:
        raise SmsOtpError("smsgate backend selected but RENTSHIELD_SMS_GATE_URL/_USER unset")
    message = f"Your RentShield verification code is {code}. It expires in 15 minutes."
    try:
        resp = requests.post(
            f"{base}/message",
            auth=(user, password),
            json={"message": message, "phoneNumbers": [phone]},
            timeout=10,
        )
    except requests.RequestException as exc:  # network/DNS/timeout
        raise SmsOtpError(f"SMS gateway unreachable: {exc}") from exc
    if resp.status_code not in (200, 201, 202):
        raise SmsOtpError(f"SMS gateway rejected the send: {resp.status_code} {resp.text}")
