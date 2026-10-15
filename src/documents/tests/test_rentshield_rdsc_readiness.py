"""TDD tests for the RDSC factual compliance audit matrix (hard gate).

Three deterministic, binary checkpoints decide whether a served notice may be
compiled into an RDSC filing packet:

  A (Identity)  -- the owner's identity verification is VERIFIED, the passport
                   NFC chip was read (chip_document_number), and a face
                   comparison was computed (chip_selfie_match_score).
  B (Lease)     -- a registered Ejari certificate Document is linked to the
                   notice (ejari_certificate_document custom field).
  C (Delivery)  -- the notice is served (served_date) with a non-empty notary
                   reference OR a linked courier/registered-mail evidence doc.

can_compile = A and B and C, re-enforced server-side in the packet generator so
a client cannot bypass the greyed-out button.
"""

from __future__ import annotations

from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from documents.models import Document
from documents.rentshield.compliance import evaluate_rdsc_readiness
from documents.rentshield.service import _set_custom_field_value
from documents.rentshield_identity.models import IdentityVerification


def _make_notice(owner: User, **field_overrides) -> Document:
    document = Document.objects.create(
        owner=owner,
        title="Test Notice",
        checksum=f"rdsc-ready-{owner.username}-{field_overrides.get('_suffix', '')}",
        mime_type="application/pdf",
    )
    field_overrides.pop("_suffix", None)
    fields = {
        "landlord_name": "John Smith",
        "tenant_name": "Jane Tenant",
        "reason": "nonpayment",
        "notice_date": "2026-08-01",
        "notice_period_days": 30,
        **field_overrides,
    }
    for key, value in fields.items():
        _set_custom_field_value(document, key, value)
    return document


def _verify_identity(owner: User, **overrides) -> IdentityVerification:
    defaults = {
        "status": IdentityVerification.Status.VERIFIED,
        "chip_document_number": "C01X00T47",
        "chip_selfie_match_score": 0.91,
    }
    defaults.update(overrides)
    return IdentityVerification.objects.create(user=owner, **defaults)


def _make_fully_compliant_notice(owner: User) -> Document:
    """Owner identity verified + Ejari linked + served with a notary ref."""
    _verify_identity(owner)
    return _make_notice(
        owner,
        ejari_certificate_document=[101],
        served_date="2026-09-01",
        service_method="notary_public",
        notary_reference_no="NP-2026-5541",
    )


class TestCheckpointAIdentity(APITestCase):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(username="ckA-owner")

    def test_false_when_owner_has_no_identity_verification(self):
        doc = _make_notice(self.owner)
        result = evaluate_rdsc_readiness(doc)
        self.assertFalse(result["identity"])

    def test_true_when_verified_with_chip_and_face_score(self):
        _verify_identity(self.owner)
        doc = _make_notice(self.owner)
        self.assertTrue(evaluate_rdsc_readiness(doc)["identity"])

    def test_false_when_not_yet_verified(self):
        _verify_identity(self.owner, status=IdentityVerification.Status.AWAITING_NOTARY_REVIEW)
        doc = _make_notice(self.owner)
        self.assertFalse(evaluate_rdsc_readiness(doc)["identity"])

    def test_false_when_nfc_chip_not_read(self):
        _verify_identity(self.owner, chip_document_number="")
        doc = _make_notice(self.owner)
        self.assertFalse(evaluate_rdsc_readiness(doc)["identity"])

    def test_false_when_no_face_match_score(self):
        _verify_identity(self.owner, chip_selfie_match_score=None)
        doc = _make_notice(self.owner)
        self.assertFalse(evaluate_rdsc_readiness(doc)["identity"])


class TestCheckpointBLease(APITestCase):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(username="ckB-owner")

    def test_false_without_linked_ejari(self):
        doc = _make_notice(self.owner)
        self.assertFalse(evaluate_rdsc_readiness(doc)["lease"])

    def test_true_with_linked_ejari_certificate(self):
        doc = _make_notice(self.owner, ejari_certificate_document=[101])
        self.assertTrue(evaluate_rdsc_readiness(doc)["lease"])


