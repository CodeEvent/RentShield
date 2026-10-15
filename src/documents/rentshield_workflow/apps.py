# Prototype: evaluates django-viewflow (AGPLv3 -- see flows.py docstring)
# as a workflow/case-management engine for RentShield's multi-step notice
# lifecycle, starting with the RDSC filing flow. Same reasoning as
# rentshield_identity/apps.py and rentshield_billing/apps.py for being a
# separate installed app: RDSCFilingProcess needs its own viewflow Process
# row (task list, status, history) independent of Document/CustomField.
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RentshieldWorkflowConfig(AppConfig):
    name = "documents.rentshield_workflow"
    label = "rentshield_workflow"
    verbose_name = _("RentShield Workflow (viewflow prototype)")
