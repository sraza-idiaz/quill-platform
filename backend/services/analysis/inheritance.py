"""Phase II FR-XA-02 — Inheritance pattern detection.

Real RMF packages lean heavily on **inherited controls**: instead of the
team implementing AC-2 directly, they say "AC-2 is inherited from Azure AD"
or "satisfied by the cloud provider's SOC 2 Type II audit." Inherited
controls have a different evidence model:

  * The team is NOT responsible for the implementation detail.
  * The team IS responsible for the inheritance ATTRIBUTION:
      - which provider owns it?
      - what attestation document (SOC 2 / FedRAMP ATO / Type II audit / ISO
        27001 / PCI-DSS / ...) backs the claim?

Without this detector, Tier 0's check_required_fields() generates noisy
"insufficient_evidence" findings on every inherited control because the
artifact doesn't mention `account_types`, `responsible_role`, etc. — it
shouldn't, because none of that is the team's job.

With this detector, Tier 0:
  * Skips the normal required-fields check for properly-attributed inherited
    controls (no false positive).
  * Emits an explicit `insufficient_evidence` finding when the inheritance
    claim is incomplete (missing provider or attestation), with helpful
    `missing_elements` so the team knows exactly what to add.

Config-driven (P-CONFIG-01): trigger phrases and attestation vocabularies
live in this module's tables; programs may extend per-program in a future
overlay file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# Phrases that signal an inheritance claim. Detection is case-insensitive
# and uses word boundaries so we don't false-positive on "uninherited".
INHERITANCE_TRIGGERS: tuple[str, ...] = (
    "inherited from",
    "is inherited",
    "are inherited",
    "satisfied by",
    "provided by",
    "common control",
    "common controls",
    "responsibility of the",     # "responsibility of the cloud service provider"
    "managed by the",
    "implemented by the cloud",
    "implemented by the platform",
    "covered by",
)

# Vocabularies that indicate a real third-party attestation backs the claim.
# Map each (lowercase) form to its preferred display form. The display form
# is what shows up in `claim.attestations` for downstream rationale strings,
# UI badges, audit metadata, etc.
ATTESTATION_VOCAB: dict[str, str] = {
    "soc 2":                  "SOC 2",
    "soc2":                   "SOC 2",
    "soc 1":                  "SOC 1",
    "soc1":                   "SOC 1",
    "ssae 18":                "SSAE 18",
    "ssae-18":                "SSAE 18",
    "ssae18":                 "SSAE 18",
    "ssae 16":                "SSAE 16",
    "ssae-16":                "SSAE 16",
    "ssae16":                 "SSAE 16",
    "fedramp":                "FedRAMP",
    "fed ramp":               "FedRAMP",
    "type ii":                "Type II",
    "type 2":                 "Type II",
    "type i":                 "Type I",
    "type 1":                 "Type I",
    "iso 27001":              "ISO 27001",
    "iso/iec 27001":          "ISO 27001",
    "iso27001":               "ISO 27001",
    "iso 27017":              "ISO 27017",
    "iso 27018":              "ISO 27018",
    "pci dss":                "PCI DSS",
    "pci-dss":                "PCI DSS",
    "pci":                    "PCI DSS",
    "ato":                    "ATO",
    "authority to operate":   "ATO",
    "p-ato":                  "FedRAMP P-ATO",
    "joint authorization board": "FedRAMP",
    "hitrust":                "HITRUST",
    "csa star":               "CSA STAR",
    "nist 800-53 ato":        "ATO",
}

# After a trigger like "inherited from <X>" or "provided by <X>", scoop up
# the next 1-6 words (capitalized or hyphenated) as the provider name.
_PROVIDER_AFTER_TRIGGER = re.compile(
    r"\b(?:inherited\s+from|satisfied\s+by|provided\s+by|managed\s+by\s+the|"
    r"responsibility\s+of\s+the|covered\s+by|implemented\s+by\s+the\s+(?:cloud|platform))\s+"
    r"([A-Z][\w\-]*(?:\s+[A-Z][\w\-&/]*){0,5})",
    re.IGNORECASE,
)


@dataclass
class InheritanceClaim:
    """Structured representation of an inheritance claim found in a control
    narrative.

    `is_complete` is True iff BOTH a provider name AND at least one
    recognized attestation vocabulary appear in the same narrative — that's
    the condition under which Tier 0 considers the inheritance properly
    attributed and skips the implementation-detail check.
    """
    trigger: str                      # the matched trigger phrase
    provider: Optional[str] = None    # e.g. "Azure Active Directory"
    attestations: list[str] = field(default_factory=list)
    raw_text: str = ""                # the surrounding narrative

    @property
    def is_complete(self) -> bool:
        return bool(self.provider) and bool(self.attestations)

    @property
    def missing_elements(self) -> list[str]:
        out: list[str] = []
        if not self.provider:
            out.append("inheritance_provider")
        if not self.attestations:
            out.append("inheritance_attestation")
        return out


def detect_inheritance(text: str) -> Optional[InheritanceClaim]:
    """Return an InheritanceClaim if the narrative makes an inheritance claim,
    else None. Case-insensitive; longest trigger wins.

    This is a deterministic Tier 0 check — no LLM. False negatives are
    acceptable (Tier 2 LLM still sees the narrative and can flag it); false
    positives are not (we never want to silently skip a real implementation
    check), so the trigger list is conservative.
    """
    if not text:
        return None
    low = text.lower()

    # Trigger detection — try longest first to be greedy.
    triggers_sorted = sorted(INHERITANCE_TRIGGERS, key=len, reverse=True)
    trigger_hit: Optional[str] = None
    for t in triggers_sorted:
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(t) + r"(?![A-Za-z0-9])", low):
            trigger_hit = t
            break
    if not trigger_hit:
        return None

    # Provider extraction (best-effort).
    provider: Optional[str] = None
    m = _PROVIDER_AFTER_TRIGGER.search(text)
    if m:
        provider = m.group(1).strip().rstrip(".,;:")
        # Trim trailing connective words that aren't really part of the name.
        provider = re.sub(r"\s+(?:and|with|the|via)\s*$", "", provider, flags=re.IGNORECASE).strip()

    # Attestation references — match each vocab variant case-insensitively
    # and collect its canonical display form (preserving first-seen order).
    # The vocab map is sorted longest-key-first so "iso/iec 27001" wins
    # before "iso 27001" can claim part of it.
    seen: set[str] = set()
    deduped: list[str] = []
    for vocab_key in sorted(ATTESTATION_VOCAB.keys(), key=len, reverse=True):
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(vocab_key) + r"(?![A-Za-z0-9])", low):
            canon = ATTESTATION_VOCAB[vocab_key]
            if canon not in seen:
                seen.add(canon)
                deduped.append(canon)

    return InheritanceClaim(
        trigger=trigger_hit, provider=provider, attestations=deduped,
        raw_text=text[:400],
    )
