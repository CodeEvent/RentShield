# Runnable check for the viewflow prototype (see flows.py's docstring
# for the design and why record_filing is a Handle node completed via
# rentshield_views.rdsc_filing_complete_view, not a viewflow HTML form).
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from documents.models import Document
from documents.rentshield.service import _set_custom_field_value
from documents.rentshield_identity.models import IdentityVerification
from viewflow.workflow.models import Task

from .flows import RDSCFilingFlow
from .models import RDSCFilingProcess


def _make_served_notice(owner: User) -> Document:
    """A fully RDSC-compliant served notice: owner identity VERIFIED (NFC chip
    + face score), a registered Ejari certificate linked, and served with a
    notary reference. All three compliance checkpoints must pass, because
    generate_rdsc_filing_packet re-enforces the can_compile gate server-side
    (documents.rentshield.compliance) -- so a packet (and therefore this flow)
    only starts for a notice that clears it."""
    IdentityVerification.objects.create(
        user=owner,
        status=IdentityVerification.Status.VERIFIED,
        chip_document_number="C01X00T47",
        chip_selfie_match_score=0.91,
    )
    document = Document.objects.create(
        owner=owner,
        title="Test Notice",
        checksum=f"rdsc-workflow-test-{owner.username}",
        mime_type="application/pdf",
    )
    for key, value in {
        "landlord_name": "John Smith",
        "tenant_name": "Jane Tenant",
        "reason": "nonpayment",
        "notice_date": "2026-08-01",
        "notice_period_days": 30,
        "served_date": "2026-09-01",
        "ejari_certificate_document": [101],
        "service_method": "notary_public",
        "notary_reference_no": "NP-2026-5541",
    }.items():
        _set_custom_field_value(document, key, value)
    return document


class TestRDSCFilingFlow(TestCase):
    """The flow itself: starting it, then completing record_filing by
    calling it directly, the same way rdsc_filing_complete_view does --
    no HTTP form, no session, no assignment concept."""

    def test_starts_straight_at_a_new_record_filing_task(self):
        owner = User.objects.create_user(username="rdsc-flow-owner")
        document = _make_served_notice(owner)

        process = RDSCFilingFlow.start.run(document_id=document.pk)

        task = Task.objects.get(flow_task=RDSCFilingFlow.record_filing, process=process)
        self.assertEqual(task.status, "NEW")
        self.assertEqual(process.status, "NEW")

    def test_completes_once_record_filing_is_run(self):
        owner = User.objects.create_user(username="rdsc-flow-owner2")
        document = _make_served_notice(owner)
        process = RDSCFilingFlow.start.run(document_id=document.pk)
        task = Task.objects.get(flow_task=RDSCFilingFlow.record_filing, process=process)

        RDSCFilingFlow.record_filing.run(
            task,
            rdc_case_reference="RDC-2026-00042",
            filed_date="2026-09-05",
        )

        process.refresh_from_db()
        self.assertEqual(process.status, "DONE")
        self.assertEqual(process.rdc_case_reference, "RDC-2026-00042")


