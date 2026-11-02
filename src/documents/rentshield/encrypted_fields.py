"""Transparent at-rest encryption for the handful of model fields that
hold a secret or a piece of regulated personal data (a TOTP shared
secret, a passport/ID number, a date of birth, a name read off an ID
document). Everything stays a normal Django field from the model's point
of view -- you read and write plaintext -- but what lands in the database
column is a Fernet token, so a leaked database dump or a stolen backup
never exposes the cleartext.

Why Fernet (cryptography.fernet), not a bespoke scheme: it is AES-128-CBC
with an HMAC-SHA256 authentication tag and a random IV per value, from a
library already in the dependency tree. MultiFernet gives us key rotation
for free -- the first key encrypts, every key can decrypt -- so a future
`PAPERLESS_FIELD_ENCRYPTION_KEY=new,old` rolls the key without a data
migration.

Key source, in order of preference:
  1. PAPERLESS_FIELD_ENCRYPTION_KEY -- one or more comma-separated Fernet
     keys (urlsafe-base64, 32 bytes). Generate one with:
         python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  2. Otherwise a key deterministically derived from SECRET_KEY, so local
     development and the test suite work with no extra configuration. This
     is only ever a fallback: settings.py warns loudly if it is used while
     DEBUG is off, because rotating SECRET_KEY would then silently strip
     the ability to decrypt every stored value.

Legacy/plaintext tolerance: from_db_value tries to decrypt and, on an
InvalidToken, returns the raw column value unchanged. That makes turning
a plain CharField into an encrypted one a pure schema change -- existing
plaintext rows keep reading correctly, and the one-off data migration
(or the next save of each row) rewrites them as ciphertext. It also means
a decrypt never hard-crashes a page over one bad row.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken
from cryptography.fernet import MultiFernet
from django.conf import settings
from django.db import models


@lru_cache(maxsize=1)
def _cipher() -> MultiFernet:
    """Build the MultiFernet once and cache it. The keys come from
    settings.RS_FIELD_ENCRYPTION_KEYS (a non-empty list of str/bytes
    Fernet keys), which settings.py is responsible for populating."""
    keys = getattr(settings, "RS_FIELD_ENCRYPTION_KEYS", None)
    if not keys:
        raise RuntimeError(
            "RS_FIELD_ENCRYPTION_KEYS is empty; field-level encryption cannot "
            "run. settings.py should always populate it (deriving from "
            "SECRET_KEY as a last resort).",
        )
    fernets = [Fernet(k.encode() if isinstance(k, str) else k) for k in keys]
    return MultiFernet(fernets)


def _reset_cipher_cache() -> None:
    """Drop the cached cipher -- used by tests that override the keys."""
    _cipher.cache_clear()


class EncryptedFieldMixin:
    """Encrypt on the way to the database, decrypt on the way back.

    The DB column is always TEXT (a Fernet token is longer than, and a
    different shape from, the plaintext), so concrete fields below extend
    TextField regardless of how short the cleartext is."""

    def from_db_value(self, value, expression, connection):  # noqa: ARG002
        if value is None:
            return value
        token = value.encode("utf-8") if isinstance(value, str) else value
        try:
            return _cipher().decrypt(token).decode("utf-8")
        except (InvalidToken, ValueError, TypeError):
            # Not a token we wrote (legacy plaintext, or a value stored
            # before this field was encrypted). Hand it back untouched so
            # the migration can rewrite it and no page 500s on one row.
            return value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None:
            return value
        if not isinstance(value, str):
            value = str(value)
        return _cipher().encrypt(value.encode("utf-8")).decode("utf-8")


class EncryptedCharField(EncryptedFieldMixin, models.TextField):
    """Drop-in replacement for a CharField holding a short secret or ID
    (TOTP secret, passport/document number, date of birth, name). Stored
    encrypted; still presented as a single-line value to the app."""


class EncryptedTextField(EncryptedFieldMixin, models.TextField):
    """Drop-in replacement for a TextField holding free-text that may
    contain personal data (mismatch notes, AI pre-screen summary)."""
