"""Chaos / resilience tests (FR-RES-01..03, NFR-REL, NFR-SEC).

Exercises:
  * LLM-down: orchestrator degrades to Tier 0/1 + flag_for_review, no crash.
  * Corrupted artifact: clean failure, no exception.
  * Tier 2 raising mid-run: pipeline continues; finding set still consistent.
  * No artifact content leaks into logs (NFR-OBS-01).
  * Citation validation drops a forged span; finding never surfaces (FR-T2-03).
"""
import io
import logging
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db.repository import InMemoryRepository                          # noqa: E402
from backend.models.domain import Artifact, ArtifactType                      # noqa: E402
from backend.services.catalog_loader import load_catalog, load_rubric         # noqa: E402
from backend.services.analysis.tier2_sufficiency import SufficiencyResult     # noqa: E402
from backend.services.orchestrator import Orchestrator                        # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
CATALOG = load_catalog(ROOT / "config" / "catalog.yaml")
RUBRIC = load_rubric(ROOT / "config" / "rubric.yaml")


class _ExplodingAnalyzer:
    name = "boom"; version = "0"
    def score(self, **kw): raise RuntimeError("simulated LLM crash")


class _FabricatesSpan:
    """An analyzer that returns an insufficiency claim — citation validator must drop it."""
    name = "liar"; version = "0"
    def score(self, **kw):
        return SufficiencyResult("present", "insufficient", "this exact sentence does NOT exist",
                                 ["specifics"], 0.95)


async def _ingest(filename: str, tenant: str = "default") -> tuple[Artifact, Path]:
    repo = InMemoryRepository()
    a = Artifact(id=f"art-{uuid.uuid4().hex[:8]}", type=ArtifactType.ssp,
                 filename=filename, hash="h", tenant=tenant)
    await repo.save_artifact(a)
    return a, FIXTURES / filename


@pytest.mark.asyncio
async def test_llm_crash_degrades_gracefully(caplog):
    a, path = await _ingest("ssp_weak_ac2.md")
    repo = InMemoryRepository(); await repo.save_artifact(a)
    orch = Orchestrator(repo, CATALOG, RUBRIC, analyzer=_ExplodingAnalyzer())
    with caplog.at_level(logging.WARNING):
        run = await orch.analyze(a, path)
    assert run.status.value == "completed"      # FR-RES-01 graceful degradation
    assert "T0" in [t.value for t in run.tier_path]


@pytest.mark.asyncio
async def test_corrupted_artifact_clean_failure(tmp_path):
    bad = tmp_path / "bad.json"; bad.write_text("{not valid")
    a = Artifact(id="art-bad", type=ArtifactType.oscal, filename="bad.json", hash="h")
    repo = InMemoryRepository(); await repo.save_artifact(a)
    orch = Orchestrator(repo, CATALOG, RUBRIC, analyzer=None)
    run = await orch.analyze(a, bad)
    assert run.status.value == "failed"          # FR-ING-05
    assert run.failure_reason


@pytest.mark.asyncio
async def test_fabricated_span_is_dropped_by_citation_validator(caplog):
    a, path = await _ingest("ssp_weak_ac2.md")
    repo = InMemoryRepository(); await repo.save_artifact(a)
    orch = Orchestrator(repo, CATALOG, RUBRIC, analyzer=_FabricatesSpan())
    with caplog.at_level(logging.WARNING):
        run = await orch.analyze(a, path)
    findings = await repo.list_findings(run.id, "default")
    # Any T2 findings emitted MUST have validated spans — none of the liar's
    # fabricated text should have survived.
    for f in findings:
        for span in f.evidence_spans:
            if not span.artifact_id.startswith("catalog:"):
                assert "this exact sentence" not in span.quoted_text


@pytest.mark.asyncio
async def test_no_artifact_content_in_logs(caplog):
    """NFR-OBS-01: artifact narrative must not appear in log output."""
    a, path = await _ingest("ssp_good_ac2.md")
    secret_phrase = "service accounts. The Information System"   # appears in fixture
    repo = InMemoryRepository(); await repo.save_artifact(a)
    orch = Orchestrator(repo, CATALOG, RUBRIC, analyzer=None)
    with caplog.at_level(logging.DEBUG):
        await orch.analyze(a, path)
    all_log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert secret_phrase not in all_log_text, "artifact content leaked to logs"
