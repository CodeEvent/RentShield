# Seeds scenario-rich RentShield demo data: notices driven into distinct
# end-states (served, notarized, arrears active/cured/expired, RDSC-ready vs
# blocked, disputed) plus identity verifications in several review states, so
# every lifecycle feature -- the arrears grace-period auto-void and the RDSC
# compliance gate included -- has real, visible, workable data.
#
# Everything is built through the same service code paths real usage goes
# through (documents.rentshield.service.generate_and_consume /
# write_and_consume, the ArrearsPayment auto-void signal), so the demo
# exercises exactly what production does. Every object carries the
# 'Demo Data' tag, and every user it creates is prefixed 'demo_', so --reset
# can remove all of it cleanly and nothing real is touched.
from __future__ import annotations

from datetime import date
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.utils import timezone

from documents.models import Document
from documents.models import Tag
from documents.rentshield.custom_fields import DEMO_DATA_TAG_NAME
from documents.rentshield.custom_fields import TENANCY_CONTRACT_TAG_NAME
from documents.rentshield.document_analysis import DocumentAnalysisError
from documents.rentshield.roles import PROPERTY_OWNER_GROUP_NAME
from documents.rentshield.service import _set_custom_field_value
from documents.rentshield.service import generate_and_consume
from documents.rentshield.service import run_ai_review
from documents.rentshield.service import write_and_consume
from documents.rentshield_billing.models import ArrearsGracePeriod
from documents.rentshield_billing.models import ArrearsLedgerEvent
from documents.rentshield_billing.models import ArrearsPayment
from documents.rentshield_identity.models import IdentityVerification

User = get_user_model()
TODAY = date.today()
DEMO_USER_PREFIX = "demo_"


def _d(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).isoformat()


def _future(days_ahead: int) -> str:
    return (TODAY + timedelta(days=days_ahead)).isoformat()


