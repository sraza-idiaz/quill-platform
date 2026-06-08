"""Signing service tests (WP-4 / DECISION-012)."""
from backend.services.gpg_signer import HmacSigner


def test_hmac_sign_and_verify_roundtrip():
    s = HmacSigner(secret="test")
    sig = s.sign(b"payload", signer="alice")
    assert s.verify(b"payload", sig) is True


def test_hmac_rejects_modified_payload():
    s = HmacSigner(secret="test")
    sig = s.sign(b"payload", signer="alice")
    assert s.verify(b"PAYLOAD_TAMPERED", sig) is False


def test_hmac_rejects_wrong_secret():
    s1 = HmacSigner(secret="a")
    s2 = HmacSigner(secret="b")
    sig = s1.sign(b"x", signer="alice")
    assert s2.verify(b"x", sig) is False


def test_scheme_label_is_dev():
    sig = HmacSigner().sign(b"x", signer="alice")
    assert sig.scheme == "hmac-sha256-dev"   # explicitly NOT for production
