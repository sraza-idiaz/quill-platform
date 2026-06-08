"""MCP tool surface (FR-API-01). Mirrors the REST endpoints 1:1 so an agent can
drive QUILL without HTTP. The transport is intentionally thin: each tool is a
plain async callable that returns JSON-serializable data; a real MCP runtime
binds these names to its protocol. Keeping it transport-free makes the tools
unit-testable here without standing up an MCP server.

Same auth model: tools take an `auth` dict (user/role/tenant) and enforce role
gates (FR-API-02). 'attester' is required for attest.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from backend.models.domain import FindingStatus


class MCPError(Exception):
    pass


def _require(auth: dict, *roles: str) -> None:
    role = auth.get("role")
    if role in roles or (role == "admin" and "attester" not in roles):
        return
    raise MCPError(f"role '{role}' lacks permission; required: {', '.join(roles)}")


class MCPTools:
    """Bound to a QuillContext so tools share the same repo/audit/cr_service."""

    def __init__(self, ctx):
        self.ctx = ctx

    # -- meta --
    async def health(self, *, auth: dict | None = None) -> dict:
        c = self.ctx
        return {
            "status": "ok", "baseline": c.catalog.baseline,
            "controls_loaded": len(c.catalog.controls),
            "tier2_analyzer": c.orchestrator.analyzer.name if c.orchestrator.analyzer else None,
            "air_gap": c.air_gap,
            "circuit_breaker_threshold": c.rubric.circuit_breaker_threshold,
        }

    async def catalog(self, *, auth: dict) -> dict:
        return {"baseline": self.ctx.catalog.baseline,
                "controls": [c.model_dump() for c in self.ctx.catalog.baseline_controls()]}

    # -- analyze --
    async def analyze(self, *, artifact_id: str, auth: dict) -> dict:
        _require(auth, "engineer", "admin")
        a = await self.ctx.repo.get_artifact(artifact_id, auth["tenant"])
        if not a:
            raise MCPError("artifact not found")
        from pathlib import Path
        path = Path(self.ctx.tmp_paths.get(artifact_id, ""))
        if not path.exists():
            raise MCPError("artifact content unavailable")
        run = await self.ctx.orchestrator.analyze(a, path)
        return run.model_dump()

    async def run_status(self, *, run_id: str, auth: dict) -> dict:
        _require(auth, "viewer", "engineer", "attester", "admin")
        run = await self.ctx.repo.get_run(run_id, auth["tenant"])
        if not run:
            raise MCPError("run not found")
        return run.model_dump()

    async def findings(self, *, run_id: str, auth: dict,
                       severity: Optional[str] = None, type: Optional[str] = None) -> list[dict]:
        _require(auth, "viewer", "engineer", "attester", "admin")
        fs = await self.ctx.repo.list_findings(run_id, auth["tenant"])
        if severity: fs = [f for f in fs if f.severity.value == severity]
        if type:     fs = [f for f in fs if f.type.value == type]
        return [f.model_dump() for f in fs]

    # -- attest --
    async def attest(self, *, finding_id: str, decision: str, auth: dict,
                     note: str = "", edited_fields: Optional[dict] = None) -> dict:
        _require(auth, "attester")
        try:
            d = FindingStatus(decision)
        except ValueError:
            raise MCPError(f"invalid decision: {decision}")
        rec = await self.ctx.cr_service.attest(
            finding_id=finding_id, tenant=auth["tenant"], attester_user=auth,
            decision=d, note=note, edited_fields=edited_fields,
        )
        return {"ok": True, "provenance_id": rec.id, "scheme": rec.signature_scheme}

    # -- export --
    async def export(self, *, run_id: str, fmt: str, auth: dict) -> dict:
        _require(auth, "engineer", "admin")
        from backend.services.export_service import make_export
        run = await self.ctx.repo.get_run(run_id, auth["tenant"])
        if not run:
            raise MCPError("run not found")
        artifact = await self.ctx.repo.get_artifact(run.artifact_id, auth["tenant"])
        findings = await self.ctx.repo.list_findings(run_id, auth["tenant"])
        ex = make_export(
            fmt=fmt, run_id=run_id, tenant=auth["tenant"],
            artifact_filename=artifact.filename if artifact else "?",
            artifact_id=run.artifact_id, baseline=self.ctx.catalog.baseline,
            findings=findings, audit=self.ctx.audit, signer=self.ctx.signer,
            signer_name=auth["user"],
        )
        return {"id": ex.id, "format": ex.format, "content": ex.content,
                "scheme": ex.signature.scheme, "signature": ex.signature.signature}


def registry(ctx) -> dict[str, Callable[..., Awaitable[Any]]]:
    t = MCPTools(ctx)
    return {
        "quill.health": t.health,
        "quill.catalog": t.catalog,
        "quill.analyze": t.analyze,
        "quill.run_status": t.run_status,
        "quill.findings": t.findings,
        "quill.attest": t.attest,
        "quill.export": t.export,
    }
