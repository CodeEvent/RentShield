"""Seed a self-contained RentShield demo: one Property Owner account with
a VERIFIED identity and a handful of notices across two properties in
varied states (served/matured, served/in-period, draft breach), so every
data-driven tab (Overview, Notices, Verification, Disputes, Compliance,
Documents) has real content.

Built for the free GitHub Codespaces demo (.devcontainer), where the
sqlite DB starts empty and PAPERLESS_AUTO_LOGIN_USERNAME logs every
visitor straight in as this demo owner -- no OTP, no password.

Idempotent: re-running wipes this demo user's existing notices and
recreates them, so a Codespace rebuild always lands in the same state.
It never touches real accounts (only the `demo` user).

Each notice is created through the real pipeline when Playwright (the PDF
renderer) is available, and falls back to a metadata-only Document -- same
tag + custom fields, no rendered PDF -- when it is not, so the demo
populates on a lean container that has no browser engine installed.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

DEMO_USERNAME = "demo"


class Command(BaseCommand):
    help = "Seed the RentShield demo account, identity and notices (idempotent)."

    def handle(self, *args, **options):
        from documents.models import Document
        from documents.models import Tag
        from documents.rentshield.custom_fields import RENTSHIELD_TAG_NAME
        from documents.rentshield.roles import grant_property_owner
        from documents.rentshield.service import _set_custom_field_value
        from documents.rentshield_identity.models import IdentityVerification as IV

        User = get_user_model()

        with transaction.atomic():
            user, created = User.objects.get_or_create(
                username=DEMO_USERNAME,
                defaults={
                    "email": "demo@rentshield.example",
                    "first_name": "Fatima",
                    "last_name": "Al Zaabi",
                    "is_active": True,
                },
            )
            user.set_unusable_password()
            user.save()
            grant_property_owner(user)
            self.stdout.write(f"demo user: {user.username} (id {user.id}, {'created' if created else 'existing'})")

            IV.objects.update_or_create(
                user=user,
                defaults=dict(
                    status=IV.Status.VERIFIED,
                    provider="idswyft",
                    declared_document_number="A12345678",
                    declared_date_of_birth="1985-06-12",
                    chip_document_number="A12345678",
                    chip_full_name="Fatima Al Zaabi",
                    chip_selfie_match_score=0.93,
                    automated_result="verified",
                ),
            )
            self.stdout.write("identity: VERIFIED")

            # Clean slate for this demo user's notices (never other users').
            rs_tag, _ = Tag.objects.get_or_create(
                name=RENTSHIELD_TAG_NAME,
                defaults={"color": "#10b981"},
            )
            Document.objects.filter(owner=user, tags=rs_tag).delete()

        base = dict(
            landlord_name="Fatima Al Zaabi",
            landlord_email="demo@rentshield.example",
            property_type="Apartment",
        )
        notices = [
            # Marina Heights 1203 -- served + matured statutory notice (RDSC-ready)
            dict(tenant_name="Omar Haddad", reason="sale", notice_date="2025-05-10",
                 notice_period_days=365, unit_no="1203", building_name="Marina Heights",
                 plot_number="345-1", ejari_number="DXB-2025-11234", contract_expiry="2026-05-01",
                 served_date="2025-06-01", service_method="notary_public",
                 notary_reference_no="NP-2025-8842"),
            # Marina Heights 1203 -- breach draft (not served)
            dict(tenant_name="Omar Haddad", reason="nonpayment", notice_date="2026-11-01",
                 notice_period_days=30, unit_no="1203", building_name="Marina Heights",
                 plot_number="345-1", ejari_number="DXB-2025-11234", arrears_amount_aed="42000"),
            # Downtown Views 708 -- renovation, served (in-period)
            dict(tenant_name="Layla Nasser", reason="renovation", notice_date="2026-10-01",
                 notice_period_days=365, unit_no="708", building_name="Downtown Views",
                 plot_number="DT-77", ejari_number="DXB-2026-07788", contract_expiry="2026-09-15",
                 served_date="2026-10-05", service_method="registered_mail"),
            # Downtown Views 708 -- personal-use draft
            dict(tenant_name="Layla Nasser", reason="personal", notice_date="2026-11-02",
                 notice_period_days=365, unit_no="708", building_name="Downtown Views",
                 plot_number="DT-77", ejari_number="DXB-2026-07788"),
        ]

        made = []
        for fields in notices:
            doc = self._make_notice(user, rs_tag, {**base, **fields})
            made.append(doc.id)
        self.stdout.write(self.style.SUCCESS(f"seeded {len(made)} demo notices: {made}"))

    def _make_notice(self, user, rs_tag, fields: dict):
        """Real pipeline if Playwright is available; metadata-only Document
        otherwise. Either way the notice carries the RentShield tag and all
        its custom field values, which is what the tabs read."""
        from documents.models import Document
        from documents.rentshield.service import _set_custom_field_value

        extra_keys = (
            "served_date", "service_method", "notary_reference_no",
            "contract_expiry", "arrears_amount_aed",
        )
        extras = {k: fields[k] for k in extra_keys if k in fields}
        core = {k: v for k, v in fields.items() if k not in extra_keys}

        try:
            from documents.rentshield.service import generate_and_consume

            doc = generate_and_consume(core, owner_id=user.id, synchronous=True)
        except Exception as exc:  # noqa: BLE001 -- lean container without the PDF engine
            self.stdout.write(self.style.WARNING(f"  PDF pipeline unavailable ({exc}); metadata-only notice"))
            reason = core.get("reason", "notice")
            doc = Document.objects.create(
                owner=user,
                title=f"Notice ({reason}) - {core.get('tenant_name', 'Tenant')}",
                checksum=f"demo-{user.id}-{core.get('unit_no','x')}-{reason}-{core.get('notice_date','')}",
                mime_type="application/pdf",
            )
            doc.tags.add(rs_tag)
            for k, v in core.items():
                _set_custom_field_value(doc, k, v)

        for k, v in extras.items():
            _set_custom_field_value(doc, k, v)
        return doc