class TestRdscPacketViewFlowWiring(TestCase):
    """rentshield_views.rdsc_packet_view starts RDSCFilingFlow alongside
    its existing, unchanged async packet dispatch -- see that view's
    docstring."""

    def setUp(self):
        from django.contrib.auth.models import Permission

        self.owner = User.objects.create_user(username="rdsc-wiring-owner")
        self.owner.user_permissions.add(Permission.objects.get(codename="change_document"))
        self.api_client = APIClient()
        self.api_client.force_authenticate(user=self.owner)

    @patch("documents.rentshield.service.write_and_consume", return_value="fake-task-id")
    @patch("documents.rentshield.rdsc_packet.build_rdsc_packet", return_value=b"%PDF-fake")
    def test_generating_a_packet_starts_a_filing_process(self, build_packet, write_and_consume):
        document = _make_served_notice(self.owner)
        response = self.api_client.post(f"/api/documents/notice/{document.id}/rdsc-packet/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(RDSCFilingProcess.objects.filter(document_id=document.id).count(), 1)

    @patch("documents.rentshield.service.write_and_consume", return_value="fake-task-id")
    @patch("documents.rentshield.rdsc_packet.build_rdsc_packet", return_value=b"%PDF-fake")
    def test_generating_a_packet_twice_does_not_open_a_second_process(self, build_packet, write_and_consume):
        document = _make_served_notice(self.owner)
        self.api_client.post(f"/api/documents/notice/{document.id}/rdsc-packet/")
        self.api_client.post(f"/api/documents/notice/{document.id}/rdsc-packet/")

        self.assertEqual(RDSCFilingProcess.objects.filter(document_id=document.id).count(), 1)

    def test_filing_task_lookup_404s_before_a_packet_exists(self):
        document = _make_served_notice(self.owner)
        response = self.api_client.get(f"/api/documents/notice/{document.id}/rdsc-filing-task/")
        self.assertEqual(response.status_code, 404)

    @patch("documents.rentshield.service.write_and_consume", return_value="fake-task-id")
    @patch("documents.rentshield.rdsc_packet.build_rdsc_packet", return_value=b"%PDF-fake")
    def test_filing_task_lookup_succeeds_once_a_packet_exists(self, build_packet, write_and_consume):
        document = _make_served_notice(self.owner)
        self.api_client.post(f"/api/documents/notice/{document.id}/rdsc-packet/")

        response = self.api_client.get(f"/api/documents/notice/{document.id}/rdsc-filing-task/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "open")
        self.assertIsNone(response.data["rdc_case_reference"])

    @patch("documents.rentshield.service.write_and_consume", return_value="fake-task-id")
    @patch("documents.rentshield.rdsc_packet.build_rdsc_packet", return_value=b"%PDF-fake")
    def test_filing_task_lookup_reports_done_once_filed(self, build_packet, write_and_consume):
        document = _make_served_notice(self.owner)
        self.api_client.post(f"/api/documents/notice/{document.id}/rdsc-packet/")
        self.api_client.post(
            f"/api/documents/notice/{document.id}/rdsc-filing-task/complete/",
            {"rdc_case_reference": "RDC-2026-00042", "filed_date": "2026-09-05"},
        )

        response = self.api_client.get(f"/api/documents/notice/{document.id}/rdsc-filing-task/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "done")
        self.assertEqual(response.data["rdc_case_reference"], "RDC-2026-00042")

    def test_complete_404s_before_a_packet_exists(self):
        document = _make_served_notice(self.owner)
        response = self.api_client.post(
            f"/api/documents/notice/{document.id}/rdsc-filing-task/complete/",
            {"rdc_case_reference": "RDC-2026-00042", "filed_date": "2026-09-05"},
        )
        self.assertEqual(response.status_code, 404)

    def test_complete_requires_both_fields(self):
        document = _make_served_notice(self.owner)
        response = self.api_client.post(
            f"/api/documents/notice/{document.id}/rdsc-filing-task/complete/",
            {"rdc_case_reference": ""},
        )
        self.assertEqual(response.status_code, 400)

    @patch("documents.rentshield.service.write_and_consume", return_value="fake-task-id")
    @patch("documents.rentshield.rdsc_packet.build_rdsc_packet", return_value=b"%PDF-fake")
    def test_complete_finishes_the_process(self, build_packet, write_and_consume):
        document = _make_served_notice(self.owner)
        self.api_client.post(f"/api/documents/notice/{document.id}/rdsc-packet/")

        response = self.api_client.post(
            f"/api/documents/notice/{document.id}/rdsc-filing-task/complete/",
            {"rdc_case_reference": "RDC-2026-00042", "filed_date": "2026-09-05"},
        )

        self.assertEqual(response.status_code, 200)
        process = RDSCFilingProcess.objects.get(document_id=document.id)
        self.assertEqual(process.status, "DONE")
        self.assertEqual(process.rdc_case_reference, "RDC-2026-00042")

    @patch("documents.rentshield.service.write_and_consume", return_value="fake-task-id")
    @patch("documents.rentshield.rdsc_packet.build_rdsc_packet", return_value=b"%PDF-fake")
    def test_complete_404s_for_someone_else_s_notice(self, build_packet, write_and_consume):
        from django.contrib.auth.models import Permission

        other_owner = User.objects.create_user(username="rdsc-wiring-other")
        other_owner.user_permissions.add(Permission.objects.get(codename="change_document"))
        document = _make_served_notice(other_owner)
        other_client = APIClient()
        other_client.force_authenticate(user=other_owner)
        other_client.post(f"/api/documents/notice/{document.id}/rdsc-packet/")

        # self.owner has change_document too, but doesn't own this notice
        response = self.api_client.post(
            f"/api/documents/notice/{document.id}/rdsc-filing-task/complete/",
            {"rdc_case_reference": "RDC-2026-00042", "filed_date": "2026-09-05"},
        )
        self.assertEqual(response.status_code, 404)
