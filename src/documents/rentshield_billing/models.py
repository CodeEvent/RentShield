from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Order(models.Model):
    """One payment for one notice-generation request. Created BEFORE the
    notice exists (pending payment), and generate_and_consume() only
    ever fires once this row's status flips to PAID/DEMO_PAID -- see
    documents/rentshield_billing/views.py and
    documents.tasks.finalize_paid_notice_task. `fields` is the exact
    payload create_notice_view already validates, snapshotted here so
    the notice generated after payment matches exactly what was quoted
    and paid for, not whatever the form happens to hold by the time
    payment confirms."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        DEMO_PAID = "demo_paid", "Paid (demo)"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rentshield_orders",
    )
    fields = models.JSONField(help_text="Notice-creation payload this order is for.")
    amount_aed = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True, default="")
    # Nullable FK to documents.Document -- no direct model import to
    # avoid a rentshield_billing <-> documents circular import at
    # module load time (documents already imports plenty from
    # documents.rentshield; this app should stay a one-way dependency:
    # rentshield_billing can be imported by documents code, not the
    # other way around).
    document_id = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Order #{self.pk} ({self.status}, AED {self.amount_aed})"


# ---------------------------------------------------------------------------
# Arrears grace-period ledger (Article 25(1), non-payment)
#
# A 30-day non-payment notice is a breach notice, not a termination: under
# Article 25(1) of Law No. (33) of 2008 the tenant can "cure" the breach by
# clearing the arrears within the statutory window, which voids the notice.
# This ledger makes that deterministic: when such a notice is served we open a
# grace period; every payment the landlord logs is recorded; and the moment a
# logged payment drops the balance to zero on or before the deadline, the
# notice is auto-voided and the action is written to an append-only timeline.
# No heuristics, no AI -- pure date and balance arithmetic.
# ---------------------------------------------------------------------------

# Article 25(1) cure window, in days, from the service date.
ARREARS_GRACE_DAYS = 30


class ArrearsGracePeriod(models.Model):
    """The cure window opened against one served non-payment notice."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CURED = "cured", "Cured / Voided"
        EXPIRED = "expired", "Expired"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rentshield_arrears_periods",
    )
    # Nullable FK-by-id to documents.Document, same one-way-dependency
    # discipline as Order.document_id above (no model import here).
    document_id = models.PositiveIntegerField(
        help_text="The non-payment notice Document this grace period is for.",
    )
    # Free-text handle for the property (Ejari no. / unit), for display only.
    property_ref = models.CharField(max_length=255, blank=True, default="")
    opening_balance_aed = models.PositiveIntegerField(
        help_text="Outstanding arrears at the moment the notice was served.",
    )
    served_at = models.DateTimeField(help_text="Service date -- start of the cure window.")
    deadline = models.DateTimeField(help_text="served_at + ARREARS_GRACE_DAYS.")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    cured_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["status", "deadline"])]

    def __str__(self) -> str:
        return f"ArrearsGracePeriod #{self.pk} (doc {self.document_id}, {self.status})"

    @property
    def is_within_window(self) -> bool:
        return timezone.now() <= self.deadline

    @classmethod
    def open_for_notice(
        cls,
        *,
        owner,
        document_id: int,
        opening_balance_aed: int,
        property_ref: str = "",
        served_at=None,
    ) -> "ArrearsGracePeriod":
        """Open (or return the existing active) grace period for a served
        non-payment notice. Idempotent per document: a notice served twice
        does not create a second active window."""
        existing = cls.objects.filter(
            document_id=document_id,
            status=cls.Status.ACTIVE,
        ).first()
        if existing is not None:
            return existing

        served_at = served_at or timezone.now()
        gp = cls.objects.create(
            owner=owner,
            document_id=document_id,
            property_ref=property_ref,
            opening_balance_aed=opening_balance_aed,
            served_at=served_at,
            deadline=served_at + timedelta(days=ARREARS_GRACE_DAYS),
        )
        ArrearsLedgerEvent.record(
            grace_period=gp,
            document_id=document_id,
            event_type=ArrearsLedgerEvent.EventType.OPENED,
            message=(
                f"Arrears grace period opened: AED {opening_balance_aed} outstanding, "
                f"cure deadline {gp.deadline:%d %b %Y}."
            ),
        )
        return gp


class ArrearsPayment(models.Model):
    """A rent payment a landlord logs against an open grace period. Saving one
    is the database event the auto-void listener reacts to (see signals.py)."""

    grace_period = models.ForeignKey(
        ArrearsGracePeriod,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    amount_aed = models.PositiveIntegerField(help_text="Amount received in this payment.")
    balance_after_aed = models.PositiveIntegerField(
        help_text="Outstanding arrears remaining AFTER this payment. 0 cures the notice.",
    )
    logged_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"ArrearsPayment AED {self.amount_aed} -> balance {self.balance_after_aed}"


class ArrearsLedgerEvent(models.Model):
    """Append-only, immutable audit row. Written by the grace-period logic and
    never updated or deleted -- save() rejects edits and delete() is blocked,
    so the timeline is a faithful, tamper-evident record of what happened."""

    class EventType(models.TextChoices):
        OPENED = "opened", "Grace period opened"
        PAYMENT = "payment_logged", "Payment logged"
        CURED = "cured_voided", "Cured / Voided"
        EXPIRED = "expired", "Expired"

    grace_period = models.ForeignKey(
        ArrearsGracePeriod,
        on_delete=models.CASCADE,
        related_name="events",
        null=True,
        blank=True,
    )
    document_id = models.PositiveIntegerField(null=True, blank=True)
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {self.event_type}: {self.message}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("ArrearsLedgerEvent rows are immutable and cannot be edited.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("ArrearsLedgerEvent rows are immutable and cannot be deleted.")

    @classmethod
    def record(cls, *, event_type, message, grace_period=None, document_id=None):
        return cls.objects.create(
            grace_period=grace_period,
            document_id=document_id if document_id is not None else (grace_period.document_id if grace_period else None),
            event_type=event_type,
            message=message,
        )
