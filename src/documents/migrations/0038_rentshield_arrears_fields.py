# Arrears grace-period support (Article 25(1), non-payment).
#
# "RentShield: Notice State" records lifecycle beyond served/esign/notary --
# today only the arrears auto-void writes it ("Cured/Voided").
# "RentShield: Arrears Amount (AED)" is the outstanding balance at service,
# the opening balance of documents.rentshield_billing's grace-period ledger.
#
# Mirrors documents.rentshield.custom_fields.CUSTOM_FIELD_DEFS -- kept as a
# plain literal here (not imported), same reasoning as every migration since
# 0026. Idempotent (get_or_create by name).
from django.db import migrations


def create_fields(apps, schema_editor):
    CustomField = apps.get_model("documents", "CustomField")

    CustomField.objects.get_or_create(
        name="RentShield: Notice State",
        defaults={"data_type": "string", "extra_data": None},
    )
    CustomField.objects.get_or_create(
        name="RentShield: Arrears Amount (AED)",
        defaults={"data_type": "integer", "extra_data": None},
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0037_rentshield_rdsc_fields"),
    ]

    operations = [
        migrations.RunPython(create_fields, noop_reverse),
    ]
