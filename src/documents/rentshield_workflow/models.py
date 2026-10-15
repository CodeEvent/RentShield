from django.utils.translation import gettext_lazy as _
from viewflow import jsonstore
from viewflow.workflow.models import Process

from documents.models import Document


class RDSCFilingProcess(Process):
    """Tracks one notice's path through Dubai's Rental Dispute Settlement
    Centre filing process: packet generated -> (landlord files at
    rdc.gov.ae themselves, outside RentShield) -> filing recorded back
    here. A `proxy` model over viewflow's own Process table (like
    HelloWorldProcess in viewflow's own cookbook) -- document_id and the
    RDC filing details are jsonstore fields, so this needs no migration
    of its own beyond viewflow.workflow's, and the source notice stays a
    plain Document/CustomField row exactly as everywhere else in
    RentShield (see documents/rentshield/service.py's read_notice_fields).
    """

    document_id = jsonstore.IntegerField(_("Notice document"))
    rdc_case_reference = jsonstore.CharField(_("RDC case reference"), max_length=100, blank=True)
    filed_date = jsonstore.DateField(_("Filed at rdc.gov.ae on"), null=True, blank=True)

    class Meta:
        proxy = True
        verbose_name = _("RDSC Filing")
        verbose_name_plural = _("RDSC Filings")

    @property
    def document(self) -> Document:
        return Document.objects.get(pk=self.document_id)