class TestCheckpointCDelivery(APITestCase):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(username="ckC-owner")

    def test_false_when_not_served(self):
        doc = _make_notice(self.owner, notary_reference_no="NP-1")
        self.assertFalse(evaluate_rdsc_readiness(doc)["delivery"])

    def test_false_when_served_but_no_reference(self):
        doc = _make_notice(self.owner, served_date="2026-09-01")
        self.assertFalse(evaluate_rdsc_readiness(doc)["delivery"])

    def test_true_when_served_with_notary_reference(self):
        doc = _make_notice(self.owner, served_date="2026-09-01", notary_reference_no="NP-1")
        self.assertTrue(evaluate_rdsc_readiness(doc)["delivery"])

    def test_true_when_served_with_courier_evidence(self):
        doc = _make_notice(self.owner, served_date="2026-09-01", service_evidence_document=[7])
        self.assertTrue(evaluate_rdsc_readiness(doc)["delivery"])


class TestCanCompileGate(APITestCase):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(username="gate-owner")

    def test_false_for_bare_notice(self):
        doc = _make_notice(self.owner)
        result = evaluate_rdsc_readiness(doc)
        self.assertFalse(result["can_compile"])
        self.assertFalse(result["identity"])
        self.assertFalse(result["lease"])
        self.assertFalse(result["delivery"])

    def test_false_when_only_two_of_three_pass(self):
        # identity + lease, but not served
        _verify_identity(self.owner)
        doc = _make_notice(self.owner, ejari_certificate_document=[101])
        self.assertFalse(evaluate_rdsc_readiness(doc)["can_compile"])

    def test_true_when_all_three_pass(self):
        doc = _make_fully_compliant_notice(self.owner)
        result = evaluate_rdsc_readiness(doc)
        self.assertTrue(result["identity"])
        self.assertTrue(result["lease"])
        self.assertTrue(result["delivery"])
        self.assertTrue(result["can_compile"])

    def test_exposes_display_checkpoints(self):
        doc = _make_fully_compliant_notice(self.owner)
        result = evaluate_rdsc_readiness(doc)
        keys = {c["key"] for c in result["checkpoints"]}
        self.assertEqual(keys, {"identity", "lease", "delivery"})
        for c in result["checkpoints"]:
            self.assertIn("label", c)
            self.assertIn("ok", c)
            self.assertTrue(c["ok"])


class TestRdscReadinessEndpoint(APITestCase):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(username="ep-owner")
        self.owner.user_permissions.add(Permission.objects.get(codename="change_document"))

    def _url(self, doc_id: int) -> str:
        return f"/api/documents/notice/{doc_id}/rdsc-readiness/"

    def test_requires_authentication(self):
        doc = _make_notice(self.owner)
        self.assertEqual(self.client.get(self._url(doc.id)).status_code, 401)

    def test_404s_for_someone_elses_notice(self):
        other = User.objects.create_user(username="ep-other")
        doc = _make_notice(other)
        self.client.force_authenticate(user=self.owner)
        self.assertEqual(self.client.get(self._url(doc.id)).status_code, 404)

    def test_read_only_rejects_post(self):
        doc = _make_notice(self.owner)
        self.client.force_authenticate(user=self.owner)
        self.assertEqual(self.client.post(self._url(doc.id)).status_code, 405)

    def test_returns_all_false_for_bare_notice(self):
        doc = _make_notice(self.owner)
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get(self._url(doc.id))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["can_compile"])
        self.assertFalse(resp.data["identity"])

    def test_returns_can_compile_true_when_ready(self):
        doc = _make_fully_compliant_notice(self.owner)
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get(self._url(doc.id))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["can_compile"])


class TestServerSideGateEnforcement(APITestCase):
    """The generator itself must refuse when the gate is not satisfied, so a
    client bypassing the disabled button cannot force a packet."""

    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(username="gen-owner")
        self.owner.user_permissions.add(Permission.objects.get(codename="change_document"))

    def test_generator_raises_when_served_but_not_compliant(self):
        from documents.rentshield.service import generate_rdsc_filing_packet

        # served + notary ref (C passes) but no identity and no Ejari
        doc = _make_notice(self.owner, served_date="2026-09-01", notary_reference_no="NP-1")
        with self.assertRaises(ValueError):
            generate_rdsc_filing_packet(doc)

    def test_view_returns_400_when_not_compliant(self):
        doc = _make_notice(self.owner, served_date="2026-09-01", notary_reference_no="NP-1")
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(f"/api/documents/notice/{doc.id}/rdsc-packet/")
        self.assertEqual(resp.status_code, 400)
