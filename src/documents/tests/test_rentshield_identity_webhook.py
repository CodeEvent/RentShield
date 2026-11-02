from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from documents.rentshield_identity.models import IdentityVerification

WEBHOOK_URL = "/api/documents/identity/verify/webhook/"


class TestIdswyftWebhookStatusGate(APITestCase):
    """The unauthenticated Idswyft status webhook must only be able to move
    a verification to the states Idswyft's automated pipeline produces --
    never to VERIFIED or NEEDS_MORE_INFO, which are human-only outcomes a
    Notary sets. Otherwise anyone who learns a verification_id could POST
    status=verified and skip the mandatory Notary review."""

    def setUp(self):
        self.user = get_user_model().objects.create(username="webhook_owner")
        self.record = IdentityVerification.objects.create(
            user=self.user,
            verification_id="idsw-abc-001",
            status=IdentityVerification.Status.AWAITING_NOTARY_REVIEW,
        )

    def _post(self, status_value):
        return self.client.post(
            WEBHOOK_URL,
            {"verification_id": "idsw-abc-001", "status": status_value},
            format="json",
        )

    def test_webhook_cannot_promote_to_verified(self):
        resp = self._post("verified")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.record.refresh_from_db()
        self.assertEqual(
            self.record.status,
            IdentityVerification.Status.AWAITING_NOTARY_REVIEW,
        )

    def test_webhook_cannot_set_needs_more_info(self):
        resp = self._post("needs_more_info")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.record.refresh_from_db()
        self.assertEqual(
            self.record.status,
            IdentityVerification.Status.AWAITING_NOTARY_REVIEW,
        )

    def test_webhook_accepts_automated_pipeline_states(self):
        for value in ("pending", "manual_review", "failed"):
            with self.subTest(status=value):
                resp = self._post(value)
                self.assertEqual(resp.status_code, status.HTTP_200_OK)
                self.record.refresh_from_db()
                self.assertEqual(self.record.status, value)
