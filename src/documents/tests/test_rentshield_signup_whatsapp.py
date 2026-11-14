"""Tests for the reverse-WhatsApp-QR phone verification (signup Option 2):
contact details -> email code -> a QR the user sends to us on WhatsApp ->
WAHA's inbound webhook confirms it -> account created. No outbound message,
so it's free. Runs the DEBUG dev path (no ZITADEL PAT) so completion logs the
user straight in."""

from __future__ import annotations

import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.test import override_settings

from documents.rentshield_identity.models import VerifiedPhone
from documents.rentshield_identity.models import WhatsAppVerification

EMAIL = "pm-wa@example.com"
PHONE = "+971501234567"


@override_settings(RENTSHIELD_WHATSAPP_NUMBER="+971500000000", DEBUG=True)
class SignupWhatsAppQRTest(TestCase):
    def setUp(self):
        # The email-OTP rate limit lives in the cache, which persists across
        # TestCase methods; clear it so each test starts from a clean quota.
        from django.core.cache import cache
        cache.clear()

    def _reach_phone_step(self):
        # Step 1: business email only
        self.client.post("/login/email/", {"email": EMAIL})
        # verify email
        self.client.post("/login/verify/", {"code": self.client.session["signup_draft"]["otp"]})
        # Step 2: about you — name + company + job + priorities
        self.client.post("/login/about/", {
            "first_name": "Dana", "surname": "Mansoori",
            "company_name": "Mansoori Estates", "job_title": "Property Manager",
            "priorities": "Replace expensive lawyer fees for routine notices",
        })
        # Step 3: final — phone + country + terms
        self.client.post("/login/phone/", {"phone": PHONE, "country": "United Kingdom", "agree": "on"})
        resp = self.client.get("/login/phone/")
        return resp, self.client.session["signup_draft"]["wa_code"]

    def _inbound(self, code, sender="971501234567@c.us", qs=""):
        payload = {"event": "message", "payload": {"from": sender, "body": f"RentShield verify {code}"}}
        return self.client.post(
            f"/api/whatsapp/inbound/{qs}",
            data=json.dumps(payload), content_type="application/json",
        )

    def test_qr_page_renders_and_creates_pending_row(self):
        resp, code = self._reach_phone_step()
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "wa.me")
        self.assertContains(resp, code)
        row = WhatsAppVerification.objects.get(code=code)
        self.assertFalse(row.is_verified)
        self.assertEqual(row.expected_phone, PHONE)

    def test_full_flow_webhook_then_complete(self):
        resp, code = self._reach_phone_step()
        # not verified before the message
        self.assertFalse(self.client.get("/login/phone/status/").json()["verified"])
        # WAHA delivers the inbound message
        w = self._inbound(code)
        self.assertEqual(w.status_code, 200)
        self.assertTrue(w.json()["matched"])
        row = WhatsAppVerification.objects.get(code=code)
        self.assertTrue(row.is_verified)
        self.assertEqual(row.sender_phone, "+971501234567")
        # status now flips, and no account exists yet
        self.assertTrue(self.client.get("/login/phone/status/").json()["verified"])
        self.assertFalse(User.objects.filter(email=EMAIL).exists())
        # the page's auto-POST completes signup
        self.client.post("/login/phone/verify/")
        user = User.objects.get(email=EMAIL)
        self.assertEqual((user.first_name, user.last_name), ("Dana", "Mansoori"))
        self.assertTrue(VerifiedPhone.objects.get(user=user).is_verified)
        self.assertEqual(VerifiedPhone.objects.get(user=user).phone, PHONE)

    def test_no_account_until_verified(self):
        self._reach_phone_step()
        r = self.client.post("/login/phone/verify/")
        self.assertRedirects(r, "/login/phone", fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(email=EMAIL).exists())

    def test_webhook_unknown_code_does_not_match(self):
        self._reach_phone_step()
        w = self._inbound("ZZZZZZZZ")
        self.assertEqual(w.status_code, 200)
        self.assertFalse(w.json()["matched"])

    def test_qr_page_misconfigured_without_number(self):
        with override_settings(RENTSHIELD_WHATSAPP_NUMBER=""):
            resp, _code = self._reach_phone_step()
            self.assertContains(resp, "isn't set up")

    def test_full_flow_saves_business_profile(self):
        _, code = self._reach_phone_step()
        self._inbound(code)
        self.client.post("/login/phone/verify/")
        from documents.rentshield_identity.models import AccountProfile
        user = User.objects.get(email=EMAIL)
        prof = AccountProfile.objects.get(user=user)
        self.assertEqual(prof.company_name, "Mansoori Estates")
        self.assertEqual(prof.job_title, "Property Manager")
        self.assertEqual(prof.country, "United Kingdom")
        self.assertTrue(prof.priorities)

    @override_settings(RENTSHIELD_WA_WEBHOOK_SECRET="s3cr3t")
    def test_webhook_secret_enforced(self):
        _, code = self._reach_phone_step()
        # wrong/absent secret -> 403, not verified
        self.assertEqual(self._inbound(code).status_code, 403)
        self.assertFalse(WhatsAppVerification.objects.get(code=code).is_verified)
        # correct secret -> verified
        self.assertEqual(self._inbound(code, qs="?secret=s3cr3t").status_code, 200)
        self.assertTrue(WhatsAppVerification.objects.get(code=code).is_verified)
