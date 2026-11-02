"""The remote-notarization + RDC-filing handoff (2026-11):
documents.rentshield.remote_notarization and the enriched
documents.rentshield.rdsc_packet. Both are honest guidance artifacts --
RentShield neither notarizes nor files, it hands the landlord exactly
what each official system (Dubai Courts e-notary / the RDC) asks for.
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from documents.models import Document
from documents.rentshield.rdsc_packet import render_rdsc_packet_html
from documents.rentshield.remote_notarization import (
    render_remote_notarization_handoff_html,
)
from documents.rentshield.service import _set_custom_field_value


class TestRemoteNotarizationHandoff(SimpleTestCase):
    def _html(self):
        return render_remote_notarization_handoff_html(
            {
                "reason": "sale",
                "landlord_name": "John Smith",
                "tenant_name": "Jane Tenant",
                "ejari_number": "12345",
                "notice_date": "2026-08-01",
            },
        )

    def test_describes_dubai_courts_e_notary_video_route(self):
        html = self._html()
        self.assertIn("Dubai Courts", html)
        self.assertIn("video call", html)

    def test_shows_which_fields_capture_the_result(self):
        html = self._html()
        self.assertIn("RentShield: Notarized Copy", html)
        self.assertIn("RentShield: Notary Reference No.", html)
        self.assertIn("RentShield: Served Date", html)

    def test_is_honest_that_rentshield_is_not_the_notary(self):
        html = self._html()
        self.assertIn("is not the", html)
        self.assertIn("notarization is performed by the dubai courts", html.lower())


class TestEnrichedRdscPacket(SimpleTestCase):
    BASE = {
        "reason": "nonpayment",
        "tenant_name": "Jane Tenant",
        "landlord_name": "John Smith",
        "notice_period_days": 30,
    }

    def test_lists_both_filing_channels(self):
        html = render_rdsc_packet_html(self.BASE)
        self.assertIn("rdc.gov.ae", html)
        self.assertIn("Dubai REST", html)
        self.assertIn("tele-litigation", html)

    def test_not_served_tells_landlord_to_serve_first(self):
        html = render_rdsc_packet_html(self.BASE)
        self.assertIn("has not been served yet", html)

    def test_served_and_matured_says_file_now(self):
        html = render_rdsc_packet_html({**self.BASE, "served_date": "2020-01-01"})
        self.assertIn("you may file at the RDC now", html)

    def test_served_but_not_matured_gives_earliest_date(self):
        html = render_rdsc_packet_html({**self.BASE, "served_date": "2099-01-01"})
        self.assertIn("on or after", html)

    def test_notary_service_asks_for_notification_officer_report(self):
        html = render_rdsc_packet_html({**self.BASE, "service_method": "notary_public"})
        # apostrophe is HTML-escaped in the rendered output
        self.assertIn("notification officer", html)

    def test_registered_mail_asks_for_post_receipt(self):
        html = render_rdsc_packet_html({**self.BASE, "service_method": "registered_mail"})
        self.assertIn("registered-post receipt", html)


def _make_notice(owner: User, **field_overrides) -> Document:
    document = Document.objects.create(
        owner=owner,
        title="Test Notice",
        checksum=f"remote-notar-{owner.username}",
        mime_type="application/pdf",
    )
    fields = {"tenant_name": "Jane Tenant", "reason": "sale", **field_overrides}
    for key, value in fields.items():
        _set_custom_field_value(document, key, value)
    return document


class TestRemoteNotarizationView(APITestCase):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(username="remote-notar-owner")
        self.owner.user_permissions.add(
            Permission.objects.get(codename="change_document"),
        )

    def test_requires_authentication(self):
        document = _make_notice(self.owner)
        resp = self.client.post(f"/api/documents/notice/{document.id}/remote-notarization/")
        self.assertEqual(resp.status_code, 401)

    @patch("documents.rentshield.service.write_and_consume", return_value="fake-task-id")
    @patch(
        "documents.rentshield.pdf.render_html_to_pdf",
        return_value=b"%PDF-fake",
    )
    def test_generates_handoff_even_before_service(self, render_pdf, write_and_consume):
        # No served_date and no compliance gate -- notarization precedes service.
        document = _make_notice(self.owner)
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(f"/api/documents/notice/{document.id}/remote-notarization/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["task_id"], "fake-task-id")
        write_and_consume.assert_called_once()
        _, kwargs = write_and_consume.call_args
        self.assertEqual(kwargs["owner_id"], self.owner.id)

    def test_404s_for_someone_elses_notice(self):
        other = User.objects.create_user(username="remote-notar-other")
        document = _make_notice(other)
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(f"/api/documents/notice/{document.id}/remote-notarization/")
        self.assertEqual(resp.status_code, 404)
