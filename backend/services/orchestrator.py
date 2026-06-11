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
import time
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
from backend.services.continuous import (
    RunVersion,
    carryover_attestations,
    diff_findings,
    finding_signature,
)

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
                              baseline: Optional[str] = None,
                              package_id: Optional[str] = None,
                              folder_fingerprint: str = "") -> Run:
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

        # A bad artifact (parse error, missing bytes) used to abort the whole
        # package run and leave the OTHER artifacts pinned at status='analyzing'
        # forever (no finally-block reset). Now: skip the bad ones, run the rest,
        # surface failures in run.failure_reason so the UI can show them.
        all_segments = []
        artifact_texts: dict[str, str] = {}
        skipped: list[tuple[str, str]] = []
        for a, path in items:
            try:
                segs = normalize(a.id, path)
            except ParseError as e:
                logger.warning("run %s: skipping %s (%s)", run.id, a.filename, e)
                await self.repo.update_artifact_status(a.id, a.tenant, ArtifactStatus.failed)
                skipped.append((a.filename, str(e)))
                continue
            all_segments += segs
            txt = "\n".join(s.text for s in segs)
            self.repo.set_artifact_text(a.id, txt)
            artifact_texts[a.id] = txt

        # If EVERYTHING failed to parse, mark the run failed; otherwise carry on.
        if not all_segments:
            run.status = RunStatus.failed
            run.failure_reason = "all artifacts failed to parse: " + \
                "; ".join(f"{n}: {e}" for n, e in skipped)
            await self.repo.save_run(run, tenant=tenant)
            # Reset any unmarked artifacts (shouldn't be any, but be defensive).
            for a, _ in items:
                await self.repo.update_artifact_status(a.id, a.tenant, ArtifactStatus.failed)
            return run
        if skipped:
            # Record skipped files but keep the run as `completed` since the
            # surviving artifacts produced output. UI can read failure_reason
            # to surface which files were skipped.
            run.failure_reason = "skipped: " + \
                "; ".join(f"{n} ({e})" for n, e in skipped)

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
                t2_note = f"tier2_degraded: {e}"
                run.failure_reason = (
                    f"{run.failure_reason}; {t2_note}" if run.failure_reason else t2_note
                )

        valid, rejected = validate_findings(all_findings, artifact_texts, catalog_refs)
        if rejected:
            logger.warning("run %s: %d finding(s) rejected by citation validation", run.id, len(rejected))
        if run.circuit_breaker_tripped:
            for f in valid:
                f.needs_review = True

        # Phase II FR-CONT-06 — carry forward prior attestations on findings
        # whose signature is unchanged. Only happens when the caller supplied
        # a package_id and there is a prior version on record.
        diff_counts: dict[str, int] = {}
        if package_id:
            latest = await self.repo.latest_run_version(package_id, tenant)
            if latest is not None:
                prev_findings = await self.repo.list_findings(latest.run_id, tenant)
                carry = carryover_attestations(prev_findings, valid)
                for f in valid:
                    if f.id in carry:
                        prior = carry[f.id]
                        f.status = prior.status
                        f.needs_review = prior.needs_review or f.needs_review
                d = diff_findings(prev_findings, valid,
                                  prev_attested={pf.id for pf in prev_findings
                                                 if pf.status in (FindingStatus.approved,
                                                                  FindingStatus.edited)})
                diff_counts = d.counts()

        await self.repo.replace_findings(run.id, tenant, valid)
        run.status = RunStatus.completed
        await self.repo.save_run(run, tenant=tenant)
        for a, _ in items:
            await self.repo.update_artifact_status(a.id, a.tenant, ArtifactStatus.reviewed)

        # Phase II FR-CONT — version registry.
        if package_id:
            prior_versions = await self.repo.list_run_versions(package_id, tenant)
            version = RunVersion(
                package_id=package_id, tenant=tenant, run_id=run.id,
                version_idx=len(prior_versions) + 1,
                fingerprint=folder_fingerprint,
                finding_signatures=[finding_signature(f) for f in valid],
                created_at=time.time(),
                diff_counts=diff_counts,
            )
            await self.repo.save_run_version(version)

        logger.info("run %s completed: %d findings (tiers=%s, breaker=%s, artifacts=%d, diff=%s)",
                    run.id, len(valid), [t.value for t in run.tier_path],
                    run.circuit_breaker_tripped, len(items), diff_counts)
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
