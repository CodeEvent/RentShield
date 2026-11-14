"""Tests for the SMS-OTP phone verification path (RENTSHIELD_PHONE_VERIFY=sms).

Full 3-step signup: Step 1 name + business email -> email code -> Step 2 about
you -> Step 3 final (phone + country + terms) -> SMS code -> account. Runs the
DEBUG dev path (no ZITADEL PAT) so completion logs the new user straight in."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.test import override_settings

from documents.rentshield_identity.models import VerifiedPhone

EMAIL = "dana@example.com"
PHONE = "+971501234567"


@override_settings(RENTSHIELD_SMS_BACKEND="console", RENTSHIELD_PHONE_VERIFY="sms")
class SignupPhoneFlowTest(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def _walk_to_final(self):
        """Steps 1 + email code + step 2, leaving the final (phone) step next."""
        self.client.post("/login/email/", {"email": EMAIL})
        self.client.post("/login/verify/", {"code": self.client.session["signup_draft"]["otp"]})
        self.client.post("/login/about/", {
            "first_name": "Dana", "surname": "Mansoori",
            "company_name": "Mansoori Estates", "job_title": "Property Manager",
            "priorities": "Replace expensive lawyer fees for routine notices",
        })

    def _send_sms(self, phone=PHONE, country="United Arab Emirates"):
        """Final step stores the phone, then the next POST sends the SMS."""
        self.client.post("/login/phone/", {"phone": phone, "country": country, "agree": "on"})
        return self.client.post("/login/phone/")

    @override_settings(DEBUG=True)
    def test_full_signup_with_phone_otp(self):
        self._walk_to_final()
        self.assertEqual(len(mail.outbox), 1)
        self.assertFalse(User.objects.filter(email=EMAIL).exists())
        resp = self._send_sms()
        self.assertRedirects(resp, "/login/phone/verify", fetch_redirect_response=False)
        phone_code = self.client.session["signup_draft"]["phone_otp"]
        self.assertRegex(phone_code, r"^\d{6}$")
        self.client.post("/login/phone/verify/", {"code": phone_code})
        user = User.objects.get(email=EMAIL)
        self.assertEqual((user.first_name, user.last_name), ("Dana", "Mansoori"))
        phone_row = VerifiedPhone.objects.get(user=user)
        self.assertEqual(phone_row.phone, PHONE)
        self.assertTrue(phone_row.is_verified)
        self.assertNotIn("signup_draft", self.client.session)

    @override_settings(DEBUG=True)
    def test_account_reflects_contact_and_business_details(self):
        self._walk_to_final()
        self._send_sms()
        self.client.post("/login/phone/verify/", {"code": self.client.session["signup_draft"]["phone_otp"]})
        from documents.rentshield_identity.models import AccountProfile
        user = User.objects.get(email=EMAIL)
        prof = AccountProfile.objects.get(user=user)
        self.assertEqual(prof.company_name, "Mansoori Estates")
        self.assertEqual(prof.job_title, "Property Manager")
        self.assertEqual(prof.country, "United Arab Emirates")
        resp = self.client.get("/account/security/")
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Dana Mansoori", body)
        self.assertIn(PHONE, body)

    def test_provisioning_receives_contact_details(self):
        self._walk_to_final()
        self._send_sms()
        code = self.client.session["signup_draft"]["phone_otp"]
        with patch("documents.rentshield_views.provision_zitadel_user", return_value="zid-123") as prov:
            self.client.post("/login/phone/verify/", {"code": code})
        prov.assert_called_once()
        kwargs = prov.call_args.kwargs
        self.assertEqual(kwargs["given_name"], "Dana")
        self.assertEqual(kwargs["family_name"], "Mansoori")
        self.assertEqual(kwargs["phone"], PHONE)

    def test_wrong_phone_code_creates_no_account(self):
        self._walk_to_final()
        self._send_sms()
        resp = self.client.post("/login/phone/verify/", {"code": "000000"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(email=EMAIL).exists())

    @override_settings(RENTSHIELD_SMS_BACKEND="smsgate", RENTSHIELD_SMS_GATE_URL="", DEBUG=True)
    def test_smsgate_without_config_fails_gracefully(self):
        self._walk_to_final()
        self.client.post("/login/phone/", {"phone": PHONE, "country": "United Arab Emirates", "agree": "on"})
        resp = self.client.post("/login/phone/")  # tries to send -> graceful error
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(email=EMAIL).exists())

    def test_phone_step_requires_verified_email(self):
        resp = self.client.post("/login/phone/")
        self.assertRedirects(resp, "/login/email", fetch_redirect_response=False)

    def test_invalid_phone_rejected_on_final_step(self):
        self._walk_to_final()
        resp = self.client.post("/login/phone/", {"phone": "12345", "country": "United Arab Emirates", "agree": "on"})
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("phone", self.client.session["signup_draft"])

    def test_final_step_requires_terms(self):
        self._walk_to_final()
        resp = self.client.post("/login/phone/", {"phone": PHONE, "country": "United Arab Emirates"})
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("phone", self.client.session["signup_draft"])

    def test_email_only_on_step_one(self):
        # Step 1 asks for the email ONLY -- a valid email proceeds without a name.
        resp = self.client.post("/login/email/", {"email": EMAIL})
        self.assertRedirects(resp, "/login/verify", fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)

    def test_missing_name_rejected_on_step_two(self):
        self.client.post("/login/email/", {"email": EMAIL})
        self.client.post("/login/verify/", {"code": self.client.session["signup_draft"]["otp"]})
        resp = self.client.post("/login/about/", {
            "first_name": "", "surname": "Mansoori",
            "company_name": "Acme", "job_title": "PM", "priorities": "x",
        })
        self.assertEqual(resp.status_code, 200)  # re-renders step 2 with an error
        self.assertNotIn("first_name", self.client.session["signup_draft"])
