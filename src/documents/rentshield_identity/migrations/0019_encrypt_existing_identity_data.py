"""Rewrite any rows that predate field-level encryption so their
sensitive columns hold ciphertext, not cleartext.

0018 only changed the column type (CharField/TextField -> the encrypted
field). Existing rows still hold plaintext at that point; the encrypted
field reads them back fine (from_db_value falls back to the raw value on
an InvalidToken), but they are not yet protected at rest. Re-saving each
row runs the value back through the field's get_prep_value, which
encrypts it. Idempotent: a value that is already a token decrypts on read
and re-encrypts on save, so running this twice is harmless.
"""

from __future__ import annotations

from django.db import migrations

# The encrypted columns on each model, by model name within this app.
_ENCRYPTED_FIELDS = {
    "IdentityVerification": [
        "declared_document_number",
        "declared_date_of_birth",
        "declared_expiry_date",
        "declared_can",
        "card_ocr_full_name",
        "card_ocr_date_of_birth",
        "card_ocr_document_number",
        "chip_full_name",
        "chip_date_of_birth",
        "chip_document_number",
        "identity_mismatch_notes",
        "notary_notes",
        "ai_prescreen_summary",
    ],
    "NoticeSignerVerification": ["signer_name", "ocr_full_name"],
    "TotpDevice": ["secret"],
}


def encrypt_existing(apps, schema_editor):
    for model_name, fields in _ENCRYPTED_FIELDS.items():
        model = apps.get_model("rentshield_identity", model_name)
        for row in model.objects.all().iterator():
            # Reading already decrypted the values (or returned plaintext
            # untouched); saving them re-encrypts via get_prep_value.
            row.save(update_fields=fields)


def noop_reverse(apps, schema_editor):
    # Cannot (and must not) turn ciphertext back into plaintext columns.
    # The encrypted field still reads transparently if the schema is
    # reverted, so there is nothing to undo here.
    pass


class Migration(migrations.Migration):
    dependencies = [
        (
            "rentshield_identity",
            "0018_alter_identityverification_ai_prescreen_summary_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(encrypt_existing, noop_reverse),
    ]
