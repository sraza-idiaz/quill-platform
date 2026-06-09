"""QUILL FastAPI entrypoint. Standalone service (DECISION-005) that imports AXO
shared packages at WP-4. Loads catalog + rubric, builds the in-memory repo +
orchestrator, and mounts the REST API.

Tier 2 analyzer is attached only when configured + reachable; otherwise the
service runs Tier 0/1 (degraded) so it is always usable (FR-RES-01).
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from fastapi import FastAPI

from backend.db.repository import InMemoryRepository
from backend.services.catalog_loader import Catalog, Rubric, load_catalog, load_rubric
from backend.services.orchestrator import Orchestrator
from backend.services.analysis.tier2_sufficiency import Analyzer, OllamaAnalyzer
from backend.services.audit_service import AuditLedger
from backend.services.provenance_service import ProvenanceLedger
from backend.services.change_request_service import ChangeRequestService
from backend.services.gpg_signer import Signer, make_default_signer
from backend.services.analysis.synonyms import Synonyms, load_synonyms

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("quill")

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class QuillContext:
    repo: InMemoryRepository
    catalog: Catalog
    rubric: Rubric
    orchestrator: Orchestrator
    audit: AuditLedger
    provenance: ProvenanceLedger
    cr_service: ChangeRequestService
    signer: Signer
    synonyms: Synonyms
    air_gap: bool = True
    tmp_paths: dict[str, str] = field(default_factory=dict)


def _envbool(name: str, default: Optional[bool] = None) -> Optional[bool]:
    """Read an env var as a boolean override (truthy: 1/true/yes/on)."""
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def build_context(analyzer: Optional[Analyzer] = None, config_path: Optional[Path] = None,
                  signer: Optional[Signer] = None) -> QuillContext:
    # `QUILL_CONFIG` env var picks an alternate yaml (e.g. prod), default keeps dev config.
    chosen = config_path or Path(os.environ.get("QUILL_CONFIG") or (ROOT / "config" / "quill.config.yaml"))
    if not chosen.is_absolute():
        chosen = ROOT / chosen
    cfg = yaml.safe_load(chosen.read_text())
    catalog = load_catalog(ROOT / cfg.get("catalog_path", "config/catalog.yaml"))
    rubric = load_rubric(ROOT / cfg.get("rubric_path", "config/rubric.yaml"))
    # Phase II — load the synonym table (FR-XA-01/05/06). Path is optional;
    # missing file yields an empty table and the pipeline degrades gracefully.
    synonyms = load_synonyms(ROOT / cfg.get("synonyms_path", "config/synonyms.yaml"))
    repo = InMemoryRepository()

    # Env-var overrides (used by deployed environments like Render).
    air_gap = _envbool("QUILL_AIR_GAP", cfg.get("air_gap", True))
    enable_t2 = _envbool("QUILL_ENABLE_TIER2_AT_STARTUP", cfg.get("enable_tier2_at_startup", False))
    if analyzer is None and cfg.get("ollama") and enable_t2:
        analyzer = OllamaAnalyzer(cfg["ollama"]["host"], cfg["ollama"]["model"])

    orch = Orchestrator(repo, catalog, rubric, analyzer=analyzer, synonyms=synonyms)
    signer = signer or make_default_signer()
    audit = AuditLedger()
    provenance = ProvenanceLedger(signer)
    cr_service = ChangeRequestService(
        repo, provenance, audit,
        model=(analyzer.name if analyzer else "tier0"),
        model_version=(analyzer.version if analyzer else "0"),
    )
    return QuillContext(
        repo=repo, catalog=catalog, rubric=rubric, orchestrator=orch,
        audit=audit, provenance=provenance, cr_service=cr_service, signer=signer,
        synonyms=synonyms,
        air_gap=air_gap,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.quill = getattr(app.state, "quill", None) or build_context()
    logger.info("QUILL up — baseline=%s controls=%d air_gap=%s breaker=%d",
                app.state.quill.catalog.baseline, len(app.state.quill.catalog.controls),
                app.state.quill.air_gap, app.state.quill.rubric.circuit_breaker_threshold)
    yield


def create_app(context: Optional[QuillContext] = None) -> FastAPI:
    app = FastAPI(title="QUILL — RMF Pre-Adjudication", version="0.1.0", lifespan=lifespan)
    if context is not None:
        app.state.quill = context
    from backend.routes.api import router
    app.include_router(router)

    # Serve the web UI (FR-UI). Vanilla HTML/JS, no build step.
    ui_dir = ROOT / "desktop" / "web"
    if ui_dir.exists():
        from fastapi.responses import RedirectResponse
        from fastapi.staticfiles import StaticFiles
        app.mount("/ui", StaticFiles(directory=str(ui_dir), html=True), name="ui")

        @app.get("/", include_in_schema=False)
        async def _root():
            return RedirectResponse(url="/ui/")

    # Make sure dev iterations on the UI aren't served from a stale browser cache.
    @app.middleware("http")
    async def _no_cache_ui(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/ui"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    return app


app = create_app()
