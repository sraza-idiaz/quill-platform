"""Citation validation (FR-T2-03, NFR-AUD-03) — the hard traceability rule.

A finding derived from artifact narrative MUST cite text that is verbatim-present
in that artifact. Any finding whose cited span is absent is REJECTED (dropped +
logged), never surfaced. This is what makes traceability = 100% enforceable and
defeats a model coerced into fabricating a citation.

Catalog-reference spans (artifact_id starting 'catalog:') are validated against
the catalog, not artifact text — used by `missing` findings which have no artifact
text to quote (see tier0_rules).
"""

from __future__ import annotations

import logging

from backend.models.domain import Finding

logger = logging.getLogger("quill.citation")


def _normalize_ws(s: str) -> str:
    return " ".join(s.split())


def span_is_valid(span_text: str, artifact_text: str) -> bool:
    """Verbatim presence, whitespace-insensitive."""
    if not span_text.strip():
        return False
    return _normalize_ws(span_text) in _normalize_ws(artifact_text)


def validate_findings(
    findings: list[Finding],
    artifact_texts: dict[str, str],
    catalog_refs: set[str] | None = None,
) -> tuple[list[Finding], list[Finding]]:
    """Return (valid, rejected).

    artifact_texts: artifact_id -> full normalized text.
    catalog_refs:   set of valid 'catalog:<...>' artifact_ids.
    """
    catalog_refs = catalog_refs or set()
    valid: list[Finding] = []
    rejected: list[Finding] = []

    for f in findings:
        # A finding must carry at least one span.
        if not f.evidence_spans:
            logger.warning("REJECT finding %s (%s): no evidence span", f.id, f.control_id)
            rejected.append(f)
            continue

        ok = True
        for span in f.evidence_spans:
            if span.artifact_id.startswith("catalog:"):
                if span.artifact_id not in catalog_refs:
                    ok = False
                    break
                continue
            text = artifact_texts.get(span.artifact_id)
            if text is None or not span_is_valid(span.quoted_text, text):
                ok = False
                break

        if ok:
            valid.append(f)
        else:
            logger.warning(
                "REJECT finding %s (%s): cited span not present in artifact",
                f.id, f.control_id,
            )
            rejected.append(f)

    return valid, rejected
