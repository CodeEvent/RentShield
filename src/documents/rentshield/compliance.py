"""RDSC factual compliance audit matrix -- a deterministic, binary hard gate.

Before a served notice can be compiled into an RDSC filing packet, three
checkpoints must ALL be true. Every check reads real database state; there is
no scoring, no heuristic and no AI -- the same inputs always give the same
booleans.

  A (Identity)  The owner's identity verification is VERIFIED (a Notary Public
                sign-off), the passport NFC chip was actually read
                (chip_document_number present), and a face comparison was
                computed (chip_selfie_match_score is not null).
  B (Lease)     A registered Ejari certificate Document is linked to the notice
                via the "RentShield: Ejari Certificate" custom field.
  C (Delivery)  The notice is served (served_date set) with either a non-empty
                notary reference number OR a linked courier/registered-mail
                service-evidence Document.

can_compile = A and B and C.

NOTE ON FIELD MAPPING: the identity model has no literal `passport_nfc_valid` /
`face_liveness_match` columns. Those plan concepts map onto the real evidence
fields above; the mapping is surfaced in each checkpoint's `detail` so it stays
auditable.
"""

from __future__ import annotations

from documents.models import Document
from documents.rentshield.service import read_notice_fields


def _identity_ok(owner) -> tuple[bool, str]:
    """Checkpoint A: VERIFIED + NFC chip read + face comparison computed."""
    if owner is None:
        return False, "No owner on this notice."

    from documents.rentshield_identity.models import IdentityVerification

    iv = IdentityVerification.objects.filter(user=owner).first()
    if iv is None:
        return False, "Owner has no identity verification on file."

    verified = iv.status == IdentityVerification.Status.VERIFIED
    nfc_valid = bool((iv.chip_document_number or "").strip())
    face_liveness = iv.chip_selfie_match_score is not None

    if not verified:
        return False, f"Identity not verified (status: {iv.status})."
    if not nfc_valid:
        return False, "Passport NFC chip was not read."
    if not face_liveness:
        return False, "No face/liveness comparison on record."
    return True, "Owner verified: NFC chip read and face match on record."


def _lease_ok(fields: dict) -> tuple[bool, str]:
    """Checkpoint B: a registered Ejari certificate is linked to the notice."""
    if fields.get("ejari_certificate_document"):
        ejari_no = fields.get("ejari_number")
        suffix = f" (Ejari No. {ejari_no})" if ejari_no else ""
        return True, f"Registered Ejari certificate linked{suffix}."
    return False, "No registered Ejari certificate linked to this notice."


def _delivery_ok(fields: dict) -> tuple[bool, str]:
    """Checkpoint C: served, with a notary reference or courier evidence."""
    served = bool(fields.get("served_date"))
    if not served:
        return False, "Notice has not been served."

    has_notary_ref = bool((fields.get("notary_reference_no") or "").strip())
    has_courier_evidence = bool(fields.get("service_evidence_document"))
    if has_notary_ref:
        return True, f"Served; notary reference {fields.get('notary_reference_no')}."
    if has_courier_evidence:
        return True, "Served; courier/registered-mail evidence on file."
    return False, "Served, but no notary reference or courier evidence recorded."


def evaluate_rdsc_readiness(document: Document) -> dict:
    """Evaluate the three checkpoints and the master gate for one notice.

    Returns top-level booleans (identity/lease/delivery/can_compile) plus a
    `checkpoints` list for display (key, label, ok, detail).
    """
    fields = read_notice_fields(document)

    identity, identity_detail = _identity_ok(document.owner)
    lease, lease_detail = _lease_ok(fields)
    delivery, delivery_detail = _delivery_ok(fields)
    can_compile = identity and lease and delivery

    return {
        "identity": identity,
        "lease": lease,
        "delivery": delivery,
        "can_compile": can_compile,
        "checkpoints": [
            {
                "key": "identity",
                "label": "Owner identity verified",
                "ok": identity,
                "detail": identity_detail,
            },
            {
                "key": "lease",
                "label": "Registered Ejari linked",
                "ok": lease,
                "detail": lease_detail,
            },
            {
                "key": "delivery",
                "label": "Notice served with proof",
                "ok": delivery,
                "detail": delivery_detail,
            },
        ],
    }
