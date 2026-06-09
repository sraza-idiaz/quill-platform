"""QUILL REST API (FR-API-01). MCP server mirrors these 1:1 (added at WP-3 tail).

Endpoints follow SYSTEM_DESIGN §3. Auth is QUILL-native JWT (`backend/services/auth.py`)
with a DEV_MODE header fallback for local testing. All operations are tenant-scoped (FR-API-03).
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status

from pydantic import BaseModel, Field

from backend.models.domain import Artifact, ArtifactType, FindingStatus, Program, ProgramStatus
from backend.services.auth import get_current_user, require_role
from backend.services.change_request_service import AttestationError

router = APIRouter()

_SUFFIX_TYPE = {
    ".json": ArtifactType.oscal,
    ".md": ArtifactType.ssp, ".markdown": ArtifactType.ssp, ".txt": ArtifactType.ssp,
    ".pdf": ArtifactType.ssp, ".docx": ArtifactType.ssp,
}


def _ctx(request: Request):
    """Pull shared app state (repo/catalog/rubric/orchestrator)."""
    return request.app.state.quill


# -- meta ------------------------------------------------------------------- #
@router.get("/health")
async def health(request: Request):
    ctx = _ctx(request)
    return {
        "status": "ok",
        "baseline": ctx.catalog.baseline,
        "controls_loaded": len(ctx.catalog.controls),
        "tier2_analyzer": ctx.orchestrator.analyzer.name if ctx.orchestrator.analyzer else None,
        "air_gap": ctx.air_gap,
        "circuit_breaker_threshold": ctx.rubric.circuit_breaker_threshold,
    }


# -- programs (Phase II — multi-tenant) ------------------------------------ #
class ProgramCreateRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=64,
                    description="lowercase, hyphenated id used as tenant key")
    name: str = Field(..., min_length=1, max_length=200)
    baseline: str = Field("moderate", description="low | moderate | high")
    framework: str = Field("nist-800-53-rev5")
    owner: str = ""
    description: str = ""


@router.get("/programs")
async def list_programs(request: Request, user=Depends(get_current_user)):
    """List all programs the operator could possibly act in.

    Phase II — identity is header-declared (no real auth). A program switcher
    in the UI lets the operator select which tenant they're acting on next.
    """
    ctx = _ctx(request)
    progs = await ctx.repo.list_programs()
    return [p.model_dump(mode="json") for p in progs]


@router.post("/programs", status_code=status.HTTP_201_CREATED)
async def create_program(body: ProgramCreateRequest, request: Request,
                         user=Depends(require_role("admin"))):
    ctx = _ctx(request)
    # ID validation: alpha-numeric + hyphens only (safe as a tenant key)
    if not all(c.isalnum() or c == "-" for c in body.id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "program id must be alphanumeric or hyphen only")
    if body.baseline not in ("low", "moderate", "high"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "baseline must be low | moderate | high")
    existing = await ctx.repo.get_program(body.id)
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"program '{body.id}' already exists")
    prog = Program(
        id=body.id, name=body.name, baseline=body.baseline,
        framework=body.framework, owner=body.owner or user["user"],
        description=body.description,
    )
    await ctx.repo.save_program(prog)
    ctx.audit.append(
        tenant=body.id, actor=user["user"], action="program.created",
        target_type="program", target_id=body.id,
        metadata={"name": body.name, "baseline": body.baseline, "framework": body.framework},
    )
    return prog.model_dump(mode="json")


@router.get("/programs/{program_id}")
async def get_program(program_id: str, request: Request, user=Depends(get_current_user)):
    ctx = _ctx(request)
    p = await ctx.repo.get_program(program_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "program not found")
    return p.model_dump(mode="json")


@router.get("/catalog")
async def get_catalog(request: Request, user=Depends(get_current_user)):
    ctx = _ctx(request)
    return {
        "baseline": ctx.catalog.baseline,
        "controls": [c.model_dump() for c in ctx.catalog.baseline_controls()],
    }


# -- artifacts -------------------------------------------------------------- #
@router.post("/artifacts", status_code=status.HTTP_201_CREATED)
async def upload_artifact(request: Request, file: UploadFile,
                          user=Depends(require_role("engineer", "admin"))):
    ctx = _ctx(request)
    suffix = Path(file.filename or "x").suffix.lower()
    if suffix not in _SUFFIX_TYPE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unsupported type: {suffix}")

    data = await file.read()
    tmp = Path(tempfile.gettempdir()) / f"quill-{uuid.uuid4().hex}{suffix}"
    tmp.write_bytes(data)

    from backend.services.ingest.normalizer import compute_hash
    artifact = Artifact(
        id=f"art-{uuid.uuid4().hex[:12]}",
        type=_SUFFIX_TYPE[suffix],
        filename=file.filename or tmp.name,
        hash=compute_hash(tmp),
        uploaded_by=user["user"],
        tenant=user["tenant"],
    )
    await ctx.repo.save_artifact(artifact)
    ctx.tmp_paths[artifact.id] = str(tmp)  # dev: keep path for analysis
    ctx.audit.append(
        tenant=user["tenant"], actor=user["user"], action="artifact.ingested",
        target_type="artifact", target_id=artifact.id,
        metadata={"filename": artifact.filename, "hash": artifact.hash, "type": artifact.type.value},
    )
    return artifact.model_dump()


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str, request: Request, user=Depends(get_current_user)):
    ctx = _ctx(request)
    a = await ctx.repo.get_artifact(artifact_id, user["tenant"])
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "artifact not found")
    return a.model_dump()


@router.get("/artifacts/{artifact_id}/text")
async def get_artifact_text(artifact_id: str, request: Request, user=Depends(get_current_user)):
    """Normalized artifact text for UI source-span highlighting (FR-UI-02)."""
    ctx = _ctx(request)
    a = await ctx.repo.get_artifact(artifact_id, user["tenant"])
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "artifact not found")
    return {"artifact_id": artifact_id, "text": ctx.repo.artifact_text(artifact_id)}


@router.get("/artifacts")
async def list_artifacts(request: Request, user=Depends(get_current_user)):
    ctx = _ctx(request)
    arts = await ctx.repo.list_artifacts(user["tenant"])
    return [a.model_dump() for a in arts]


# -- runs ------------------------------------------------------------------- #
async def _baseline_for(ctx, tenant: str) -> str | None:
    """Look up the per-program baseline (Phase II FR-MT-01). Falls back to the
    catalog default when the program doesn't exist or has no baseline set."""
    p = await ctx.repo.get_program(tenant) if tenant else None
    return p.baseline if p and p.baseline else None


