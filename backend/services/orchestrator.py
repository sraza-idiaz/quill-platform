"""Run orchestrator — drives an artifact through the tiers (SYSTEM_DESIGN §2.2).

ingest/normalize -> T0 (deterministic) -> T1 (evidence index) -> T2 (LLM sufficiency)
-> citation validation (drop fabricated spans) -> confidence disposition
-> circuit breaker (threshold 3) -> persist run + findings.

Graceful degradation (FR-RES-01): if the Tier 2 analyzer is unavailable, the run
completes with T0 findings + flags the rest for human review. Idempotent
(NFR-REL-04): re-running replaces findings.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.services.analysis.synonyms import Synonyms

from backend.models.domain import (
    Artifact,
    ArtifactStatus,
    Finding,
    FindingStatus,
    Run,
    RunStatus,
    Tier,
)
from backend.db.repository import InMemoryRepository
from backend.services.catalog_loader import Catalog, Rubric
from backend.services.ingest.normalizer import normalize
from backend.services.ingest.parsers import ParseError
from backend.services.analysis.tier0_rules import run_tier0
from backend.services.analysis.tier1_retrieval import build_evidence_index
from backend.services.analysis.tier2_sufficiency import Analyzer, run_tier2
from backend.services.analysis.citation_validator import validate_findings
from backend.services.analysis.confidence import CircuitBreaker, apply_disposition
from backend.models.domain import FindingType

logger = logging.getLogger("quill.orchestrator")


class Orchestrator:
    def __init__(self, repo: InMemoryRepository, catalog: Catalog, rubric: Rubric,
                 analyzer: Optional[Analyzer] = None,
                 synonyms: Optional["Synonyms"] = None):
        self.repo = repo
        self.catalog = catalog
        self.rubric = rubric
        self.analyzer = analyzer  # None -> Tier 2 skipped (degraded)
        self.synonyms = synonyms  # Phase II FR-XA-01/05/06 — optional, degrades when None

    async def analyze_package(self, items: list[tuple[Artifact, Path]],
                              tenant: str = "default",
                              baseline: Optional[str] = None) -> Run:
        """Analyze a set of artifacts as ONE run so cross-artifact consistency
        checks (FR-T0-03) fire across them. The run is attributed to the first
        artifact for compatibility with the single-artifact API.

        Phase II — `baseline` overrides catalog.baseline so each program can
        analyze against its own baseline (FR-MT-01 / FR-CAT-05). The run
        records the active baseline in tier_path metadata.
        """
        if not items:
            raise ValueError("analyze_package requires at least one artifact")
        active_baseline = baseline or self.catalog.baseline
        primary = items[0][0]
        run = Run(id=f"run-{uuid.uuid4().hex[:12]}", artifact_id=primary.id,
                  status=RunStatus.analyzing)
        await self.repo.save_run(run, tenant=tenant)
        for a, _ in items:
            await self.repo.update_artifact_status(a.id, a.tenant, ArtifactStatus.analyzing)

        all_segments = []
        artifact_texts: dict[str, str] = {}
        for a, path in items:
            try:
                segs = normalize(a.id, path)
            except ParseError as e:
                run.status = RunStatus.failed
                run.failure_reason = f"{a.filename}: {e}"
                await self.repo.save_run(run, tenant=tenant)
                await self.repo.update_artifact_status(a.id, a.tenant, ArtifactStatus.failed)
                logger.warning("run %s failed on %s: %s", run.id, a.filename, e)
                return run
            all_segments += segs
            txt = "\n".join(s.text for s in segs)
            self.repo.set_artifact_text(a.id, txt)
            artifact_texts[a.id] = txt

        catalog_refs = {f"catalog:{active_baseline}"}
        breaker = CircuitBreaker(self.rubric.circuit_breaker_threshold)
        all_findings: list[Finding] = []

        t0 = run_tier0(run.id, all_segments, self.catalog, self.rubric,
                       baseline=active_baseline, synonyms=self.synonyms)
        all_findings += t0
        run.tier_path.append(Tier.t0)

        evidence_index = build_evidence_index(all_segments, self.catalog)
        run.tier_path.append(Tier.t1)

        if self.analyzer is not None:
            run.model = self.analyzer.name
            run.model_version = self.analyzer.version
            try:
                t2 = run_tier2(run.id, evidence_index, self.catalog, self.rubric, self.analyzer)
                run.tier_path.append(Tier.t2)
                for f in t2:
                    f = apply_disposition(f, self.rubric)
                    low = f.status == FindingStatus.flag_for_review or f.needs_review
                    contradiction = f.type == FindingType.inconsistent
                    if breaker.observe(low_confidence=low or contradiction):
                        run.circuit_breaker_tripped = True
                    all_findings.append(f)
            except Exception as e:  # noqa: BLE001
                logger.warning("Tier 2 unavailable (%s); degrading to T0+T1", e)
                run.failure_reason = f"tier2_degraded: {e}"

        valid, rejected = validate_findings(all_findings, artifact_texts, catalog_refs)
        if rejected:
            logger.warning("run %s: %d finding(s) rejected by citation validation", run.id, len(rejected))
        if run.circuit_breaker_tripped:
            for f in valid:
                f.needs_review = True

        await self.repo.replace_findings(run.id, tenant, valid)
        run.status = RunStatus.completed
        await self.repo.save_run(run, tenant=tenant)
        for a, _ in items:
            await self.repo.update_artifact_status(a.id, a.tenant, ArtifactStatus.reviewed)
        logger.info("run %s completed: %d findings (tiers=%s, breaker=%s, artifacts=%d)",
                    run.id, len(valid), [t.value for t in run.tier_path],
                    run.circuit_breaker_tripped, len(items))
        return run

    async def analyze(self, artifact: Artifact, path: Path,
                      baseline: Optional[str] = None) -> Run:
        """Single-artifact run. `baseline` overrides catalog.baseline for the
        per-program case (Phase II FR-MT-01)."""
        active_baseline = baseline or self.catalog.baseline
        run = Run(id=f"run-{uuid.uuid4().hex[:12]}", artifact_id=artifact.id,
                  status=RunStatus.analyzing)
        await self.repo.save_run(run, tenant=artifact.tenant)
        await self.repo.update_artifact_status(artifact.id, artifact.tenant, ArtifactStatus.analyzing)

        try:
            segments = normalize(artifact.id, path)
        except ParseError as e:
            run.status = RunStatus.failed
            run.failure_reason = str(e)
            await self.repo.save_run(run, tenant=artifact.tenant)
            await self.repo.update_artifact_status(artifact.id, artifact.tenant, ArtifactStatus.failed)
            logger.warning("run %s failed: %s", run.id, e)
            return run

        artifact_text = "\n".join(s.text for s in segments)
        self.repo.set_artifact_text(artifact.id, artifact_text)
        catalog_refs = {f"catalog:{active_baseline}"}

        breaker = CircuitBreaker(self.rubric.circuit_breaker_threshold)
        all_findings: list[Finding] = []

        # Tier 0 — deterministic, using the per-program baseline
        t0 = run_tier0(run.id, segments, self.catalog, self.rubric,
                       baseline=active_baseline, synonyms=self.synonyms)
        all_findings += t0
        run.tier_path.append(Tier.t0)

        # Tier 1 — evidence index
        evidence_index = build_evidence_index(segments, self.catalog)
        run.tier_path.append(Tier.t1)

        # Tier 2 — local-LLM sufficiency (graceful degradation if no analyzer)
        if self.analyzer is not None:
            run.model = self.analyzer.name
            run.model_version = self.analyzer.version
            try:
                t2 = run_tier2(run.id, evidence_index, self.catalog, self.rubric, self.analyzer)
                run.tier_path.append(Tier.t2)
                # confidence disposition + circuit breaker
                emitted: list[Finding] = []
                for f in t2:
                    f = apply_disposition(f, self.rubric)
                    low = f.status == FindingStatus.flag_for_review or f.needs_review
                    contradiction = f.type == FindingType.inconsistent
                    if breaker.observe(low_confidence=low or contradiction):
                        run.circuit_breaker_tripped = True
                    emitted.append(f)
                all_findings += emitted
            except Exception as e:  # noqa: BLE001 — degrade, don't crash (FR-RES-01)
                logger.warning("Tier 2 unavailable (%s); degrading to T0 + flag_for_review", e)
                run.failure_reason = f"tier2_degraded: {e}"
        else:
            logger.info("no analyzer configured; Tier 0 only (degraded)")

        # Citation validation — drop any finding whose span isn't in the artifact (FR-T2-03)
        artifact_texts = {artifact.id: artifact_text}
        valid, rejected = validate_findings(all_findings, artifact_texts, catalog_refs)
        if rejected:
            logger.warning("run %s: %d finding(s) rejected by citation validation", run.id, len(rejected))

        # If breaker tripped, route the whole artifact to human review:
        # mark every finding needs_review so nothing is auto-trusted.
        if run.circuit_breaker_tripped:
            for f in valid:
                f.needs_review = True

        await self.repo.replace_findings(run.id, artifact.tenant, valid)
        run.status = RunStatus.completed
        await self.repo.save_run(run, tenant=artifact.tenant)
        await self.repo.update_artifact_status(artifact.id, artifact.tenant, ArtifactStatus.reviewed)
        logger.info("run %s completed: %d findings (tiers=%s, breaker=%s)",
                    run.id, len(valid), [t.value for t in run.tier_path], run.circuit_breaker_tripped)
        return run
