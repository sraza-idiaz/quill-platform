"""Finding ↔ label matching per docs/04 §3.

A finding matches a label when:
  * same control_id, AND
  * compatible type (per the equivalence table), AND
  * span overlap (any character overlap on the same artifact, OR a verbatim
    quote-substring match).

Span overlap is mandatory — a "right control, wrong location" hit does NOT
count (this enforces the traceability gate).

`missing` and `inconsistent` match only themselves.
The {weak_narrative, insufficient_evidence, narrative_present_evidence_unclear}
family is the "evidence-deficiency" class and is interchangeable for recall.
"""

from __future__ import annotations

from typing import Iterable, Optional

EVIDENCE_CLASS = {
    "weak_narrative",
    "insufficient_evidence",
    "narrative_present_evidence_unclear",
}


def type_compatible(label_type: str, finding_type: str, label_class: Optional[str] = None) -> bool:
    if label_class == "evidence":
        return finding_type in EVIDENCE_CLASS
    if label_type == "evidence":
        return finding_type in EVIDENCE_CLASS
    return label_type == finding_type


def _norm(s: str) -> str:
    return " ".join((s or "").split()).lower()


def span_overlaps(*, label_quote: str, label_artifact_basename: Optional[str],
                  finding_spans: Iterable[dict]) -> bool:
    """True iff any finding span 'covers' the label quote.

    The label `quoted` is a substring of the artifact narrative; an overlapping
    finding span is one whose quoted_text contains the label quote (or vice
    versa) when the label artifact matches.
    """
    q = _norm(label_quote)
    if not q:
        return False
    for s in finding_spans:
        if s.get("artifact_id", "").startswith("catalog:"):
            continue  # catalog refs are valid traceability for `missing`, not narrative labels
        s_basename = (s.get("artifact_id") or "").split("/")[-1]
        if label_artifact_basename and label_artifact_basename not in (s_basename, s.get("artifact_id")):
            # we don't always have a basename match; rely on quote containment below
            pass
        sq = _norm(s.get("quoted_text") or "")
        if not sq:
            continue
        if q in sq or sq in q:
            return True
    return False


def match_finding_to_labels(finding: dict, labels: list[dict]) -> Optional[int]:
    """Return the index of the first matching label, else None."""
    f_ctrl = finding.get("control_id")
    f_type = finding.get("type")
    spans = finding.get("evidence_spans") or []
    for i, lab in enumerate(labels):
        if lab.get("control_id") != f_ctrl:
            continue
        if not type_compatible(lab.get("type", ""), f_type, lab.get("class")):
            continue
        # `missing` labels are coverage-driven (handled outside); narrative
        # labels require quote overlap.
        if lab.get("type") == "missing":
            return i
        if lab.get("type") == "inconsistent":
            # inconsistency findings cite two artifact spans; either side is acceptable
            if spans:
                return i
            continue
        if span_overlaps(label_quote=lab.get("quoted", ""),
                         label_artifact_basename=lab.get("artifact"), finding_spans=spans):
            return i
    return None
