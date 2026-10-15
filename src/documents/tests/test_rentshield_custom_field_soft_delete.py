"""Regression test for a real bug hit live (2026-09-23) while testing the
RDSC filing-packet button: documents.rentshield.service._set_custom_field_value()
used update_or_create() against CustomFieldInstance's default manager,
which -- because CustomFieldInstance is a django_softdelete SoftDeleteModel
-- filters out soft-deleted rows. Re-setting a field whose earlier value
had been trashed (e.g. via paperless-ngx's own UI) tried to INSERT a
fresh row and hit the real DB-level unique constraint on
(document_id, field_id) that the soft-deleted row still occupies,
raising an IntegrityError instead of just setting the value."""

from __future__ import annotations

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from documents.models import CustomFieldInstance
from documents.models import Document
from documents.rentshield.custom_fields import key_to_id_map
from documents.rentshield.service import _set_custom_field_value


class TestSetCustomFieldValueAfterSoftDelete(APITestCase):
    def setUp(self):
        super().setUp()
        owner = User.objects.create_user(username="soft-delete-test-owner")
        self.document = Document.objects.create(
            owner=owner, title="Soft Delete Test", checksum="soft-delete-test-doc", mime_type="application/pdf",
        )

    def test_resetting_a_field_after_its_earlier_value_was_trashed_does_not_raise(self):
        _set_custom_field_value(self.document, "served_date", "2026-09-01")
        field_id = key_to_id_map()["served_date"]
        instance = CustomFieldInstance.objects.get(document=self.document, field_id=field_id)
        instance.delete()  # soft-delete, same as paperless-ngx's own trash

        self.assertFalse(CustomFieldInstance.objects.filter(document=self.document, field_id=field_id).exists())

        _set_custom_field_value(self.document, "served_date", "2026-09-20")

        restored = CustomFieldInstance.objects.get(document=self.document, field_id=field_id)
        self.assertEqual(str(restored.value_date), "2026-09-20")
        self.assertIsNone(restored.deleted_at)

    def test_setting_a_field_that_was_never_set_before_still_works(self):
        _set_custom_field_value(self.document, "served_date", "2026-09-01")
        field_id = key_to_id_map()["served_date"]
        instance = CustomFieldInstance.objects.get(document=self.document, field_id=field_id)
        self.assertEqual(str(instance.value_date), "2026-09-01")