@router.post("/artifacts/{artifact_id}/runs", status_code=status.HTTP_201_CREATED)
async def create_run(artifact_id: str, request: Request,
                     user=Depends(require_role("engineer", "admin"))):
    ctx = _ctx(request)
    a = await ctx.repo.get_artifact(artifact_id, user["tenant"])
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "artifact not found")
    path = Path(ctx.tmp_paths.get(artifact_id, ""))
    if not path.exists():
        raise HTTPException(status.HTTP_409_CONFLICT, "artifact content unavailable")
    # Per-program baseline override (Phase II FR-MT-01 / FR-CAT-05).
    baseline = await _baseline_for(ctx, user["tenant"])
    run = await ctx.orchestrator.analyze(a, path, baseline=baseline)
    ctx.audit.append(
        tenant=user["tenant"], actor=user["user"], action=f"run.{run.status.value}",
        target_type="run", target_id=run.id,
        metadata={"artifact_id": run.artifact_id, "tier_path": [t.value for t in run.tier_path],
                  "circuit_breaker_tripped": run.circuit_breaker_tripped,
                  "baseline": baseline or ctx.catalog.baseline},
    )
    return run.model_dump()


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request, user=Depends(get_current_user)):
    ctx = _ctx(request)
    run = await ctx.repo.get_run(run_id, user["tenant"])
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return run.model_dump()


