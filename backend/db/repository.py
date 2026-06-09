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

from backend.models.domain import Artifact, Finding, Program, ProgramStatus, Run


class Repository(Protocol):
    # Phase II — programs (tenants)
    async def save_program(self, program: Program) -> Program: ...
    async def get_program(self, program_id: str) -> Optional[Program]: ...
    async def list_programs(self) -> list[Program]: ...

    async def save_artifact(self, artifact: Artifact) -> Artifact: ...
    async def get_artifact(self, artifact_id: str, tenant: str) -> Optional[Artifact]: ...
    async def list_artifacts(self, tenant: str) -> list[Artifact]: ...
    async def update_artifact_status(self, artifact_id: str, tenant: str, status) -> None: ...

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
        self._artifacts: dict[tuple[str, str], Artifact] = {}
        self._runs: dict[tuple[str, str], Run] = {}
        self._findings: dict[tuple[str, str], Finding] = {}
        self._artifact_text: dict[str, str] = {}  # artifact_id -> normalized text (for citation validation)
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
