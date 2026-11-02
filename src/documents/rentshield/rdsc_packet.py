# Assembles a filing-packet cover sheet for Dubai's Rental Dispute
# Settlement Centre (RDC/RDSC) online portal (rdc.gov.ae) once a notice
# has been served and the tenant hasn't complied -- NOT an RDC API
# integration (no public API exists) and NOT the RDC claim form itself
# (that's filed directly at rdc.gov.ae). This just tells the landlord
# exactly what that portal will ask for and whether RentShield already
# has it linked, so they aren't hunting for documents from scratch.
from __future__ import annotations

import datetime
import html as html_module

from documents.rentshield.constants import ALL_REASONS
from documents.rentshield.dates import format_date_en
from documents.rentshield.dates import get_expiry_date
from documents.rentshield.pdf import render_html_to_pdf
from documents.rentshield.service_methods import SERVICE_METHODS

# Tag applied to every generated packet Document -- shared between
# rentshield_views.rdsc_packet_view (the live API) and
# rentshield_workflow.flows.RDSCFilingFlow (the viewflow prototype), both
# of which go through service.generate_rdsc_filing_packet() below.
RDSC_PACKET_TAG_NAME = "RentShield: RDSC Filing Packet"

# RDC's own published fee rule (3.5% of annual rent, min AED 500, max AED
# 20,000) -- stated as reference, never computed: RentShield has no field
# for the actual annual rent amount, and inventing one just for a fee
# estimate here would be scope this feature doesn't need.
_RDC_FEE_NOTE = "RDC's filing fee is 3.5% of the annual rent (minimum AED 500, maximum AED 20,000), payable when you file."

# The two official channels a landlord can file through, and the RDC's own
# remote-hearing option -- stated as guidance, never automated (there is no
# public RDC API; RentShield hands the landlord a ready checklist, it does
# not submit on their behalf). Confirmed against RDC guidance 2026-11.
_FILING_CHANNELS_NOTE = (
    "File directly through either official channel: the RDC online portal "
    "(rdc.gov.ae) or the Dubai REST app. Hearings may be attended remotely "
    "through the RDC's tele-litigation system."
)


def _esc(value) -> str:
    return html_module.escape(str(value) if value is not None else "")


def _proof_of_service(fields: dict, service_method_key, service_method_label):
    """The RDC wants the notarized notice plus service evidence specific to
    how it was served: a Notary Public's notification officer's report, or
    the Emirates Post registered-post receipt. Returns (present, note)."""
    has_evidence = bool(fields.get("service_evidence_document"))
    if service_method_key == "notary_public":
        return True, "served via Notary Public -- attach the notification officer's report"
    if service_method_key == "registered_mail":
        note = (
            "registered mail -- attach the Emirates Post registered-post receipt"
            if has_evidence
            else "registered mail -- Emirates Post registered-post receipt not linked yet"
        )
        return has_evidence, note
    return has_evidence, service_method_label or "no service method recorded yet"


def _filing_readiness(fields: dict) -> str:
    """When the landlord may actually file: only once the notice has been
    served AND its period has elapsed (the period runs from the served
    date -- see notice_builder). Computed from served_date + the notice's
    own period, never guessed."""
    served = fields.get("served_date")
    try:
        period_days = int(fields["notice_period_days"]) if fields.get("notice_period_days") else None
    except (TypeError, ValueError):
        period_days = None
    if not served:
        return (
            "This notice has not been served yet. Serve it (Notary Public or "
            "registered mail) and record the served date before filing at the RDC."
        )
    effective = get_expiry_date(served, period_days) if period_days else None
    if not effective:
        return "Served, but the notice period is not recorded, so the earliest filing date cannot be computed."
    if datetime.date.today() >= effective:
        return f"The notice period elapsed on {format_date_en(effective)}; you may file at the RDC now."
    return f"The notice period has not yet elapsed. You may file at the RDC on or after {format_date_en(effective)}."


