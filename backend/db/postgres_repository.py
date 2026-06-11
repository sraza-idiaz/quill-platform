"""Postgres-backed Repository implementation (asyncpg).

Implements the same Protocol that InMemoryRepository implements, so the
orchestrator + routes don't know which backend is active.

Activation: when DATABASE_URL is set in the environment, backend.main wires
this up; otherwise it falls back to InMemoryRepository (the current behavior).

Design notes
------------
* All entity tables are TENANT-SCOPED. Every read/write threads `tenant`
  through. This is enforced at the SQL level — every WHERE filters by tenant.
* asyncpg connection pooling. The pool is created once at process startup
  and shared across requests.
* Idempotent schema migration on init: runs schema.sql via execute(). The
  migration is just CREATE TABLE IF NOT EXISTS — safe to run on every boot.
* JSONB for embedded structures (tier_path, evidence_spans, metadata).
  asyncpg returns them as Python dicts/lists automatically once we register
  a codec.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import asyncpg

from backend.models.domain import (
    Artifact,
    ArtifactStatus,
    ArtifactType,
    EvidenceSpan,
    Finding,
    FindingStatus,
    FindingType,
    Package,
    PackageStatus,
    Program,
    ProgramStatus,
    Run,
    RunStatus,
    Severity,
    Tier,
)
from backend.services.continuous import RunVersion

logger = logging.getLogger("quill.db")

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


# --------------------------------------------------------------------------- #
# Row → model converters (centralised so the SELECT site stays compact)
# --------------------------------------------------------------------------- #
def _program(row) -> Program:
    return Program(
        id=row["id"], name=row["name"], baseline=row["baseline"],
        framework=row["framework"], owner=row["owner"],
        status=ProgramStatus(row["status"]),
        description=row["description"], created_at=row["created_at"],
    )


def _package(row) -> Package:
    return Package(
        id=row["id"], tenant=row["tenant"], name=row["name"],
        status=PackageStatus(row["status"]),
        description=row["description"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _artifact(row) -> Artifact:
    return Artifact(
        id=row["id"], tenant=row["tenant"],
        type=ArtifactType(row["type"]),
        filename=row["filename"], hash=row["hash"],
        source=row["source"], uploaded_by=row["uploaded_by"],
        status=ArtifactStatus(row["status"]),
        package_id=row["package_id"], created_at=row["created_at"],
    )


def _run(row) -> Run:
    tier_path = row["tier_path"] or []
    if isinstance(tier_path, str):
        tier_path = json.loads(tier_path)
    return Run(
        id=row["id"], artifact_id=row["artifact_id"],
        tier_path=[Tier(t) for t in tier_path],
        model=row["model"], model_version=row["model_version"],
        status=RunStatus(row["status"]),
        circuit_breaker_tripped=row["circuit_breaker_tripped"],
        started_at=row["started_at"], finished_at=row["finished_at"],
        failure_reason=row["failure_reason"],
    )


def _finding(row) -> Finding:
    spans_raw = row["evidence_spans"] or []
    if isinstance(spans_raw, str):
        spans_raw = json.loads(spans_raw)
    missing = row["missing_elements"] or []
    if isinstance(missing, str):
        missing = json.loads(missing)
    return Finding(
        id=row["id"], run_id=row["run_id"],
        control_id=row["control_id"], objective_id=row["objective_id"],
        type=FindingType(row["type"]),
        severity=Severity(row["severity"]),
        confidence=float(row["confidence"]),
        recommendation=row["recommendation"], rationale=row["rationale"],
        missing_elements=list(missing),
        evidence_spans=[EvidenceSpan(**s) for s in spans_raw],
        tier=Tier(row["tier"]),
        status=FindingStatus(row["status"]),
        needs_review=row["needs_review"], created_at=row["created_at"],
    )


def _run_version(row) -> RunVersion:
    sigs = row["finding_signatures"] or []
    if isinstance(sigs, str):
        sigs = json.loads(sigs)
    diff = row["diff_counts"] or {}
    if isinstance(diff, str):
        diff = json.loads(diff)
    return RunVersion(
        package_id=row["package_id"], tenant=row["tenant"],
        run_id=row["run_id"], version_idx=row["version_idx"],
        fingerprint=row["fingerprint"],
        finding_signatures=list(sigs), diff_counts=dict(diff),
        created_at=float(row["created_at"]),
    )


# --------------------------------------------------------------------------- #
class PostgresRepository:
    """Repository implementation backed by Postgres via asyncpg."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool
        # Side-channel cache for artifact text (citation validation). On disk
        # in `artifact_texts`, mirrored in memory for fast `artifact_text()`
        # synchronous reads which the orchestrator calls in hot paths.
        self._artifact_text_cache: dict[str, str] = {}

    @classmethod
    async def create(cls, dsn: str, min_size: int = 1, max_size: int = 5) -> "PostgresRepository":
        # Render's free Postgres can flake at startup if we open the pool
        # before the DB is fully ready — be patient with the connect.
        pool = await asyncpg.create_pool(dsn=dsn, min_size=min_size, max_size=max_size,
                                          command_timeout=15)
        repo = cls(pool)
        await repo._migrate()
        await repo._bootstrap_default_program()
        return repo

    async def _migrate(self) -> None:
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        async with self._pool.acquire() as conn:
            await conn.execute(sql)
        logger.info("Postgres schema migration complete")

    async def _bootstrap_default_program(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO programs (id, name, baseline, owner, status, description)
                VALUES ('default','Default Program','moderate','system','active',
                        'Auto-created program for backward compatibility with Phase I.')
                ON CONFLICT (id) DO NOTHING
                """
            )

    async def close(self) -> None:
        await self._pool.close()

    # ---- programs -------------------------------------------------------- #
    async def save_program(self, program: Program) -> Program:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO programs (id, name, baseline, framework, owner, status, description)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (id) DO UPDATE SET
                  name=EXCLUDED.name, baseline=EXCLUDED.baseline,
                  framework=EXCLUDED.framework, owner=EXCLUDED.owner,
                  status=EXCLUDED.status, description=EXCLUDED.description
                """,
                program.id, program.name, program.baseline, program.framework,
                program.owner, program.status.value, program.description,
            )
        # Fetch back to get server-side created_at.
        return await self.get_program(program.id)  # type: ignore[return-value]

    async def get_program(self, program_id: str) -> Optional[Program]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM programs WHERE id=$1", program_id)
        return _program(row) if row else None

    async def list_programs(self) -> list[Program]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM programs ORDER BY status, LOWER(name)"
            )
        return [_program(r) for r in rows]

    # ---- packages -------------------------------------------------------- #
    async def save_package(self, package: Package) -> Package:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO packages (id, tenant, name, status, description, updated_at)
                VALUES ($1,$2,$3,$4,$5, now())
                ON CONFLICT (tenant, id) DO UPDATE SET
                  name=EXCLUDED.name, status=EXCLUDED.status,
                  description=EXCLUDED.description, updated_at=now()
                """,
                package.id, package.tenant, package.name,
                package.status.value, package.description,
            )
        return await self.get_package(package.id, package.tenant)  # type: ignore[return-value]

    async def get_package(self, package_id: str, tenant: str) -> Optional[Package]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM packages WHERE tenant=$1 AND id=$2",
                tenant, package_id,
            )
        return _package(row) if row else None

    async def list_packages(self, tenant: str) -> list[Package]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM packages WHERE tenant=$1
                ORDER BY (status='archived'), updated_at DESC
                """,
                tenant,
            )
        return [_package(r) for r in rows]

    async def update_package_status(self, package_id: str, tenant: str,
                                    status: PackageStatus) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE packages SET status=$3, updated_at=now() WHERE tenant=$1 AND id=$2",
                tenant, package_id, status.value,
            )

    async def list_artifacts_in_package(self, package_id: str, tenant: str) -> list[Artifact]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM artifacts WHERE tenant=$1 AND package_id=$2",
                tenant, package_id,
            )
        return [_artifact(r) for r in rows]

    # ---- artifacts ------------------------------------------------------- #
    async def save_artifact(self, artifact: Artifact) -> Artifact:
        # Note: this overload does NOT touch the content column. To persist
        # bytes (first upload, content edit), use save_artifact_with_content.
        # A bare save_artifact must NEVER overwrite existing content with
        # NULL — that would silently lose the file on every metadata update.
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO artifacts (id, tenant, type, filename, hash, source,
                                       uploaded_by, status, package_id)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (tenant, id) DO UPDATE SET
                  type=EXCLUDED.type, filename=EXCLUDED.filename,
                  hash=EXCLUDED.hash, source=EXCLUDED.source,
                  uploaded_by=EXCLUDED.uploaded_by, status=EXCLUDED.status,
                  package_id=EXCLUDED.package_id
                """,
                artifact.id, artifact.tenant, artifact.type.value,
                artifact.filename, artifact.hash, artifact.source,
                artifact.uploaded_by, artifact.status.value, artifact.package_id,
            )
        return await self.get_artifact(artifact.id, artifact.tenant)  # type: ignore[return-value]

    async def save_artifact_with_content(self, artifact: Artifact, content: bytes) -> Artifact:
        """Persist artifact metadata AND raw bytes in one transaction.
        Called by the upload route on ingest and by continuous_runner when
        the watcher detects a file change."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO artifacts (id, tenant, type, filename, hash, source,
                                       uploaded_by, status, package_id, content)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT (tenant, id) DO UPDATE SET
                  type=EXCLUDED.type, filename=EXCLUDED.filename,
                  hash=EXCLUDED.hash, source=EXCLUDED.source,
                  uploaded_by=EXCLUDED.uploaded_by, status=EXCLUDED.status,
                  package_id=EXCLUDED.package_id, content=EXCLUDED.content
                """,
                artifact.id, artifact.tenant, artifact.type.value,
                artifact.filename, artifact.hash, artifact.source,
                artifact.uploaded_by, artifact.status.value, artifact.package_id,
                content,
            )
        return await self.get_artifact(artifact.id, artifact.tenant)  # type: ignore[return-value]

    async def get_artifact_content(self, artifact_id: str, tenant: str) -> Optional[bytes]:
        """Read the raw bytes for an artifact, or None if it was uploaded
        before bytes-persistence shipped."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT content FROM artifacts WHERE tenant=$1 AND id=$2",
                tenant, artifact_id,
            )
        if not row:
            return None
        return bytes(row["content"]) if row["content"] is not None else None

    async def get_artifact(self, artifact_id: str, tenant: str) -> Optional[Artifact]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM artifacts WHERE tenant=$1 AND id=$2",
                tenant, artifact_id,
            )
        return _artifact(row) if row else None

    async def list_artifacts(self, tenant: str) -> list[Artifact]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM artifacts WHERE tenant=$1 ORDER BY created_at DESC",
                tenant,
            )
        return [_artifact(r) for r in rows]

    async def update_artifact_status(self, artifact_id: str, tenant: str, status) -> None:
        v = status.value if hasattr(status, "value") else str(status)
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE artifacts SET status=$3 WHERE tenant=$1 AND id=$2",
                tenant, artifact_id, v,
            )

    # ---- runs ------------------------------------------------------------ #
    async def save_run(self, run: Run, tenant: str = "default") -> Run:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO runs (id, tenant, artifact_id, tier_path, model, model_version,
                                  status, circuit_breaker_tripped, started_at, finished_at, failure_reason)
                VALUES ($1,$2,$3,$4::jsonb,$5,$6,$7,$8,$9,$10,$11)
                ON CONFLICT (tenant, id) DO UPDATE SET
                  tier_path=EXCLUDED.tier_path, model=EXCLUDED.model,
                  model_version=EXCLUDED.model_version, status=EXCLUDED.status,
                  circuit_breaker_tripped=EXCLUDED.circuit_breaker_tripped,
                  started_at=EXCLUDED.started_at, finished_at=EXCLUDED.finished_at,
                  failure_reason=EXCLUDED.failure_reason
                """,
                run.id, tenant, run.artifact_id,
                json.dumps([t.value for t in run.tier_path]),
                run.model, run.model_version, run.status.value,
                run.circuit_breaker_tripped, run.started_at, run.finished_at,
                run.failure_reason,
            )
        return run

    async def get_run(self, run_id: str, tenant: str) -> Optional[Run]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM runs WHERE tenant=$1 AND id=$2",
                tenant, run_id,
            )
        return _run(row) if row else None

    # ---- findings -------------------------------------------------------- #
    async def replace_findings(self, run_id: str, tenant: str,
                                findings: list[Finding]) -> None:
        # Idempotency: delete the prior findings for this run, then insert.
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM findings WHERE tenant=$1 AND run_id=$2",
                    tenant, run_id,
                )
                if findings:
                    await conn.executemany(
                        """
                        INSERT INTO findings (id, tenant, run_id, control_id, objective_id,
                                              type, severity, confidence, recommendation,
                                              rationale, missing_elements, evidence_spans,
                                              tier, status, needs_review, created_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
                                $11::jsonb,$12::jsonb,$13,$14,$15,$16)
                        """,
                        [
                            (
                                f.id, tenant, f.run_id, f.control_id, f.objective_id,
                                f.type.value, f.severity.value, f.confidence,
                                f.recommendation, f.rationale,
                                json.dumps(f.missing_elements),
                                json.dumps([s.model_dump() for s in f.evidence_spans]),
                                f.tier.value, f.status.value, f.needs_review,
                                f.created_at,
                            )
                            for f in findings
                        ],
                    )

    async def get_finding(self, finding_id: str, tenant: str) -> Optional[Finding]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM findings WHERE tenant=$1 AND id=$2",
                tenant, finding_id,
            )
        return _finding(row) if row else None

    async def list_findings(self, run_id: str, tenant: str) -> list[Finding]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM findings WHERE tenant=$1 AND run_id=$2",
                tenant, run_id,
            )
        return [_finding(r) for r in rows]

    async def update_finding(self, finding: Finding) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE findings SET
                  control_id=$3, objective_id=$4, type=$5, severity=$6, confidence=$7,
                  recommendation=$8, rationale=$9, missing_elements=$10::jsonb,
                  evidence_spans=$11::jsonb, tier=$12, status=$13, needs_review=$14
                WHERE id=$1 AND tenant IN (SELECT tenant FROM findings WHERE id=$1)
                """,
                finding.id, None,                   # placeholder
                finding.control_id, finding.objective_id, finding.type.value,
                finding.severity.value, finding.confidence,
                finding.recommendation, finding.rationale,
                json.dumps(finding.missing_elements),
                json.dumps([s.model_dump() for s in finding.evidence_spans]),
                finding.tier.value, finding.status.value, finding.needs_review,
            )

    # ---- run versions (Phase II FR-CONT) -------------------------------- #
    async def save_run_version(self, version: RunVersion) -> RunVersion:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO run_versions (tenant, package_id, run_id, version_idx,
                                          fingerprint, finding_signatures, diff_counts, created_at)
                VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8)
                ON CONFLICT (tenant, package_id, version_idx) DO UPDATE SET
                  run_id=EXCLUDED.run_id, fingerprint=EXCLUDED.fingerprint,
                  finding_signatures=EXCLUDED.finding_signatures,
                  diff_counts=EXCLUDED.diff_counts, created_at=EXCLUDED.created_at
                """,
                version.tenant, version.package_id, version.run_id, version.version_idx,
                version.fingerprint,
                json.dumps(version.finding_signatures),
                json.dumps(version.diff_counts),
                version.created_at,
            )
        return version

    async def list_run_versions(self, package_id: str, tenant: str) -> list[RunVersion]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM run_versions
                WHERE tenant=$1 AND package_id=$2
                ORDER BY version_idx ASC
                """,
                tenant, package_id,
            )
        return [_run_version(r) for r in rows]

    async def latest_run_version(self, package_id: str, tenant: str) -> Optional[RunVersion]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM run_versions
                WHERE tenant=$1 AND package_id=$2
                ORDER BY version_idx DESC LIMIT 1
                """,
                tenant, package_id,
            )
        return _run_version(row) if row else None

    # ---- artifact text (sync helpers for citation validation) ----------- #
    def set_artifact_text(self, artifact_id: str, text: str) -> None:
        self._artifact_text_cache[artifact_id] = text
        # Persist asynchronously without awaiting — the cache is the truth
        # for in-flight runs; the row is for surviving restarts.
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._upsert_artifact_text(artifact_id, text))
        except RuntimeError:
            # No running loop (e.g. unit test outside an async context) —
            # the cache is enough for this run.
            pass

    async def _upsert_artifact_text(self, artifact_id: str, text: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO artifact_texts (artifact_id, text) VALUES ($1, $2)
                ON CONFLICT (artifact_id) DO UPDATE SET text=EXCLUDED.text
                """,
                artifact_id, text,
            )

    def artifact_text(self, artifact_id: str) -> str:
        # Cache-first synchronous read for the orchestrator's hot path
        # (citation validation, called inside a single analyze() pass that
        # has just set_artifact_text'd a moment ago). Routes that fetch text
        # AFTER a server restart (e.g. /artifacts/{id}/text for a prior
        # run's Gate view) must use the async variant below — it falls back
        # to the DB.
        return self._artifact_text_cache.get(artifact_id, "")

    async def get_artifact_text_async(self, artifact_id: str) -> str:
        """Read the normalized artifact text — cache, then DB. Repopulates
        the cache on a hit so subsequent sync reads (orchestrator hot path)
        stay fast across a restart."""
        cached = self._artifact_text_cache.get(artifact_id)
        if cached is not None:
            return cached
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT text FROM artifact_texts WHERE artifact_id=$1",
                artifact_id,
            )
        text = row["text"] if row else ""
        if text:
            self._artifact_text_cache[artifact_id] = text
        return text
