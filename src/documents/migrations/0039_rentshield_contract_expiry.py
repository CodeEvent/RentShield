# Expiry date of the registered Ejari tenancy contract.
#
# "RentShield: Contract Expiry" gives each notice the contract-expiry date
# the frontend needs to compute the Notice Window (the 365-day statutory
# buffer before expiry, Article 25) and to show a real "contract ends" date
# in the property workspace -- notices previously carried no such date, so
# the Notice Window widget stayed hidden for real data.
#
# Mirrors documents.rentshield.custom_fields.CUSTOM_FIELD_DEFS -- kept as a
# plain literal here (not imported), same reasoning as every migration since
# 0026. Idempotent (get_or_create by name).
from django.db import migrations


def create_field(apps, schema_editor):
    CustomField = apps.get_model("documents", "CustomField")

    CustomField.objects.get_or_create(
        name="RentShield: Contract Expiry",
        defaults={"data_type": "date", "extra_data": None},
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0038_rentshield_arrears_fields"),
    ]

    operations = [
        migrations.RunPython(create_field, noop_reverse),
    ]
