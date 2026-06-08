"""Eval harness — runs the full pipeline over the labeled corpus and reports
the Phase I quality metrics (docs/04).

Usage:
    python -m eval.harness.run_eval [--analyzer mock|none] [--no-write]

Default analyzer is `mock` (the conftest MockAnalyzer — deterministic Tier 2
stand-in). Use `none` for Tier 0/1 only. Live Ollama is plugged in by wiring
OllamaAnalyzer; the harness is analyzer-agnostic.

Output:
  * `eval/reports/eval-<timestamp>.md`   human-readable
  * `eval/reports/eval-<timestamp>.json` machine-readable summary
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
import uuid
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.db.repository import InMemoryRepository                 # noqa: E402
from backend.models.domain import Artifact, ArtifactType             # noqa: E402
from backend.services.catalog_loader import load_catalog, load_rubric  # noqa: E402
from backend.services.orchestrator import Orchestrator               # noqa: E402

from eval.harness.match import match_finding_to_labels               # noqa: E402
from eval.harness.metrics import (                                   # noqa: E402
    CalibrationBucket, MetricBucket, bucket_for, expected_ce,
    make_calibration_buckets, monotonic_in_confidence, severity_within_one,
)

ART_DIR = ROOT / "eval" / "artifacts"
LABELS = ROOT / "eval" / "ground_truth" / "labels.yaml"
REPORTS = ROOT / "eval" / "reports"


def _suffix_type(p: Path) -> ArtifactType:
    if p.suffix == ".json": return ArtifactType.oscal
    return ArtifactType.ssp


def _load_analyzer(name: str):
    if name == "mock":
        sys.path.insert(0, str(ROOT / "tests"))
        from conftest import MockAnalyzer  # type: ignore
        return MockAnalyzer()
    return None


async def _run_package(pkg: dict, catalog, rubric, analyzer) -> dict:
    """Analyze the WHOLE package as one run so cross-artifact checks fire."""
    repo = InMemoryRepository()
    orch = Orchestrator(repo, catalog, rubric, analyzer=analyzer)
    items = []
    for name in pkg["artifacts"]:
        path = ART_DIR / name
        artifact = Artifact(
            id=f"art-{uuid.uuid4().hex[:8]}", type=_suffix_type(path),
            filename=name, hash="h", tenant="eval",
        )
        await repo.save_artifact(artifact)
        items.append((artifact, path))
    run = await orch.analyze_package(items, tenant="eval")
    fs = await repo.list_findings(run.id, "eval")
    findings = [f.model_dump(mode="json") for f in fs]
    return {"id": pkg["id"], "artifacts": pkg["artifacts"], "findings": findings}


def _expected_missing(pkg: dict, catalog) -> set[str]:
    if not pkg.get("expect_missing_for_baseline_moderate"):
        return set()
    covered: set[str] = set()
    for name in pkg["artifacts"]:
        text = (ART_DIR / name).read_text(encoding="utf-8")
        # crude but sufficient: a control is "addressed" if its id appears in the text
        for c in catalog.controls.values():
            if c.control_id in text or c.control_id.lower() in text:
                covered.add(c.control_id)
    return {c.control_id for c in catalog.baseline_controls()} - covered


async def evaluate(*, analyzer_name: str, write: bool = True) -> dict:
    catalog = load_catalog(ROOT / "config" / "catalog.yaml")
    rubric = load_rubric(ROOT / "config" / "rubric.yaml")
    analyzer = _load_analyzer(analyzer_name)

    spec = yaml.safe_load(LABELS.read_text())
    recall_b = MetricBucket()
    coverage_b = MetricBucket()                  # `missing` (catalog-derived)
    inconsistency_b = MetricBucket()
    fp = MetricBucket()                          # unmatched findings
    traceability_b = MetricBucket()              # every artifact-derived finding has verifiable span
    sev_b = MetricBucket()
    cal_buckets = make_calibration_buckets()
    per_pkg: list[dict] = []

    for pkg in spec["packages"]:
        result = await _run_package(pkg, catalog, rubric, analyzer)
        findings = result["findings"]
        labels = list(pkg.get("labels") or [])

        # ---- narrative recall (per label) ---------------------------------- #
        matched_label_idx: set[int] = set()
        for f in findings:
            i = match_finding_to_labels(f, labels)
            if i is not None:
                matched_label_idx.add(i)
        for i, lab in enumerate(labels):
            recall_b.total += 1
            if i in matched_label_idx:
                recall_b.matched += 1
            # inconsistency tracked separately for visibility
            if lab.get("type") == "inconsistent":
                inconsistency_b.total += 1
                if i in matched_label_idx:
                    inconsistency_b.matched += 1
                    # severity agreement (best matching finding)
                    for f in findings:
                        if (f.get("control_id") == lab.get("control_id")
                                and f.get("type") == "inconsistent"):
                            sev_b.total += 1
                            if severity_within_one(f.get("severity", ""), lab.get("severity", "")):
                                sev_b.matched += 1
                            break
            else:
                for f in findings:
                    if match_finding_to_labels(f, [lab]) is not None:
                        sev_b.total += 1
                        if severity_within_one(f.get("severity", ""), lab.get("severity", "")):
                            sev_b.matched += 1
                        break

        # ---- missing-control coverage (catalog-derived) -------------------- #
        expected_missing = _expected_missing(pkg, catalog)
        emitted_missing = {f["control_id"] for f in findings if f["type"] == "missing"}
        for c in expected_missing:
            coverage_b.total += 1
            if c in emitted_missing:
                coverage_b.matched += 1

        # ---- false positives ------------------------------------------------ #
        # An emitted finding is FP iff: (a) it's `missing` for a control NOT in
        # the expected_missing set, or (b) it's a narrative finding with no
        # matching label and on a control not flagged by any label.
        labeled_controls = {lab.get("control_id") for lab in labels}
        for f in findings:
            fp.total += 1
            t = f["type"]; cid = f["control_id"]
            if t == "missing":
                if cid in expected_missing:
                    continue
            elif t == "inconsistent":
                # If labels claim this inconsistency or any label exists on cid, treat as ok
                if any(lab.get("type") == "inconsistent" and lab.get("control_id") == cid for lab in labels):
                    continue
                if cid in labeled_controls:
                    continue
            else:
                if match_finding_to_labels(f, labels) is not None:
                    continue
                if cid in labeled_controls:
                    # narrative finding on the right control but elsewhere — ambiguous; count as catch
                    continue
            fp.matched += 1   # this counter holds the FP count (matched=FP, total=emitted)

        # ---- traceability --------------------------------------------------- #
        for f in findings:
            traceability_b.total += 1
            spans = f.get("evidence_spans") or []
            if not spans:
                continue
            ok = True
            for s in spans:
                if s.get("artifact_id", "").startswith("catalog:"):
                    continue
                if not (s.get("quoted_text") or "").strip():
                    ok = False; break
            if ok:
                traceability_b.matched += 1

        # ---- calibration ---------------------------------------------------- #
        for f in findings:
            conf = float(f.get("confidence", 0.0))
            b = bucket_for(conf, cal_buckets)
            if b is None:
                continue
            b.findings += 1
            b.confs.append(conf)
            # "correct" if it matches some label OR a coverage-expected missing
            correct = False
            if f["type"] == "missing":
                correct = f["control_id"] in expected_missing
            else:
                correct = (match_finding_to_labels(f, labels) is not None) or \
                          (f["control_id"] in labeled_controls)
            if correct:
                b.correct += 1

        per_pkg.append({
            "id": pkg["id"], "artifacts": pkg["artifacts"],
            "labels_total": len(labels),
            "findings_emitted": len(findings),
            "labels_matched": len(matched_label_idx),
            "expected_missing": sorted(expected_missing),
            "emitted_missing": sorted(emitted_missing),
        })

    # narrative recall (labels) + coverage recall combined
    narrative_recall = recall_b.rate
    coverage_recall = coverage_b.rate
    total_recall_matched = recall_b.matched + coverage_b.matched
    total_recall_count = recall_b.total + coverage_b.total
    total_recall = (total_recall_matched / total_recall_count) if total_recall_count else 0.0

    fp_rate = (fp.matched / fp.total) if fp.total else 0.0
    precision = 1.0 - fp_rate

    cal_serial = [{
        "range": [round(b.lo, 2), round(b.hi, 2)],
        "findings": b.findings, "correct": b.correct,
        "empirical": round(b.empirical, 3),
        "mean_conf": round(b.mean_conf, 3),
    } for b in cal_buckets]
    ece = round(expected_ce(cal_buckets), 4)
    monotonic = monotonic_in_confidence(cal_buckets)

    summary = {
        "analyzer": analyzer_name,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "packages": len(per_pkg),
        "metrics": {
            "deficiency_detection_recall": round(total_recall, 3),
            "narrative_recall": round(narrative_recall, 3),
            "coverage_recall": round(coverage_recall, 3),
            "inconsistency_recall": round(inconsistency_b.rate, 3),
            "false_positive_rate": round(fp_rate, 3),
            "precision": round(precision, 3),
            "traceability": round(traceability_b.rate, 3),
            "severity_within_one": round(sev_b.rate, 3),
            "calibration": {
                "monotonic": monotonic,
                "expected_calibration_error": ece,
                "buckets": cal_serial,
            },
        },
        "gates": {
            "recall_ge_0_80": total_recall >= 0.80,
            "fp_le_0_20":     fp_rate     <= 0.20,
            "traceability_eq_1":  traceability_b.rate == 1.0,
            "calibration_demonstrated": monotonic and ece <= 0.20,
        },
        "totals": {
            "findings_emitted": fp.total,
            "labels": recall_b.total,
            "expected_missing": coverage_b.total,
            "false_positives": fp.matched,
        },
        "packages_detail": per_pkg,
    }
    summary["all_gates_passed"] = all(summary["gates"].values())

    if write:
        REPORTS.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        (REPORTS / f"eval-{stamp}.json").write_text(json.dumps(summary, indent=2))
        (REPORTS / f"eval-{stamp}.md").write_text(_to_md(summary))
        (REPORTS / "latest.json").write_text(json.dumps(summary, indent=2))
        (REPORTS / "latest.md").write_text(_to_md(summary))
    return summary


def _to_md(s: dict) -> str:
    m = s["metrics"]; g = s["gates"]
    lines = [
        f"# QUILL Eval Report",
        f"",
        f"- **Generated:** {s['generated_at']}",
        f"- **Analyzer:** `{s['analyzer']}`",
        f"- **Packages:** {s['packages']}",
        f"- **Findings emitted:** {s['totals']['findings_emitted']}",
        f"- **Labels:** {s['totals']['labels']}  ·  Expected missing: {s['totals']['expected_missing']}",
        f"",
        f"## Gates",
        f"",
        f"| Gate | Target | Result | Pass |",
        f"|---|---|---|:---:|",
        f"| Deficiency-detection recall | ≥ 0.80 | **{m['deficiency_detection_recall']:.2f}** | {'✅' if g['recall_ge_0_80'] else '❌'} |",
        f"| False-positive rate         | ≤ 0.20 | **{m['false_positive_rate']:.2f}** | {'✅' if g['fp_le_0_20'] else '❌'} |",
        f"| Traceability                | = 1.00 | **{m['traceability']:.2f}** | {'✅' if g['traceability_eq_1'] else '❌'} |",
        f"| Confidence calibration      | monotonic + ECE ≤ 0.20 | **monotonic={m['calibration']['monotonic']}, ECE={m['calibration']['expected_calibration_error']}** | {'✅' if g['calibration_demonstrated'] else '❌'} |",
        f"",
        f"**Overall:** {'✅ ALL GATES PASSED' if s['all_gates_passed'] else '⚠ some gates not met (see breakdown)'}",
        f"",
        f"## Recall breakdown",
        f"",
        f"- Narrative recall (per labelled deficiency): **{m['narrative_recall']:.2f}**",
        f"- Coverage recall (`missing` for baseline): **{m['coverage_recall']:.2f}**",
        f"- Inconsistency recall (cross-artifact contradictions): **{m['inconsistency_recall']:.2f}**",
        f"",
        f"## Precision",
        f"",
        f"- Precision: **{m['precision']:.2f}**  ·  Severity agreement (±1 level): **{m['severity_within_one']:.2f}**",
        f"",
        f"## Confidence calibration",
        f"",
        f"| Range | Findings | Empirical correct | Mean confidence |",
        f"|---|---:|---:|---:|",
    ]
    for b in m["calibration"]["buckets"]:
        lines.append(f"| {b['range'][0]:.2f}–{b['range'][1]:.2f} | {b['findings']} | "
                     f"{b['empirical']:.2f} | {b['mean_conf']:.2f} |")
    lines += [
        f"",
        f"_Monotonic in confidence: {m['calibration']['monotonic']}; ECE = {m['calibration']['expected_calibration_error']:.4f}._",
        f"",
        f"## Per-package detail",
        f"",
        f"| Package | Artifacts | Labels | Matched | Findings | Expected missing |",
        f"|---|---|---:|---:|---:|---|",
    ]
    for p in s["packages_detail"]:
        lines.append(
            f"| `{p['id']}` | {', '.join(p['artifacts'])} | {p['labels_total']} | "
            f"{p['labels_matched']} | {p['findings_emitted']} | "
            f"{', '.join(p['expected_missing']) or '—'} |"
        )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--analyzer", choices=("mock", "none"), default="mock")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()
    s = asyncio.run(evaluate(analyzer_name=args.analyzer, write=not args.no_write))
    m = s["metrics"]
    print(f"\n  QUILL eval — analyzer={s['analyzer']}  packages={s['packages']}")
    print(f"  recall={m['deficiency_detection_recall']:.2f}  fp={m['false_positive_rate']:.2f}  "
          f"trace={m['traceability']:.2f}  ECE={m['calibration']['expected_calibration_error']:.3f}  "
          f"monotonic={m['calibration']['monotonic']}")
    print(f"  gates: {'✅ ALL PASSED' if s['all_gates_passed'] else 'see report'}")
    return 0 if s["all_gates_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
