# Guidance handoff for notarizing a notice REMOTELY via Dubai Courts'
# approved e-notary (notarization by video call) -- the counterpart to
# rdsc_packet.py on the filing side. Same honest design: there is no
# notary API to call, and RentShield is not itself the notary, so this
# does not notarize anything -- it tells the landlord exactly how to get
# the notice notarized remotely and which RentShield fields capture the
# result so the downstream RDSC packet (rdsc_packet.py) picks it up.
#
# Why this exists (2026-11): Dubai Courts run an approved e-notary that
# notarizes documents over a video call, and the RDC accepts a remotely
# notarized notice. Before this, RentShield only routed notices to its
# own in-house Notary Public queue (an async, upload-the-stamped-copy
# flow); landlords who wanted the faster official remote route had no
# guidance for it. Confirmed against Dubai Courts e-notary + RDC
# guidance, 2026-11.
from __future__ import annotations

import html as html_module

from documents.rentshield.constants import ALL_REASONS

# Tag applied to a generated remote-notarization handoff Document, mirroring
# rdsc_packet.RDSC_PACKET_TAG_NAME so both handoffs are findable the same way.
REMOTE_NOTARIZATION_TAG_NAME = "RentShield: Remote Notarization Handoff"

# What the landlord needs on the video call, in order. Kept as data so the
# steps can be rendered here and asserted in tests without parsing markup.
_STEPS = [
    "Have ready: your Emirates ID or passport, the Ejari certificate, and this "
    "notice (RentShield has generated and stored it).",
    "Book the Dubai Courts approved e-notary (notarization by video call) and "
    "join from a quiet, well-lit place -- the notary verifies your identity on "
    "camera, so some signers may still be asked to attend in person if remote "
    "identity verification cannot be completed.",
    "The notary notarizes the notice and issues a notarized copy plus a notary "
    "reference number.",
    "Serve the notarized notice on the tenant via Notary Public or registered "
    "mail, and keep the notification officer's report or the Emirates Post "
    "registered-post receipt -- that is the proof of service the RDC asks for.",
]

# Where each returned artifact is recorded in RentShield, so the RDSC filing
# packet (rdsc_packet.py) and the statutory clock (notice_builder.py) pick
# them up automatically.
_RECORD_INTO = [
    ("Notarized copy", "RentShield: Notarized Copy"),
    ("Notary reference number", "RentShield: Notary Reference No."),
    ("Served date (starts the statutory notice period)", "RentShield: Served Date"),
]


def _esc(value) -> str:
    return html_module.escape(str(value) if value is not None else "")


def render_remote_notarization_handoff_html(fields: dict) -> str:
    reason_meta = ALL_REASONS.get(fields.get("reason"))
    reason_label = reason_meta["label"] if reason_meta else fields.get("reason")

    steps = "\n".join(f"<li>{_esc(step)}</li>" for step in _STEPS)
    records = "\n".join(
        f'<li><strong>{_esc(label)}</strong> &rarr; stored as "{_esc(field_name)}"</li>'
        for label, field_name in _RECORD_INTO
    )

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: 'Times New Roman', serif; color: #1a1a1a; line-height: 1.6; padding: 40px; }}
  .kicker {{ text-transform: uppercase; letter-spacing: 0.08em; font-size: 11px; color: #666; }}
  h1 {{ font-size: 22px; margin: 4px 0; }}
  h2 {{ font-size: 15px; margin: 20px 0 6px; }}
  .meta {{ margin: 16px 0; font-size: 13px; }}
  .meta td {{ padding: 2px 12px 2px 0; }}
  ol, ul {{ font-size: 13px; }}
  .footer {{ font-size: 11px; color: #666; margin-top: 24px; }}
</style>
</head>
<body>
  <p class="kicker">Remote Notarization -- How-To Handoff</p>
  <h1>{_esc(reason_label)} &mdash; {_esc(fields.get("tenant_name"))}</h1>
  <table class="meta">
    <tr><td>Landlord</td><td>{_esc(fields.get("landlord_name"))}</td></tr>
    <tr><td>Ejari No.</td><td>{_esc(fields.get("ejari_number") or "not recorded")}</td></tr>
    <tr><td>Notice Date</td><td>{_esc(fields.get("notice_date"))}</td></tr>
  </table>
  <p>Dubai Courts run an approved e-notary that notarizes documents over a
  video call, and the RDC accepts a remotely notarized eviction notice. To
  notarize this notice remotely:</p>
  <h2>Steps</h2>
  <ol>{steps}</ol>
  <h2>What RentShield records from the result</h2>
  <ul>{records}</ul>
  <p class="footer">RentShield does not notarize this notice and is not the
  notary -- notarization is performed by the Dubai Courts approved notary.
  This is guidance only; book the e-notary through the official Dubai Courts
  service.</p>
</body>
</html>"""


def build_remote_notarization_handoff(fields: dict) -> bytes:
    from documents.rentshield.pdf import render_html_to_pdf

    return render_html_to_pdf(render_remote_notarization_handoff_html(fields))
