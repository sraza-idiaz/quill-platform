"""QUILL REST API (FR-API-01). MCP server mirrors these 1:1 (added at WP-3 tail).

Endpoints follow SYSTEM_DESIGN §3. Auth is QUILL-native JWT (`backend/services/auth.py`)
with a DEV_MODE header fallback for local testing. All operations are tenant-scoped (FR-API-03).
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import Response

from pydantic import BaseModel, Field

from backend.models.domain import (Artifact, ArtifactType, FindingStatus, Package,
                                    PackageStatus, PACKAGE_STATE_MACHINE, Program, ProgramStatus)
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


# -- packages (Phase II — FR-PKG-*) ---------------------------------------- #


class PackageCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    id: Optional[str] = Field(None, max_length=64,
                              description="optional; defaults to PKG-YYYY-XXXX")
    description: str = ""


class PackageStatusUpdate(BaseModel):
    status: str  # validated against PackageStatus enum + transition machine


def _new_package_id() -> str:
    """FR-PKG-06 — deterministic-looking PKG-YYYY-XXXXXX id."""
    import datetime as _dt
    year = _dt.datetime.now(_dt.timezone.utc).year
    return f"PKG-{year}-{uuid.uuid4().hex[:6].upper()}"


@router.get("/packages")
async def list_packages(request: Request, user=Depends(get_current_user)):
    ctx = _ctx(request)
    pkgs = await ctx.repo.list_packages(user["tenant"])
    out = []
    for p in pkgs:
        arts = await ctx.repo.list_artifacts_in_package(p.id, user["tenant"])
        d = p.model_dump(mode="json")
        d["artifact_count"] = len(arts)
        out.append(d)
    return out


@router.post("/packages", status_code=status.HTTP_201_CREATED)
async def create_package(body: PackageCreateRequest, request: Request,
                         user=Depends(require_role("engineer", "admin"))):
    ctx = _ctx(request)
    pid = body.id or _new_package_id()
    if not all(c.isalnum() or c in "-_" for c in pid):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "package id must be alphanumeric / hyphen / underscore only")
    existing = await ctx.repo.get_package(pid, user["tenant"])
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"package '{pid}' already exists")
    pkg = Package(id=pid, tenant=user["tenant"], name=body.name,
                  description=body.description, status=PackageStatus.draft)
    await ctx.repo.save_package(pkg)
    ctx.audit.append(
        tenant=user["tenant"], actor=user["user"], action="package.created",
        target_type="package", target_id=pid,
        metadata={"name": body.name},
    )
    return pkg.model_dump(mode="json")


@router.get("/packages/{package_id}")
async def get_package(package_id: str, request: Request, user=Depends(get_current_user)):
    ctx = _ctx(request)
    p = await ctx.repo.get_package(package_id, user["tenant"])
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "package not found")
    arts = await ctx.repo.list_artifacts_in_package(package_id, user["tenant"])
    out = p.model_dump(mode="json")
    out["artifacts"] = [a.model_dump(mode="json") for a in arts]
    return out


@router.patch("/packages/{package_id}/status")
async def set_package_status(package_id: str, body: PackageStatusUpdate, request: Request,
                              user=Depends(require_role("engineer", "admin"))):
    ctx = _ctx(request)
    p = await ctx.repo.get_package(package_id, user["tenant"])
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "package not found")
    try:
        new_status = PackageStatus(body.status)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid status: {body.status}")
    if new_status not in PACKAGE_STATE_MACHINE.get(p.status, set()):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"illegal transition: '{p.status.value}' -> '{new_status.value}'"
        )
    await ctx.repo.update_package_status(package_id, user["tenant"], new_status)
    ctx.audit.append(
        tenant=user["tenant"], actor=user["user"], action="package.status_changed",
        target_type="package", target_id=package_id,
        metadata={"from": p.status.value, "to": new_status.value},
    )
    return {"id": package_id, "status": new_status.value}


@router.post("/packages/{package_id}/artifacts/{artifact_id}")
async def attach_artifact_to_package(package_id: str, artifact_id: str, request: Request,
                                     user=Depends(require_role("engineer", "admin"))):
    """FR-PKG-02 — attach an existing artifact to a package. Artifact and
    package must be in the same tenant."""
    ctx = _ctx(request)
    pkg = await ctx.repo.get_package(package_id, user["tenant"])
    if not pkg:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "package not found")
    if pkg.status == PackageStatus.archived:
        raise HTTPException(status.HTTP_409_CONFLICT, "package is archived (read-only)")
    art = await ctx.repo.get_artifact(artifact_id, user["tenant"])
    if not art:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "artifact not found")
    art.package_id = package_id
    await ctx.repo.save_artifact(art)
    ctx.audit.append(
        tenant=user["tenant"], actor=user["user"], action="package.artifact_attached",
        target_type="package", target_id=package_id,
        metadata={"artifact_id": artifact_id},
    )
    return {"package_id": package_id, "artifact_id": artifact_id, "ok": True}


@router.delete("/packages/{package_id}/artifacts/{artifact_id}")
async def detach_artifact_from_package(package_id: str, artifact_id: str, request: Request,
                                        user=Depends(require_role("engineer", "admin"))):
    ctx = _ctx(request)
    art = await ctx.repo.get_artifact(artifact_id, user["tenant"])
    if not art or art.package_id != package_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "artifact not in this package")
    art.package_id = None
    await ctx.repo.save_artifact(art)
    ctx.audit.append(
        tenant=user["tenant"], actor=user["user"], action="package.artifact_detached",
        target_type="package", target_id=package_id,
        metadata={"artifact_id": artifact_id},
    )
    return {"package_id": package_id, "artifact_id": artifact_id, "ok": True}


# -- dependency graph (Phase II FR-XA-03) ---------------------------------- #
async def _build_graph_for_artifacts(ctx, user, arts: list[Artifact]):
    """Re-normalize every artifact in `arts` and build the dependency graph.

    Normalization is cheap; we don't persist segments. If an artifact's
    source file isn't reachable (e.g. it was uploaded in a previous process
    that's since gone), it's quietly skipped — the graph degrades.
    """
    from backend.services.ingest.normalizer import normalize
    from backend.services.analysis.dependency_graph import build_graph

    segments = []
    for a in arts:
        p = Path(ctx.tmp_paths.get(a.id, ""))
        if not p.exists():
            continue
        try:
            segments.extend(normalize(a.id, p))
        except Exception:  # parse error — drop this artifact from the graph
            continue
    baseline = await _baseline_for(ctx, user["tenant"])
    return build_graph(segments, ctx.catalog, baseline=baseline)


@router.get("/packages/{package_id}/graph")
async def get_package_graph(package_id: str, request: Request, user=Depends(get_current_user)):
    """Return the control-to-control reference graph across all artifacts in
    the package (Phase II FR-XA-03). Used by the Attestation Gate's
    'Related controls' panel."""
    ctx = _ctx(request)
    pkg = await ctx.repo.get_package(package_id, user["tenant"])
    if not pkg:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "package not found")
    arts = await ctx.repo.list_artifacts_in_package(package_id, user["tenant"])
    g = await _build_graph_for_artifacts(ctx, user, arts)
    return g.to_dict()


@router.get("/artifacts/{artifact_id}/graph")
async def get_artifact_graph(artifact_id: str, request: Request, user=Depends(get_current_user)):
    """Single-artifact dependency graph — used when a finding is reviewed
    outside a package context (legacy / single-doc workflow)."""
    ctx = _ctx(request)
    a = await ctx.repo.get_artifact(artifact_id, user["tenant"])
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "artifact not found")
    g = await _build_graph_for_artifacts(ctx, user, [a])
    return g.to_dict()


@router.post("/packages/{package_id}/runs", status_code=status.HTTP_201_CREATED)
async def analyze_package(package_id: str, request: Request,
                          user=Depends(require_role("engineer", "admin"))):
    """FR-PKG-04 — run the full analysis pipeline across every artifact in
    the package as one logical run. Cross-artifact reasoning fires across
    the whole bundle (FR-T0-03 / FR-XA-*)."""
    ctx = _ctx(request)
    pkg = await ctx.repo.get_package(package_id, user["tenant"])
    if not pkg:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "package not found")
    if pkg.status == PackageStatus.archived:
        raise HTTPException(status.HTTP_409_CONFLICT, "package is archived (read-only)")
    arts = await ctx.repo.list_artifacts_in_package(package_id, user["tenant"])
    if not arts:
        raise HTTPException(status.HTTP_409_CONFLICT, "package has no artifacts")

    # Build (artifact, path) tuples for the orchestrator. Skip artifacts
    # whose source file has gone missing rather than crashing the whole run.
    items: list[tuple[Artifact, Path]] = []
    missing: list[str] = []
    for a in arts:
        p = Path(ctx.tmp_paths.get(a.id, ""))
        if p.exists():
            items.append((a, p))
        else:
            missing.append(a.id)
    if not items:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"no artifact content available; missing: {missing}")

    baseline = await _baseline_for(ctx, user["tenant"])
    run = await ctx.orchestrator.analyze_package(
        items, tenant=user["tenant"], baseline=baseline,
        package_id=package_id,
    )

    # Pull the new version + diff counts back for the audit payload.
    latest = await ctx.repo.latest_run_version(package_id, user["tenant"])
    diff_counts = latest.diff_counts if latest else {}

    ctx.audit.append(
        tenant=user["tenant"], actor=user["user"],
        action=f"package_run.{run.status.value}",
        target_type="package", target_id=package_id,
        metadata={
            "run_id": run.id,
            "artifact_count": len(items),
            "missing_artifacts": missing,
            "tier_path": [t.value for t in run.tier_path],
            "baseline": baseline or ctx.catalog.baseline,
            "circuit_breaker_tripped": run.circuit_breaker_tripped,
            "diff_counts": diff_counts,
        },
    )
    out = run.model_dump()
    out["diff_counts"] = diff_counts
    return out


# -- continuous re-analysis (Phase II FR-CONT) ----------------------------- #

class WatchRequest(BaseModel):
    folder: str = Field(..., min_length=1,
                        description="absolute filesystem path the watcher should monitor")


@router.post("/packages/{package_id}/watch",
             status_code=status.HTTP_201_CREATED)
async def watch_package(package_id: str, body: WatchRequest, request: Request,
                        user=Depends(require_role("engineer", "admin"))):
    """FR-CONT-01 — register a folder as the source of truth for a package.

    The watcher polls the folder every ~5s; on content change it re-runs
    the package's analysis and records a new version with diff metadata.
    """
    ctx = _ctx(request)
    pkg = await ctx.repo.get_package(package_id, user["tenant"])
    if not pkg:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "package not found")
    folder = Path(body.folder).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"folder does not exist or is not a directory: {folder}")
    ctx.watcher.add_watch(package_id, user["tenant"], folder)
    ctx.audit.append(
        tenant=user["tenant"], actor=user["user"], action="watch.added",
        target_type="package", target_id=package_id,
        metadata={"folder": str(folder)},
    )
    return {
        "package_id": package_id,
        "folder": str(folder),
        "poll_interval_s": ctx.watcher._poll_s,
        "ok": True,
    }


@router.delete("/packages/{package_id}/watch")
async def unwatch_package(package_id: str, request: Request,
                          user=Depends(require_role("engineer", "admin"))):
    ctx = _ctx(request)
    ctx.watcher.remove_watch(package_id)
    ctx.audit.append(
        tenant=user["tenant"], actor=user["user"], action="watch.removed",
        target_type="package", target_id=package_id,
    )
    return {"package_id": package_id, "ok": True}


@router.get("/packages/{package_id}/watch")
async def get_watch(package_id: str, request: Request, user=Depends(get_current_user)):
    """Inspect the current watch registration (folder + last fingerprint)."""
    ctx = _ctx(request)
    for w in ctx.watcher.list_watches():
        if w["package_id"] == package_id:
            return w
    raise HTTPException(status.HTTP_404_NOT_FOUND, "no watch registered for this package")


@router.post("/packages/{package_id}/watch/poll")
async def poll_watch(package_id: str, request: Request,
                     user=Depends(require_role("engineer", "admin"))):
    """Force a single watch-poll cycle. Useful for tests + the
    'Re-analyze now' button when the operator doesn't want to wait for
    the next poll tick. Returns the events that fired (could be empty).
    """
    ctx = _ctx(request)
    events = await ctx.watcher.poll_once()
    return {"events_fired": [
        {"package_id": e.package_id, "fingerprint": e.fingerprint,
         "detected_at": e.detected_at}
        for e in events if e.package_id == package_id or package_id == "*"
    ]}


@router.get("/packages/{package_id}/versions")
async def list_package_versions(package_id: str, request: Request,
                                user=Depends(get_current_user)):
    """FR-CONT — list every analysis run of this package, most recent first,
    with the new/resolved/unchanged counts computed at run time."""
    ctx = _ctx(request)
    pkg = await ctx.repo.get_package(package_id, user["tenant"])
    if not pkg:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "package not found")
    versions = await ctx.repo.list_run_versions(package_id, user["tenant"])
    out = []
    for v in reversed(versions):
        out.append({
            "package_id": v.package_id,
            "run_id": v.run_id,
            "version_idx": v.version_idx,
            "fingerprint": v.fingerprint,
            "diff_counts": v.diff_counts,
            "finding_count": len(v.finding_signatures),
            "created_at": v.created_at,
        })
    return out


@router.get("/packages/{package_id}/diff")
async def package_diff(package_id: str, request: Request,
                       user=Depends(get_current_user),
                       from_run: str | None = None, to_run: str | None = None):
    """FR-CONT-04 — finding-state diff between two runs of the same package.

    Defaults: `from_run` = previous version, `to_run` = latest version.
    The diff drives the UI 'since last analysis: 3 new, 2 resolved' badge
    and the stale-attestation re-confirm flow (FR-CONT-07).
    """
    from backend.services.continuous import diff_findings
    ctx = _ctx(request)
    pkg = await ctx.repo.get_package(package_id, user["tenant"])
    if not pkg:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "package not found")
    versions = await ctx.repo.list_run_versions(package_id, user["tenant"])
    if len(versions) < 1:
        return {"counts": {"new": 0, "resolved": 0, "stale": 0, "unchanged": 0},
                "new": [], "resolved": [], "stale": [], "unchanged": []}
    to_v = next((v for v in versions if v.run_id == to_run), versions[-1]) if to_run \
           else versions[-1]
    if len(versions) < 2 and not from_run:
        # Single version — everything is "new".
        new_findings = await ctx.repo.list_findings(to_v.run_id, user["tenant"])
        return {"counts": {"new": len(new_findings), "resolved": 0,
                           "stale": 0, "unchanged": 0},
                "new": [f.model_dump(mode="json") for f in new_findings],
                "resolved": [], "stale": [], "unchanged": []}
    from_v = next((v for v in versions if v.run_id == from_run), None) if from_run \
             else versions[-2]
    if from_v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "from_run not found for this package")
    prev_findings = await ctx.repo.list_findings(from_v.run_id, user["tenant"])
    new_findings = await ctx.repo.list_findings(to_v.run_id, user["tenant"])
    d = diff_findings(prev_findings, new_findings,
                      prev_attested={f.id for f in prev_findings
                                     if f.status.value in ("approved", "edited")})
    out = d.to_dict()
    out["from_run"] = from_v.run_id
    out["to_run"] = to_v.run_id
    return out


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


# -- AI calibration (Phase II FR-AI-02) ------------------------------------ #
@router.get("/calibration/report")
async def calibration_report(request: Request,
                              user=Depends(get_current_user),
                              program: str | None = None,
                              package_id: str | None = None):
    """Compute the reliability curve + ECE + monotonicity for the operator's
    program (default) or a specified program/package scope.

    Phase II quality gate: ECE ≤ 0.20 AND monotonic across populated bins.
    Empty result (no attestations yet) is a valid "no data" response, not
    an error — the curve fills in as humans attest findings.
    """
    from backend.services.calibration import compute_calibration
    ctx = _ctx(request)
    tenant = program or user["tenant"]
    # Gather all findings for the tenant. In-memory repo: walk findings.
    all_findings = []
    if package_id:
        pkg = await ctx.repo.get_package(package_id, tenant)
        if not pkg:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "package not found")
        versions = await ctx.repo.list_run_versions(package_id, tenant)
        for v in versions:
            all_findings.extend(await ctx.repo.list_findings(v.run_id, tenant))
    else:
        # All findings for the tenant across every run we have a record of.
        # Iterate via internal _findings (in-memory repo); kept tenant-scoped.
        for (t, _fid), f in getattr(ctx.repo, "_findings", {}).items():
            if t == tenant:
                all_findings.append(f)
    report = compute_calibration(all_findings)
    out = report.to_dict()
    out["scope"] = {"tenant": tenant, "package_id": package_id}
    return out


@router.get("/calibration/curve.csv")
async def calibration_curve_csv(request: Request, user=Depends(get_current_user),
                                 program: str | None = None):
    """The reliability curve as CSV — useful for embedding in release notes."""
    from backend.services.calibration import compute_calibration, reliability_curve_csv
    ctx = _ctx(request)
    tenant = program or user["tenant"]
    all_findings = []
    for (t, _fid), f in getattr(ctx.repo, "_findings", {}).items():
        if t == tenant:
            all_findings.append(f)
    report = compute_calibration(all_findings)
    csv = reliability_curve_csv(report)
    return Response(content=csv, media_type="text/csv",
                    headers={"Content-Disposition":
                             f'attachment; filename="quill-reliability-{tenant}.csv"'})


# -- package exports (Phase II FR-EXP-04..06) ------------------------------ #
@router.get("/packages/{package_id}/export")
async def export_package(package_id: str, request: Request,
                          user=Depends(require_role("engineer", "admin", "viewer")),
                          format: str = "stakeholder_pdf"):
    """Three package-scoped export formats:

      * `stakeholder_pdf` (FR-EXP-04) — stakeholder summary PDF.
      * `version_diff`    (FR-EXP-05) — markdown comparing the two most
        recent runs of this package (or the only run if just one exists).
      * `oscal_package`   (FR-EXP-06) — OSCAL 1.1.x bundle (SSP shell +
        POA&M + Assessment Results) shaped for eMASS-class ingestion.

    Authoritative findings (the ones surfaced in the POA&M / Assessment
    Results) are attested only (P-CORE-02).
    """
    from backend.services.package_exports import (
        render_oscal_package_json,
        render_stakeholder_pdf,
        render_version_diff_markdown,
    )
    ctx = _ctx(request)
    pkg = await ctx.repo.get_package(package_id, user["tenant"])
    if not pkg:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "package not found")
    versions = await ctx.repo.list_run_versions(package_id, user["tenant"])
    if not versions:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "package has no analysis runs to export")
    baseline = await _baseline_for(ctx, user["tenant"]) or ctx.catalog.baseline

    if format == "stakeholder_pdf":
        latest = versions[-1]
        findings = await ctx.repo.list_findings(latest.run_id, user["tenant"])
        pdf_bytes = render_stakeholder_pdf(
            package=pkg, findings=findings, baseline=baseline, run_id=latest.run_id,
        )
        ctx.audit.append(
            tenant=user["tenant"], actor=user["user"], action="export.stakeholder_pdf",
            target_type="package", target_id=package_id,
            metadata={"run_id": latest.run_id, "bytes": len(pdf_bytes)},
        )
        return Response(
            content=pdf_bytes, media_type="application/pdf",
            headers={"Content-Disposition":
                     f'attachment; filename="{package_id}-stakeholder.pdf"'},
        )

    if format == "version_diff":
        if len(versions) < 2:
            # Single version — return a markdown stub showing only "new".
            v = versions[-1]
            findings = await ctx.repo.list_findings(v.run_id, user["tenant"])
            md = render_version_diff_markdown(
                package=pkg, from_run_id="(none)", to_run_id=v.run_id,
                from_findings=[], to_findings=findings,
            )
        else:
            v_prev, v_to = versions[-2], versions[-1]
            prev = await ctx.repo.list_findings(v_prev.run_id, user["tenant"])
            new = await ctx.repo.list_findings(v_to.run_id, user["tenant"])
            md = render_version_diff_markdown(
                package=pkg, from_run_id=v_prev.run_id, to_run_id=v_to.run_id,
                from_findings=prev, to_findings=new,
            )
        ctx.audit.append(
            tenant=user["tenant"], actor=user["user"], action="export.version_diff",
            target_type="package", target_id=package_id,
            metadata={"versions": [v.run_id for v in versions[-2:]]},
        )
        return Response(
            content=md, media_type="text/markdown",
            headers={"Content-Disposition":
                     f'attachment; filename="{package_id}-diff.md"'},
        )

    if format == "oscal_package":
        latest = versions[-1]
        findings = await ctx.repo.list_findings(latest.run_id, user["tenant"])
        arts = await ctx.repo.list_artifacts_in_package(package_id, user["tenant"])
        artifact_filenames = {a.id: a.filename for a in arts}
        bundle = render_oscal_package_json(
            package=pkg, run_id=latest.run_id, baseline=baseline,
            findings=findings, artifact_filenames=artifact_filenames,
        )
        ctx.audit.append(
            tenant=user["tenant"], actor=user["user"], action="export.oscal_package",
            target_type="package", target_id=package_id,
            metadata={"run_id": latest.run_id},
        )
        return Response(
            content=bundle, media_type="application/json",
            headers={"Content-Disposition":
                     f'attachment; filename="{package_id}-oscal.json"'},
        )

    raise HTTPException(status.HTTP_400_BAD_REQUEST,
                        f"unknown package export format: {format} "
                        "(expected stakeholder_pdf | version_diff | oscal_package)")


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
