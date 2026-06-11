"""Repository layer — persistence abstraction.

A Protocol defines the data operations the service needs; `InMemoryRepository`
implements them for dev/test (no live Postgres required), and a Postgres-backed
implementation (asyncpg, mirroring AXO's `db/*_queries.py`) is wired for
production against migrations 001/002. See DECISION-009.

All operations are tenant-scoped (FR-API-03 / NFR-SCAL-02).
"""

from __future__ import annotations

import datetime as dt
from typing import Optional, Protocol

from backend.models.domain import (Artifact, Finding, Package, PackageStatus,
                                    Program, ProgramStatus, Run)
from backend.services.continuous import RunVersion


class Repository(Protocol):
    # Phase II — programs (tenants)
    async def save_program(self, program: Program) -> Program: ...
    async def get_program(self, program_id: str) -> Optional[Program]: ...
    async def list_programs(self) -> list[Program]: ...

    # Phase II — packages
    async def save_package(self, package: Package) -> Package: ...
    async def get_package(self, package_id: str, tenant: str) -> Optional[Package]: ...
    async def list_packages(self, tenant: str) -> list[Package]: ...
    async def update_package_status(self, package_id: str, tenant: str,
                                    status: PackageStatus) -> None: ...
    async def list_artifacts_in_package(self, package_id: str, tenant: str) -> list[Artifact]: ...

    # Phase II FR-CONT — version registry
    async def save_run_version(self, version: RunVersion) -> RunVersion: ...
    async def list_run_versions(self, package_id: str, tenant: str) -> list[RunVersion]: ...
    async def latest_run_version(self, package_id: str, tenant: str) -> Optional[RunVersion]: ...

    async def save_artifact(self, artifact: Artifact) -> Artifact: ...
    async def get_artifact(self, artifact_id: str, tenant: str) -> Optional[Artifact]: ...
    async def list_artifacts(self, tenant: str) -> list[Artifact]: ...
    async def update_artifact_status(self, artifact_id: str, tenant: str, status) -> None: ...
    # Optional content persistence — only PostgresRepository implements it
    # today; InMemoryRepository keeps bytes in a side cache.
    async def save_artifact_with_content(self, artifact: Artifact, content: bytes) -> Artifact: ...
    async def get_artifact_content(self, artifact_id: str, tenant: str) -> Optional[bytes]: ...

    async def save_run(self, run: Run) -> Run: ...
    async def get_run(self, run_id: str, tenant: str) -> Optional[Run]: ...

    async def replace_findings(self, run_id: str, tenant: str, findings: list[Finding]) -> None: ...
    async def get_finding(self, finding_id: str, tenant: str) -> Optional[Finding]: ...
    async def list_findings(self, run_id: str, tenant: str) -> list[Finding]: ...
    async def update_finding(self, finding: Finding) -> None: ...


