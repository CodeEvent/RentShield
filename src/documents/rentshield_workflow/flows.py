# Wired into the live endpoint via rentshield_views.rdsc_packet_view and
# rentshield_views.rdsc_filing_complete_view. Evaluates django-viewflow
# as RentShield's workflow/case-management engine, starting with the
# RDSC filing lifecycle already built in
# documents/rentshield/rdsc_packet.py.
#
# LICENSING: django-viewflow's core is AGPLv3. RentShield itself is
# GPLv3 (inherited from the paperless-ngx fork, see repo LICENSE) and
# already public -- AGPLv3 section 13 and GPLv3 section 13 were written
# as a matched pair specifically to permit this combination, and AGPL's
# one addition over plain GPL (source must reach users who interact with
# it *over a network*, not just people who receive a copy) is already
# satisfied by the repo being public. No new obligation versus what the
# paperless-ngx fork already carries -- revisit only if RentShield ever
# goes closed-source, which GPLv3 already forecloses independent of
# viewflow.
#
# DESIGN: packet generation stays exactly as rdsc_packet_view already
# does it -- async, via service.generate_rdsc_filing_packet(), unchanged
# -- because viewflow's async/Celery node (`contrib.celery.Job`, used in
# its own cookbook examples) is PRO-only and not present in this
# installed (AGPL) distribution; only the synchronous Function node is
# available. Routing packet generation through a synchronous Function
# node here would make the "Generate Packet" button block on PDF
# rendering + document consumption instead of returning instantly, a
# real latency regression. So this flow is deliberately decoupled from
# generation: rdsc_packet_view fires its existing async dispatch
# unchanged, then separately starts this flow straight at
# record_filing -- the one capability that's actually new (nothing
# today tracks whether a generated packet was ever filed at rdc.gov.ae).
#
# record_filing is a Handle node, not a View: it's completed by calling
# RDSCFilingFlow.record_filing.run(task, ...) from
# rdsc_filing_complete_view -- a plain DRF endpoint using the exact same
# _get_visible_document_or_404 auth every other RentShield action uses
# -- rather than viewflow's own session-authenticated HTML form. That
# form was the live-tested first attempt at this (see git history): it
# required a *second*, separate Django session login the Angular app
# never establishes (it authenticates its own API calls a different
# way), needed its own assign-then-execute dance for a task with no
# auto-assigned owner, and even once reachable, rendered as a
# differently-styled page in a new tab. Handle has none of that: no
# HTTP form, no session, no assignment concept -- the calling view is
# the sole authority on who may complete it, exactly like every other
# RentShield action.
from django.utils.dateparse import parse_date
from django.utils.translation import gettext_lazy as _
from viewflow import this
from viewflow.workflow import flow
from viewflow.workflow import lock

from .models import RDSCFilingProcess


class RDSCFilingFlow(flow.Flow):
    """One RDSC filing per notice Document: started once a packet has been
    generated (by the existing, unchanged async endpoint); tracks whether
    the landlord's actual rdc.gov.ae filing has been recorded."""

    process_class = RDSCFilingProcess
    process_title = _("RDSC Filing")
    process_description = _(
        "Tracks whether a notice's RDSC filing packet was actually filed at rdc.gov.ae.",
    )
    process_summary_template = _("RDSC filing for notice #{{ process.document_id }}")
    process_result_template = _(
        "{% if process.rdc_case_reference %}"
        "Filed as {{ process.rdc_case_reference }} on {{ process.filed_date }}"
        "{% else %}Awaiting filing at rdc.gov.ae{% endif %}",
    )

    lock_impl = lock.select_for_update_lock

    # Started from code (rdsc_packet_view) once a packet has been
    # generated -- RDSCFilingFlow.start.run(document_id=document.pk) --
    # not from a user-facing "create" form, since the notice Document
    # already exists.
    start = flow.StartHandle(this.start_process).Next(this.record_filing)

    record_filing = (
        flow.Handle(this.complete_record_filing)
        .Annotation(
            title=_("Record RDC filing"),
            summary_template=_("Confirm the RDC filing for notice #{{ process.document_id }}"),
        )
        .Next(this.end)
    )

    end = flow.End().Annotation(title=_("Filed"))

    def start_process(self, activation, document_id: int):
        activation.process.document_id = document_id
        return activation.process

    def complete_record_filing(self, activation, rdc_case_reference: str, filed_date):
        activation.process.rdc_case_reference = rdc_case_reference
        # jsonstore.DateField requires an actual date, not the "YYYY-MM-DD"
        # string rdsc_filing_complete_view passes through from the request
        # body -- parse_date is a no-op for a caller that already passes a
        # real date (e.g. this flow's own tests).
        activation.process.filed_date = (
            parse_date(filed_date) if isinstance(filed_date, str) else filed_date
        )
        activation.process.save()