@router.get("/runs/{run_id}/findings")
async def list_findings(run_id: str, request: Request, user=Depends(get_current_user),
                        severity: str | None = None, type: str | None = None):
    ctx = _ctx(request)
    findings = await ctx.repo.list_findings(run_id, user["tenant"])
    if severity:
        findings = [f for f in findings if f.severity.value == severity]
    if type:
        findings = [f for f in findings if f.type.value == type]
    findings.sort(key=lambda f: f.control_id)
    return [f.model_dump() for f in findings]


# -- findings --------------------------------------------------------------- #
@router.get("/findings/{finding_id}")
async def get_finding(finding_id: str, request: Request, user=Depends(get_current_user)):
    ctx = _ctx(request)
    f = await ctx.repo.get_finding(finding_id, user["tenant"])
    if not f:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "finding not found")
    return f.model_dump()


# -- attestation (the hard gate) ------------------------------------------- #
class AttestRequest(BaseModel):
    decision: str                      # 'approved' | 'edited' | 'rejected'
    note: str = ""
    edited_fields: dict | None = None  # required when decision == 'edited'


@router.post("/findings/{finding_id}/attest")
async def attest(
    finding_id: str, body: AttestRequest, request: Request,
    user=Depends(require_role("attester")),                 # FR-ATT-03 (admin not auto-granted)
):
    ctx = _ctx(request)
    try:
        decision = FindingStatus(body.decision)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid decision: {body.decision}")
    try:
        rec = await ctx.cr_service.attest(
            finding_id=finding_id, tenant=user["tenant"], attester_user=user,
            decision=decision, note=body.note, edited_fields=body.edited_fields,
        )
    except AttestationError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return {
        "ok": True,
        "finding_id": finding_id,
        "decision": decision.value,
        "provenance_id": rec.id,
        "signature_scheme": rec.signature_scheme,
        "signature_key_id": rec.signature_key_id,
        "signed_at": rec.signed_at,
    }


@router.get("/findings/{finding_id}/history")
async def finding_history(finding_id: str, request: Request, user=Depends(get_current_user)):
    ctx = _ctx(request)
    return await ctx.cr_service.history(finding_id, user["tenant"])


# -- audit ----------------------------------------------------------------- #
@router.get("/audit")
async def list_audit(request: Request, user=Depends(get_current_user), target_id: str | None = None):
    ctx = _ctx(request)
    return [e.__dict__ for e in ctx.audit.list(user["tenant"], target_id)]


@router.get("/audit/verify")
async def verify_audit(request: Request, user=Depends(get_current_user)):
    ctx = _ctx(request)
    return {"chain_valid": ctx.audit.verify_chain(), "events": len(ctx.audit.export())}


# -- export (FR-EXP) ------------------------------------------------------- #
class ExportRequest(BaseModel):
    format: str        # 'report' | 'poam' | 'audit'


@router.post("/runs/{run_id}/export")
async def export_run(run_id: str, body: ExportRequest, request: Request,
                     user=Depends(require_role("engineer", "admin"))):
    from backend.services.export_service import ExportSchemeError, make_export
    ctx = _ctx(request)
    run = await ctx.repo.get_run(run_id, user["tenant"])
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    artifact = await ctx.repo.get_artifact(run.artifact_id, user["tenant"])
    findings = await ctx.repo.list_findings(run_id, user["tenant"])
    try:
        export = make_export(
            fmt=body.format, run_id=run_id, tenant=user["tenant"],
            artifact_filename=artifact.filename if artifact else "?",
            artifact_id=run.artifact_id, baseline=ctx.catalog.baseline,
            findings=findings, audit=ctx.audit, signer=ctx.signer,
            signer_name=user["user"],
        )
    except ExportSchemeError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    ctx.audit.append(
        tenant=user["tenant"], actor=user["user"], action=f"export.{body.format}",
        target_type="run", target_id=run_id,
        metadata={"export_id": export.id, "scheme": export.signature.scheme,
                  "key_id": export.signature.key_id},
    )
    return {
        "id": export.id,
        "format": export.format,
        "content": export.content,
        "signature": {
            "scheme": export.signature.scheme,
            "key_id": export.signature.key_id,
            "signature": export.signature.signature,
            "signer": export.signature.signer,
            "signed_at": export.signature.signed_at.isoformat(),
        },
        "created_at": export.created_at,
    }