def _checklist_row(label: str, present: bool, note: str = "") -> str:
    mark = "&#10003;" if present else "&#9633;"
    status_class = "rs-present" if present else "rs-missing"
    detail = f" -- {_esc(note)}" if note else ""
    return f'<li class="{status_class}"><span class="rs-mark">{mark}</span> {_esc(label)}{detail}</li>'


def render_rdsc_packet_html(fields: dict) -> str:
    reason_meta = ALL_REASONS.get(fields.get("reason"))
    reason_label = reason_meta["label"] if reason_meta else fields.get("reason")

    service_method_key = fields.get("service_method")
    service_method_label = (
        SERVICE_METHODS[service_method_key]["label"]
        if service_method_key in SERVICE_METHODS
        else None
    )

    checklist = "\n".join(
        [
            _checklist_row(
                "Ejari certificate",
                bool(fields.get("ejari_certificate_document")),
                f"Ejari No. {fields['ejari_number']}" if fields.get("ejari_number") else "not linked on this notice yet",
            ),
            _checklist_row(
                "Tenancy contract",
                bool(fields.get("tenancy_contract_document")),
                "" if fields.get("tenancy_contract_document") else "not linked on this notice yet",
            ),
            _checklist_row(
                "This notice itself",
                True,
                "generated and stored by RentShield",
            ),
            _checklist_row(
                "Proof of service",
                *_proof_of_service(fields, service_method_key, service_method_label),
            ),
        ],
    )

    readiness = _filing_readiness(fields)

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: 'Times New Roman', serif; color: #1a1a1a; line-height: 1.6; padding: 40px; }}
  .kicker {{ text-transform: uppercase; letter-spacing: 0.08em; font-size: 11px; color: #666; }}
  h1 {{ font-size: 22px; margin: 4px 0; }}
  .meta {{ margin: 16px 0; font-size: 13px; }}
  .meta td {{ padding: 2px 12px 2px 0; }}
  ul.rs-checklist {{ list-style: none; padding: 0; font-size: 13px; }}
  ul.rs-checklist li {{ padding: 4px 0; }}
  .rs-mark {{ display: inline-block; width: 1.4em; }}
  .rs-present {{ color: #0a7a3d; }}
  .rs-missing {{ color: #b23b1f; }}
  .footer {{ font-size: 11px; color: #666; margin-top: 24px; }}
</style>
</head>
<body>
  <p class="kicker">RDSC Filing Packet -- Reference Checklist</p>
  <h1>{_esc(reason_label)} &mdash; {_esc(fields.get("tenant_name"))}</h1>
  <table class="meta">
    <tr><td>Landlord</td><td>{_esc(fields.get("landlord_name"))}</td></tr>
    <tr><td>Ejari No.</td><td>{_esc(fields.get("ejari_number") or "not recorded")}</td></tr>
    <tr><td>Notice Date</td><td>{_esc(fields.get("notice_date"))}</td></tr>
    <tr><td>Notice Period</td><td>{_esc(fields.get("notice_period_days"))} days</td></tr>
    <tr><td>Served Date</td><td>{_esc(fields.get("served_date") or "not recorded")}</td></tr>
    <tr><td>Service Method</td><td>{_esc(service_method_label or "not recorded")}</td></tr>
  </table>
  <p>What Dubai's Rental Dispute Settlement Centre online portal (rdc.gov.ae) asks for, and whether it's linked on this notice today:</p>
  <ul class="rs-checklist">{checklist}</ul>
  <p class="readiness"><strong>When you can file:</strong> {_esc(readiness)}</p>
  <p><strong>How to file:</strong> {_esc(_FILING_CHANNELS_NOTE)}</p>
  <p>{_esc(_RDC_FEE_NOTE)}</p>
  <p class="footer">This is a reference checklist generated by RentShield, not a court filing and not submitted to RDC on your behalf -- file directly at rdc.gov.ae (or via the Dubai REST app) using the documents above.</p>
</body>
</html>"""


def build_rdsc_packet(fields: dict) -> bytes:
    return render_html_to_pdf(render_rdsc_packet_html(fields))
