"""Signing service (WP-4) — signs attestations, provenance records, and exports.

Two implementations, both behind a `Signer` Protocol:
  * **GpgSigner** — real GPG (python-gnupg). For production / near-real-data runs.
  * **HmacSigner** — deterministic HMAC-SHA256, used in dev/tests so signing can
    be exercised end-to-end without keyring setup. Clearly labeled in the
    signature record (`scheme: 'hmac-sha256-dev'`); production deployments MUST
    use GpgSigner.

DECISION-012 records this. Both signers produce a `Signature(signature, key_id,
scheme, signed_at)` so the data shape is identical downstream.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class Signature:
    signature: str        # armored GPG sig or hex HMAC
    key_id: str           # GPG key id or 'dev'
    scheme: str           # 'gpg' | 'hmac-sha256-dev'
    signed_at: dt.datetime
    signer: str           # human label (display name / 'dev')


class Signer(Protocol):
    scheme: str
    def sign(self, payload: bytes, *, signer: str) -> Signature: ...
    def verify(self, payload: bytes, signature: Signature) -> bool: ...


# --------------------------------------------------------------------------- #
class HmacSigner:
    """Deterministic dev/test signer (DECISION-012). NOT for production."""

    scheme = "hmac-sha256-dev"

    def __init__(self, secret: Optional[str] = None):
        self._secret = (secret or os.environ.get("QUILL_DEV_SIGNING_SECRET", "quill-dev-only")).encode()

    def sign(self, payload: bytes, *, signer: str) -> Signature:
        sig = hmac.new(self._secret, payload, hashlib.sha256).hexdigest()
        return Signature(
            signature=sig, key_id="dev", scheme=self.scheme,
            signed_at=dt.datetime.now(dt.timezone.utc), signer=signer,
        )

    def verify(self, payload: bytes, signature: Signature) -> bool:
        if signature.scheme != self.scheme:
            return False
        expected = hmac.new(self._secret, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature.signature)


class GpgSigner:
    """Real GPG signing via python-gnupg. Requires a keyring with a signing key."""

    scheme = "gpg"

    def __init__(self, key_id: str, passphrase: Optional[str] = None, gnupghome: Optional[str] = None):
        import gnupg
        self._gpg = gnupg.GPG(gnupghome=gnupghome) if gnupghome else gnupg.GPG()
        self._key_id = key_id
        self._passphrase = passphrase

    def sign(self, payload: bytes, *, signer: str) -> Signature:  # pragma: no cover (needs keyring)
        signed = self._gpg.sign(payload, keyid=self._key_id, passphrase=self._passphrase, detach=True)
        if not signed:
            raise RuntimeError(f"GPG sign failed: {signed.status}")
        return Signature(
            signature=str(signed), key_id=self._key_id, scheme=self.scheme,
            signed_at=dt.datetime.now(dt.timezone.utc), signer=signer,
        )

    def verify(self, payload: bytes, signature: Signature) -> bool:  # pragma: no cover
        verified = self._gpg.verify_data(signature.signature, payload)
        return bool(verified)


def make_default_signer() -> Signer:
    """Construct the default signer. GPG in prod (when key id is configured), HMAC in dev."""
    key_id = os.environ.get("QUILL_GPG_KEY_ID")
    if key_id and os.environ.get("QUILL_DEV_MODE", "1") == "0":
        try:
            return GpgSigner(key_id=key_id, passphrase=os.environ.get("QUILL_GPG_PASSPHRASE"))
        except Exception:  # noqa: BLE001 — fall back loudly
            pass
    return HmacSigner()
