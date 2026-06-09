"""Phase II — synonym engine (FR-XA-01 / FR-XA-05 / FR-XA-06)."""
from pathlib import Path

import pytest

from backend.services.analysis.synonyms import Synonyms, empty, load_synonyms

ROOT = Path(__file__).resolve().parents[2]
PROD_TABLE = ROOT / "config" / "synonyms.yaml"


def test_canonical_round_trip_frequencies():
    s = load_synonyms(PROD_TABLE)
    # Every 90 days normalizes to quarterly
    assert s.canonical("every 90 days") == "quarterly"
    assert s.canonical("EVERY 90 DAYS") == "quarterly"  # case-insensitive
    assert s.canonical("every three months") == "quarterly"
    # Annually family
    assert s.canonical("yearly") == "annually"
    assert s.canonical("once a year") == "annually"
    # Unknown phrase passes through
    assert s.canonical("every leap year") == "every leap year"


def test_canonical_round_trip_roles():
    s = load_synonyms(PROD_TABLE)
    assert s.canonical("Information System Security Officer") == "ISSO"
    assert s.canonical("ISSO") == "ISSO"
    assert s.canonical("CHIEF INFORMATION SECURITY OFFICER") == "CISO"


def test_canonical_round_trip_authenticators():
    s = load_synonyms(PROD_TABLE)
    assert s.canonical("Personal Identity Verification") == "PIV"
    assert s.canonical("multi-factor authentication") == "MFA"
    assert s.canonical("two-factor authentication") == "MFA"
    assert s.canonical("Common Access Card") == "CAC"


def test_canonicalize_all_rewrites_phrases_in_text():
    s = load_synonyms(PROD_TABLE)
    text = "The ISSO reviews accounts every 90 days using MFA."
    out = s.canonicalize_all(text)
    assert "quarterly" in out
    # Already-canonical forms stay
    assert "ISSO" in out
    assert "MFA" in out
    # No double-rewrite or word-internal matches
    assert "the issoo" not in out.lower()


def test_find_canonical_phrases_extracts_set():
    s = load_synonyms(PROD_TABLE)
    text = "Accounts reviewed every 90 days by the Information System Security Officer."
    found = s.find_canonical_phrases(text)
    assert "quarterly" in found
    assert "ISSO" in found


def test_greedy_match_prefers_longer_phrase():
    # "every 3 months" should win over "every month" (which is in `monthly`).
    s = load_synonyms(PROD_TABLE)
    assert s.canonical("every 3 months") == "quarterly"
    found = s.find_canonical_phrases("Reviewed every 3 months by audit.")
    assert "quarterly" in found
    assert "monthly" not in found


def test_word_boundaries_no_mid_word_match():
    s = load_synonyms(PROD_TABLE)
    # "PIV" must not match inside "incipivote" (fake word) — guards against false-positives.
    assert "PIV" not in s.find_canonical_phrases("incipivote")
    # But "PIV card" inside a normal sentence does match.
    assert "PIV" in s.find_canonical_phrases("Issued a PIV card to the user.")


def test_empty_table_is_no_op():
    s = empty()
    assert s.canonical("anything") == "anything"
    assert s.canonicalize_all("foo bar baz") == "foo bar baz"
    assert s.find_canonical_phrases("foo bar baz") == set()


def test_load_synonyms_missing_file_is_empty():
    s = load_synonyms("/tmp/this-does-not-exist-1234567.yaml")
    assert s.canonical("ISSO") == "ISSO"  # unchanged
    assert s.find_canonical_phrases("ISSO every 90 days") == set()