class Command(BaseCommand):
    help = (
        "Seeds scenario-rich RentShield demo data (notices in distinct "
        "end-states, arrears ledgers, RDSC-ready/blocked notices, identity "
        "verifications). Use --reset to first remove all existing demo data "
        "(everything tagged 'Demo Data' and every 'demo_' user)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Remove existing demo data before seeding.",
        )
        parser.add_argument(
            "--reset-only",
            action="store_true",
            help="Remove existing demo data and stop (do not seed).",
        )

    # ------------------------------------------------------------------ #
    # entry point
    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        if options["reset"] or options["reset_only"]:
            self._reset()
        if options["reset_only"]:
            return

        if Tag.objects.filter(name=DEMO_DATA_TAG_NAME).exists():
            self.stdout.write(
                self.style.WARNING(
                    f"A '{DEMO_DATA_TAG_NAME}' tag already exists -- demo data is "
                    "present. Re-run with --reset to replace it.",
                ),
            )
            return

        self.demo_tag = Tag.objects.create(name=DEMO_DATA_TAG_NAME, color="#94a3b8")
        self.admin = User.objects.filter(is_superuser=True).order_by("id").first()
        self.admin_id = self.admin.id if self.admin else None

        self.stdout.write(self.style.HTTP_INFO("Seeding scenario demo data...\n"))
        self._seed_owners_and_identities()
        self._seed_notice_scenarios()
        self._seed_contracts()
        self.stdout.write(self.style.SUCCESS("\nDone. Filter by the 'Demo Data' tag to find everything."))

    # ------------------------------------------------------------------ #
    # removal
    # ------------------------------------------------------------------ #
    def _reset(self):
        self.stdout.write(self.style.HTTP_INFO("Removing existing demo data..."))

        demo_users = list(User.objects.filter(username__startswith=DEMO_USER_PREFIX))
        # Arrears ledgers owned by demo users (events cascade via collector).
        gp = ArrearsGracePeriod.objects.filter(owner__in=demo_users)
        n_events = ArrearsLedgerEvent.objects.filter(grace_period__in=gp).count()
        gp_count = gp.count()
        gp.delete()

        docs = Document.objects.filter(tags__name=DEMO_DATA_TAG_NAME)
        n_docs = docs.count()
        for doc in docs:
            doc.delete()

        n_iv = IdentityVerification.objects.filter(user__in=demo_users).count()
        n_users = len(demo_users)
        for u in demo_users:
            u.delete()  # cascades identity verification, any owned docs

        Tag.objects.filter(name=DEMO_DATA_TAG_NAME).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"  removed: {n_docs} documents, {n_users} demo users, "
                f"{n_iv} identity records, {gp_count} arrears ledgers "
                f"({n_events} timeline events).\n",
            ),
        )

    # ------------------------------------------------------------------ #
    # owners + identity verifications
    # ------------------------------------------------------------------ #
    def _seed_owners_and_identities(self):
        owner_group, _ = Group.objects.get_or_create(name=PROPERTY_OWNER_GROUP_NAME)

        def make_owner(uname, email):
            u, _ = User.objects.get_or_create(
                username=DEMO_USER_PREFIX + uname,
                defaults={"email": email},
            )
            u.groups.add(owner_group)
            return u

        # Verified owner -- backs the RDSC-ready and cured-arrears notices.
        self.owner_verified = make_owner("owner_verified", "verified.owner@example.com")
        IdentityVerification.objects.get_or_create(
            user=self.owner_verified,
            defaults={
                "status": IdentityVerification.Status.VERIFIED,
                "chip_document_number": "C01X00T47",
                "chip_selfie_match_score": 0.93,
                "automated_result": "verified",
                "notary_reviewed_at": timezone.now() - timedelta(days=12),
            },
        )
        # Owner still awaiting the Notary's review.
        self.owner_pending = make_owner("owner_pending", "pending.owner@example.com")
        IdentityVerification.objects.get_or_create(
            user=self.owner_pending,
            defaults={
                "status": IdentityVerification.Status.AWAITING_NOTARY_REVIEW,
                "chip_document_number": "D22Y91Z00",
                "chip_selfie_match_score": 0.88,
                "automated_result": "manual_review",
            },
        )
        # Owner the Notary bounced back for more info.
        self.owner_moreinfo = make_owner("owner_moreinfo", "moreinfo.owner@example.com")
        IdentityVerification.objects.get_or_create(
            user=self.owner_moreinfo,
            defaults={
                "status": IdentityVerification.Status.NEEDS_MORE_INFO,
                "chip_document_number": "",
                "notary_notes": "Chip read did not complete -- please re-scan the passport.",
            },
        )
        self.stdout.write("  identities: 1 verified, 1 awaiting review, 1 needs-more-info")

    # ------------------------------------------------------------------ #
    # notice scenarios
    # ------------------------------------------------------------------ #
    def _notice(self, fields, owner_id):
        doc = generate_and_consume(dict(fields), owner_id=owner_id, synchronous=True)
        doc.tags.add(self.demo_tag)
        return doc

    def _ejari_doc(self, owner_id, label):
        """A stand-in registered-Ejari certificate document, for the
        ejari_certificate_document link that RDSC Checkpoint B needs."""
        doc = write_and_consume(
            f"EJARI TENANCY CONTRACT REGISTRATION\n\n{label}\nRegistered with RERA.\n",
            f"Ejari Certificate - {label}.txt",
            title=f"Ejari Certificate - {label}",
            owner_id=owner_id,
            tag_ids=[self.demo_tag.id],
            synchronous=True,
        )
        return doc

    def _seed_notice_scenarios(self):
        made = []

        # S1 -- Draft: generated, not served. (sale)
        s1 = self._notice(
            {
                "landlord_name": "Ahmed Al Maktoum", "tenant_name": "Sarah Mitchell",
                "property_type": "Apartment", "unit_no": "1204",
                "building_name": "Marina Heights Tower", "ejari_number": "204938271",
                "contract_expiry": _future(90),
                "notice_date": _d(5), "reason": "sale",
            },
            self.admin_id,
        )
        made.append(("Draft / not served", s1))

        # S2 -- Served via Notary Public (personal use).
        s2 = self._notice(
            {
                "landlord_name": "Fatima Al Suwaidi", "tenant_name": "David Chen",
                "property_type": "Villa", "plot_number": "3311-0921",
                "building_name": "Al Barsha Villa 12", "ejari_number": "119284736",
                "contract_expiry": _future(200),
                "notice_date": _d(25), "reason": "personal", "add_real_notarization": True,
            },
            self.admin_id,
        )
        _set_custom_field_value(s2, "service_method", "notary_public")
        _set_custom_field_value(s2, "notary_status", "completed")
        _set_custom_field_value(s2, "notary_reference_no", "NP-2026-0442")
        _set_custom_field_value(s2, "served_date", _d(18))
        made.append(("Served via Notary", s2))

        # S3 -- Served via registered mail, with evidence doc linked.
        s3 = self._notice(
            {
                "landlord_name": "Mohammed Al Rashid", "tenant_name": "Jessica Park",
                "property_type": "Office", "unit_no": "1502",
                "building_name": "Business Bay Tower B", "ejari_number": "556677889",
                "contract_expiry": _future(330),
                "notice_date": _d(34), "reason": "demolition",
            },
            self.admin_id,
        )
        evidence = self._ejari_doc(self.admin_id, "Business Bay 1502 service receipt")
        _set_custom_field_value(s3, "service_method", "registered_mail")
        _set_custom_field_value(s3, "service_evidence_document", [evidence.id])
        _set_custom_field_value(s3, "served_date", _d(27))
        made.append(("Served via registered mail", s3))

        # S4 -- Non-payment, arrears grace period ACTIVE, one partial payment.
        s4 = self._notice(
            {
                "landlord_name": "Omar Sharif", "tenant_name": "Linda Davis",
                "property_type": "Apartment", "unit_no": "802",
                "building_name": "Downtown Views", "ejari_number": "334455667",
                "contract_expiry": _future(60),
                "notice_date": _d(8), "reason": "nonpayment", "arrears_amount_aed": 48000,
            },
            self.owner_verified.id,
        )
        _set_custom_field_value(s4, "served_date", _d(6))
        _set_custom_field_value(s4, "notary_reference_no", "NP-2026-0501")
        gp4 = ArrearsGracePeriod.open_for_notice(
            owner=self.owner_verified, document_id=s4.id,
            opening_balance_aed=48000, property_ref="334455667",
            served_at=timezone.now() - timedelta(days=6),
        )
        ArrearsPayment.objects.create(grace_period=gp4, amount_aed=18000, balance_after_aed=30000)
        made.append(("Non-payment: grace ACTIVE", s4))

        # S5 -- Non-payment CURED/VOIDED: payment clears arrears within window.
        s5 = self._notice(
            {
                "landlord_name": "Layla Hassan", "tenant_name": "Robert Wilson",
                "property_type": "Apartment", "unit_no": "45B",
                "building_name": "Discovery Gardens", "ejari_number": "112233445",
                "contract_expiry": _future(150),
                "notice_date": _d(12), "reason": "nonpayment", "arrears_amount_aed": 22000,
            },
            self.owner_verified.id,
        )
        _set_custom_field_value(s5, "served_date", _d(9))
        gp5 = ArrearsGracePeriod.open_for_notice(
            owner=self.owner_verified, document_id=s5.id,
            opening_balance_aed=22000, property_ref="112233445",
            served_at=timezone.now() - timedelta(days=9),
        )
        # Clearing payment within the window -> auto-void signal fires.
        ArrearsPayment.objects.create(grace_period=gp5, amount_aed=22000, balance_after_aed=0)
        made.append(("Non-payment: CURED / VOIDED", s5))

        # S6 -- Non-payment grace EXPIRED: served 40 days ago, still owed.
        s6 = self._notice(
            {
                "landlord_name": "Khalid Al Falasi", "tenant_name": "Emma Taylor",
                "property_type": "Villa", "plot_number": "AR-0456",
                "building_name": "Arabian Ranches Villa 7", "ejari_number": "667788990",
                "contract_expiry": _future(280),
                "notice_date": _d(44), "reason": "nonpayment", "arrears_amount_aed": 60000,
            },
            self.owner_verified.id,
        )
        _set_custom_field_value(s6, "served_date", _d(40))
        gp6 = ArrearsGracePeriod.open_for_notice(
            owner=self.owner_verified, document_id=s6.id,
            opening_balance_aed=60000, property_ref="667788990",
            served_at=timezone.now() - timedelta(days=40),
        )
        gp6.status = ArrearsGracePeriod.Status.EXPIRED
        gp6.save(update_fields=["status"])
        ArrearsLedgerEvent.record(
            grace_period=gp6, event_type=ArrearsLedgerEvent.EventType.EXPIRED,
            message="Cure window closed with arrears still outstanding. The notice stands.",
        )
        made.append(("Non-payment: grace EXPIRED", s6))

        # S7 -- RDSC-READY: verified owner + Ejari linked + served + notary ref.
        s7 = self._notice(
            {
                "landlord_name": "Noura Al Marri", "tenant_name": "James Anderson",
                "property_type": "Townhouse", "unit_no": "12",
                "building_name": "JVC District 08", "ejari_number": "223344556",
                "contract_expiry": _future(400),
                "notice_date": _d(30), "reason": "sale", "add_real_notarization": True,
            },
            self.owner_verified.id,
        )
        ejari7 = self._ejari_doc(self.owner_verified.id, "JVC District 08 Unit 12")
        _set_custom_field_value(s7, "ejari_certificate_document", [ejari7.id])
        _set_custom_field_value(s7, "service_method", "notary_public")
        _set_custom_field_value(s7, "notary_status", "completed")
        _set_custom_field_value(s7, "notary_reference_no", "NP-2026-0588")
        _set_custom_field_value(s7, "served_date", _d(22))
        made.append(("RDSC-READY (gate opens)", s7))

        # S8 -- RDSC-BLOCKED: served, but owner unverified and no Ejari linked.
        s8 = self._notice(
            {
                "landlord_name": "Yousef Al Nahyan", "tenant_name": "Grace Lee",
                "property_type": "Apartment", "unit_no": "309",
                "building_name": "Silicon Oasis Residences", "ejari_number": "445566778",
                "contract_expiry": _future(120),
                "notice_date": _d(16), "reason": "sale",
            },
            self.owner_pending.id,  # identity only AWAITING review -> Checkpoint A fails
        )
        _set_custom_field_value(s8, "served_date", _d(10))
        _set_custom_field_value(s8, "notary_reference_no", "NP-2026-0599")
        made.append(("RDSC-BLOCKED (gate stays locked)", s8))

        # S9 -- Disputed: a 30-day sublease breach, served, flagged disputed.
        s9 = self._notice(
            {
                "landlord_name": "Hind Al Mazrouei", "tenant_name": "Thomas White",
                "property_type": "Apartment", "unit_no": "77C",
                "building_name": "International City France", "ejari_number": "889900112",
                "contract_expiry": _future(220),
                "notice_date": _d(50), "reason": "sublease",
            },
            self.admin_id,
        )
        _set_custom_field_value(s9, "service_method", "court_bailiff")
        _set_custom_field_value(s9, "served_date", _d(43))
        _set_custom_field_value(s9, "notice_state", "Disputed at RDSC")
        made.append(("Disputed at RDSC", s9))

        for label, doc in made:
            self.stdout.write(self.style.SUCCESS(f"  notice [{label}] -> #{doc.id} {doc.title}"))

    # ------------------------------------------------------------------ #
    # contracts (pass / fail / pending AI review)
    # ------------------------------------------------------------------ #
    def _seed_contracts(self):
        # One contract that fails AI review (7-day clause + verbal service), one
        # that passes cleanly. Reviewed through the real run_ai_review path.
        contracts = [
            {
                "title": "Tenancy Contract - Golden Sands Building",
                "text": (
                    "TENANCY CONTRACT\n\nUnit 903, Golden Sands Building, Al Nahda, "
                    "Dubai. Ejari No. 5544332211.\n"
                    "Term: terminable by either party on 7 days written notice.\n"
                    "Service of Notice: the Landlord may serve notice verbally.\n"
                    "Rent: AED 85,000 per annum.\n"
                ),
            },
            {
                "title": "Tenancy Contract - Marina View Tower",
                "text": (
                    "TENANCY CONTRACT\n\nUnit 2210, Marina View Tower, Dubai Marina. "
                    "Ejari No. 9988776655.\n"
                    "Term: 365 days written notice, per Law No. (33) of 2008.\n"
                    "Service of Notice: registered mail with acknowledgment, or a "
                    "Notary Public.\nRent: AED 145,000 per annum.\n"
                ),
            },
        ]
        tenancy_tag, _ = Tag.objects.get_or_create(
            name=TENANCY_CONTRACT_TAG_NAME, defaults={"color": "#6366f1"},
        )
        for c in contracts:
            doc = write_and_consume(
                c["text"], f"{c['title']}.txt", title=c["title"],
                owner_id=self.admin_id, tag_ids=[self.demo_tag.id, tenancy_tag.id],
                synchronous=True,
            )
            try:
                result = run_ai_review(doc)
                verdict = "non-compliant" if result["has_violation"] else "compliant"
                self.stdout.write(self.style.SUCCESS(f"  contract [{verdict}] -> {doc.title}"))
            except DocumentAnalysisError as exc:
                self.stdout.write(
                    self.style.WARNING(
                        f"  contract [AI review pending] -> {doc.title} "
                        f"(docling-service unreachable: {exc})",
                    ),
                )
