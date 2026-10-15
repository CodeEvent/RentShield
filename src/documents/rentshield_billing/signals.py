from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from documents.rentshield_billing.models import ArrearsLedgerEvent
from documents.rentshield_billing.models import ArrearsPayment

logger = logging.getLogger("paperless.rentshield.arrears")


def _mark_notice_cured(document_id: int) -> None:
    """Reflect the void onto the notice Document's "Notice State" custom field.

    Lazily imports from documents.* at call time (never at module load) so the
    one-way dependency rule in apps.py holds. Guarded: the ledger is the source
    of truth, so a failure to stamp the Document is logged, not raised -- it
    must never roll back the cure.
    """
    try:
        from documents.models import Document
        from documents.rentshield.service import _set_custom_field_value

        document = Document.objects.filter(id=document_id).first()
        if document is None:
            logger.warning("Arrears cure: notice Document %s not found.", document_id)
            return
        _set_custom_field_value(document, "notice_state", "Cured/Voided")
    except Exception:  # noqa: BLE001
        logger.exception("Arrears cure: failed to stamp Notice State on document %s", document_id)


@receiver(post_save, sender=ArrearsPayment, dispatch_uid="rentshield_arrears_autovoid")
def evaluate_cure_on_payment(sender, instance: ArrearsPayment, created: bool, **kwargs) -> None:
    """Database listener: every logged payment is recorded, and if it drops the
    balance to zero on or before the deadline while the window is still active,
    the notice is auto-voided (Article 25(1) cure). Deterministic -- a balance
    check and a date comparison, nothing else."""
    if not created:
        return

    gp = instance.grace_period

    # Always record the payment on the immutable timeline.
    ArrearsLedgerEvent.record(
        grace_period=gp,
        event_type=ArrearsLedgerEvent.EventType.PAYMENT,
        message=(
            f"Payment logged: AED {instance.amount_aed} received, "
            f"AED {instance.balance_after_aed} outstanding."
        ),
    )

    # Only an active window can be cured.
    if gp.status != gp.Status.ACTIVE:
        return

    balance_cleared = instance.balance_after_aed <= 0
    within_window = instance.logged_at <= gp.deadline

    if balance_cleared and within_window:
        gp.status = gp.Status.CURED
        gp.cured_at = timezone.now()
        gp.save(update_fields=["status", "cured_at"])

        _mark_notice_cured(gp.document_id)

        ArrearsLedgerEvent.record(
            grace_period=gp,
            event_type=ArrearsLedgerEvent.EventType.CURED,
            message=(
                "Notice auto-voided: arrears cleared within the 30-day cure "
                f"window (deadline {gp.deadline:%d %b %Y}). Status set to Cured/Voided."
            ),
        )
        logger.info("Arrears grace period #%s cured; notice %s voided.", gp.pk, gp.document_id)
    elif balance_cleared and not within_window:
        # Paid in full but too late -- the notice stands; note it, do not void.
        ArrearsLedgerEvent.record(
            grace_period=gp,
            event_type=ArrearsLedgerEvent.EventType.PAYMENT,
            message=(
                "Arrears cleared AFTER the 30-day cure window closed "
                f"(deadline {gp.deadline:%d %b %Y}). The notice is not voided."
            ),
        )