class InMemoryRepository:
    """Dev/test store. Idempotent run findings (NFR-REL-04): replace, never append."""

    def __init__(self) -> None:
        self._programs: dict[str, Program] = {}
        self._packages: dict[tuple[str, str], Package] = {}        # (tenant, package_id)
        self._artifacts: dict[tuple[str, str], Artifact] = {}
        self._runs: dict[tuple[str, str], Run] = {}
        self._findings: dict[tuple[str, str], Finding] = {}
        self._artifact_text: dict[str, str] = {}  # artifact_id -> normalized text (for citation validation)
        self._artifact_bytes: dict[tuple[str, str], bytes] = {}  # (tenant, artifact_id) -> raw bytes
        # Phase II FR-CONT — package version registry. List per (tenant, package_id),
        # most recent last. Each entry carries finding signatures so version
        # diffs don't have to re-load Finding rows.
        self._versions: dict[tuple[str, str], list[RunVersion]] = {}
        # Bootstrap "default" program for Phase I back-compat.
        self._programs["default"] = Program(
            id="default", name="Default Program", baseline="moderate",
            owner="system", status=ProgramStatus.active,
            created_at=dt.datetime.now(dt.timezone.utc),
            description="Auto-created program for backward compatibility with Phase I.",
        )

    # -- programs (Phase II) ----------------------------------------------- #
    async def save_program(self, program: Program) -> Program:
        if program.created_at is None:
            program.created_at = dt.datetime.now(dt.timezone.utc)
        self._programs[program.id] = program
        return program

    async def get_program(self, program_id: str) -> Optional[Program]:
        return self._programs.get(program_id)

    async def list_programs(self) -> list[Program]:
        return sorted(self._programs.values(), key=lambda p: (p.status.value, p.name.lower()))

    # -- packages (Phase II FR-PKG-*) -------------------------------------- #
    async def save_package(self, package: Package) -> Package:
        now = dt.datetime.now(dt.timezone.utc)
        if package.created_at is None:
            package.created_at = now
        package.updated_at = now
        self._packages[(package.tenant, package.id)] = package
        return package

    async def get_package(self, package_id: str, tenant: str) -> Optional[Package]:
        return self._packages.get((tenant, package_id))

    async def list_packages(self, tenant: str) -> list[Package]:
        items = [p for (t, _), p in self._packages.items() if t == tenant]
        # Sort: active (not archived) first, then most recently updated first.
        return sorted(
            items,
            key=lambda p: (p.status == PackageStatus.archived,
                           -(p.updated_at.timestamp() if p.updated_at else 0)),
        )

    async def update_package_status(self, package_id: str, tenant: str,
                                    status: PackageStatus) -> None:
        p = self._packages.get((tenant, package_id))
        if p:
            p.status = status
            p.updated_at = dt.datetime.now(dt.timezone.utc)

    async def list_artifacts_in_package(self, package_id: str, tenant: str) -> list[Artifact]:
        return [a for (t, _), a in self._artifacts.items()
                if t == tenant and a.package_id == package_id]

    # -- artifacts ---------------------------------------------------------- #
    async def save_artifact(self, artifact: Artifact) -> Artifact:
        self._artifacts[(artifact.tenant, artifact.id)] = artifact
        return artifact

    async def get_artifact(self, artifact_id: str, tenant: str) -> Optional[Artifact]:
        return self._artifacts.get((tenant, artifact_id))

    async def list_artifacts(self, tenant: str) -> list[Artifact]:
        return [a for (t, _), a in self._artifacts.items() if t == tenant]

    async def update_artifact_status(self, artifact_id: str, tenant: str, status) -> None:
        a = self._artifacts.get((tenant, artifact_id))
        if a:
            a.status = status

    async def save_artifact_with_content(self, artifact: Artifact, content: bytes) -> Artifact:
        # In-memory: stash bytes in a side cache. Survives the process lifetime
        # but obviously not restarts — that's why Postgres exists.
        self._artifact_bytes[(artifact.tenant, artifact.id)] = content
        return await self.save_artifact(artifact)

    async def get_artifact_content(self, artifact_id: str, tenant: str) -> Optional[bytes]:
        return self._artifact_bytes.get((tenant, artifact_id))

    # -- runs --------------------------------------------------------------- #
    async def save_run(self, run: Run, tenant: str = "default") -> Run:
        self._runs[(tenant, run.id)] = run
        return run

    async def get_run(self, run_id: str, tenant: str) -> Optional[Run]:
        return self._runs.get((tenant, run_id))

    # -- findings ----------------------------------------------------------- #
    async def replace_findings(self, run_id: str, tenant: str, findings: list[Finding]) -> None:
        # Drop existing findings for this run (idempotency), then insert.
        for key in [k for k, f in self._findings.items() if f.run_id == run_id and k[0] == tenant]:
            del self._findings[key]
        for f in findings:
            self._findings[(tenant, f.id)] = f

    async def get_finding(self, finding_id: str, tenant: str) -> Optional[Finding]:
        return self._findings.get((tenant, finding_id))

    async def list_findings(self, run_id: str, tenant: str) -> list[Finding]:
        return [f for (t, _), f in self._findings.items() if t == tenant and f.run_id == run_id]

    async def update_finding(self, finding: Finding) -> None:
        # tenant is carried on the stored key; find and replace.
        for (t, fid), f in list(self._findings.items()):
            if fid == finding.id:
                self._findings[(t, fid)] = finding
                return

    # -- helper for citation validation ------------------------------------ #
    def set_artifact_text(self, artifact_id: str, text: str) -> None:
        self._artifact_text[artifact_id] = text

    def artifact_text(self, artifact_id: str) -> str:
        return self._artifact_text.get(artifact_id, "")

    async def get_artifact_text_async(self, artifact_id: str) -> str:
        # Symmetric surface with PostgresRepository so the route doesn't
        # care which backend is active. InMemory never has anything to
        # restore from — same cache the sync reader uses.
        return self._artifact_text.get(artifact_id, "")

    # -- Phase II FR-CONT — run versions ---------------------------------- #
    async def save_run_version(self, version: RunVersion) -> RunVersion:
        key = (version.tenant, version.package_id)
        self._versions.setdefault(key, []).append(version)
        return version

    async def list_run_versions(self, package_id: str, tenant: str) -> list[RunVersion]:
        return list(self._versions.get((tenant, package_id), []))

    async def latest_run_version(self, package_id: str, tenant: str) -> Optional[RunVersion]:
        versions = self._versions.get((tenant, package_id), [])
        return versions[-1] if versions else None
