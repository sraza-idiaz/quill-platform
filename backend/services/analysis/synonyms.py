"""Synonym resolution — Phase II FR-XA-01 / FR-XA-05 / FR-XA-06.

A `Synonyms` table normalizes equivalent expressions to a single canonical
form so downstream comparisons (cross-artifact consistency, ODP value-family
consistency, role-name resolution) don't false-positive on surface-form
variation.

Examples (loaded from `config/synonyms.yaml`):
    "every 90 days" → "quarterly"
    "Information System Security Officer" → "ISSO"
    "Personal Identity Verification card" → "PIV"

The table is config-driven (P-CONFIG-01 / NFR-MNT-01): adding a synonym is a
YAML edit, never a code change.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional

import yaml


class Synonyms:
    """Loaded synonym table. `canonical(s)` returns the canonical form of any
    member; `canonicalize_all(text)` rewrites every recognized phrase in a
    block of text to its canonical form.
    """

    def __init__(self, classes: list[dict]) -> None:
        # member (lowercase) -> canonical form. Longer phrases tried first.
        self._member_to_canonical: dict[str, str] = {}
        self._members_longest_first: list[str] = []
        for cls in classes:
            canonical = cls["canonical"]
            for member in cls.get("members", []):
                m = member.strip().lower()
                if not m:
                    continue
                self._member_to_canonical[m] = canonical
        # Sort by length desc so greedy match prefers "every 90 days" over "90 days".
        self._members_longest_first = sorted(
            self._member_to_canonical.keys(), key=len, reverse=True
        )
        # Compile one big alternation regex with word boundaries (or punctuation/space
        # boundaries) so the matcher catches phrases without matching mid-word.
        if self._members_longest_first:
            escaped = [re.escape(m) for m in self._members_longest_first]
            # \b doesn't fire around hyphens/non-word boundaries; use a wider boundary.
            self._pattern = re.compile(
                r"(?<![A-Za-z0-9])(?:" + "|".join(escaped) + r")(?![A-Za-z0-9])",
                re.IGNORECASE,
            )
        else:
            self._pattern = None

    # ─── single-token canonicalization ─────────────────────────────────── #
    def canonical(self, token: str) -> str:
        """Return the canonical form of `token`, or `token` unchanged if not
        in the table. Case-insensitive."""
        return self._member_to_canonical.get(token.strip().lower(), token)

    def is_known(self, token: str) -> bool:
        return token.strip().lower() in self._member_to_canonical

    # ─── multi-phrase rewriting ────────────────────────────────────────── #
    def canonicalize_all(self, text: str) -> str:
        """Rewrite every recognized phrase in `text` to its canonical form.
        Used by Tier 0's cross-artifact consistency check so that
        'every 90 days' and 'quarterly' compare equal."""
        if not self._pattern or not text:
            return text
        return self._pattern.sub(
            lambda m: self._member_to_canonical[m.group(0).lower()], text
        )

    def find_canonical_phrases(self, text: str) -> set[str]:
        """Return the set of canonical forms found in `text`. Useful when you
        want to know *which* equivalence classes a segment mentions without
        rewriting the text."""
        if not self._pattern or not text:
            return set()
        return {self._member_to_canonical[m.group(0).lower()]
                for m in self._pattern.finditer(text)}


def load_synonyms(path: str | Path) -> Synonyms:
    """Load a synonyms.yaml file. Returns an empty Synonyms table if the file
    is missing — the rest of the pipeline degrades gracefully."""
    p = Path(path)
    if not p.exists():
        return Synonyms(classes=[])
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return Synonyms(classes=data.get("classes", []))


def empty() -> Synonyms:
    """An empty synonyms table — handy for tests that don't depend on it."""
    return Synonyms(classes=[])
