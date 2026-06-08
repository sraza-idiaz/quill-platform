"""QUILL Tier 0 demo CLI — preview the engine on real documents.

Usage:
    python demo.py tests/fixtures/ssp_weak_ac2.md [more_files...]

Shows: ingest -> normalize -> Tier 0 deterministic findings, traceable to source.
No LLM, no DB required. This previews the analysis engine before the UI exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

from backend.services.catalog_loader import load_catalog, load_rubric
from backend.services.ingest.normalizer import normalize
from backend.services.analysis.tier0_rules import run_tier0
from backend.services.analysis.citation_validator import validate_findings

ROOT = Path(__file__).resolve().parent
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def main(paths: list[str]) -> None:
    catalog = load_catalog(ROOT / "config" / "catalog.yaml")
    rubric = load_rubric(ROOT / "config" / "rubric.yaml")

    segments = []
    artifact_texts: dict[str, str] = {}
    print(f"\n  QUILL · Tier 0 pre-adjudication  (baseline: {catalog.baseline})")
    print("  " + "─" * 70)
    for i, p in enumerate(paths):
        path = Path(p)
        aid = f"art{i}"
        segs = normalize(aid, path)
        segments += segs
        artifact_texts[aid] = "\n".join(s.text for s in segs)
        controls = sorted({s.control_hint for s in segs if s.control_hint})
        print(f"  ingested  {path.name:30} → {aid}  | controls seen: {', '.join(controls) or '—'}")

    findings = run_tier0("demo-run", segments, catalog, rubric)
    catalog_refs = {f"catalog:{catalog.baseline}"}
    valid, rejected = validate_findings(findings, artifact_texts, catalog_refs)
    valid.sort(key=lambda f: (SEV_ORDER.get(f.severity.value, 9), f.control_id))

    print("\n  FINDINGS")
    print("  " + "─" * 70)
    if not valid:
        print("  (no deficiencies detected)")
    for f in valid:
        span = f.evidence_spans[0]
        src = "absence (catalog requirement)" if span.artifact_id.startswith("catalog:") \
            else f'{span.artifact_id} @ {span.locator}: "{span.quoted_text[:60].strip()}…"'
        print(f"\n  [{f.severity.value.upper():8}] {f.type.value}  ·  {f.control_id}  ·  conf {f.confidence:.2f}")
        print(f"     ↳ {f.recommendation}")
        if f.missing_elements:
            print(f"     ↳ missing: {', '.join(f.missing_elements)}")
        print(f"     ↳ source:  {src}")

    print("\n  " + "─" * 70)
    print(f"  {len(valid)} finding(s) · {len(rejected)} rejected by citation validation "
          f"· every finding traceable to source")
    print("  Human attestation required before any finding is authoritative.\n")


if __name__ == "__main__":
    args = sys.argv[1:] or ["tests/fixtures/ssp_weak_ac2.md", "tests/fixtures/arch_ac2_conflict.md"]
    main(args)
