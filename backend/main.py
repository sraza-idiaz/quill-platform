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

from backend.db.repository import InMemoryRepository, Repository
from backend.services.catalog_loader import Catalog, Rubric, load_catalog, load_rubric
from backend.services.orchestrator import Orchestrator
from backend.services.analysis.tier2_sufficiency import Analyzer, OllamaAnalyzer
from backend.services.audit_service import AuditLedger
from backend.services.provenance_service import ProvenanceLedger
from backend.services.change_request_service import ChangeRequestService
from backend.services.gpg_signer import Signer, make_default_signer
from backend.services.analysis.synonyms import Synonyms, load_synonyms
from backend.services.continuous import FolderWatcher, WatchEvent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("quill")

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class QuillContext:
    # InMemoryRepository at startup; PostgresRepository after _attach_postgres_if_configured
    # runs in lifespan. Both satisfy the Repository Protocol.
    repo: Repository
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
    # Phase II FR-CONT — folder watcher state. The watcher is started lazily
    # by lifespan; tests that don't run lifespan still see a usable instance.
    watcher: FolderWatcher = field(default_factory=FolderWatcher)


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
        ocfg = cfg["ollama"]
        # OLLAMA_HOST  (env) overrides config — typically:
        #   * local:        http://localhost:11434   (default)
        #   * Render demo:  https://ollama.com       (Ollama Cloud direct)
        # OLLAMA_API_KEY required when host points at ollama.com.
        # OLLAMA_MODEL allows swapping the active model without a code change
        # (useful when one model loses subscription access mid-deploy).
        host    = os.environ.get("OLLAMA_HOST",  ocfg.get("host",  "http://localhost:11434"))
        model   = os.environ.get("OLLAMA_MODEL", ocfg.get("model", "gemma4:31b-cloud"))
        api_key = os.environ.get("OLLAMA_API_KEY") or None
        logger.info("OllamaAnalyzer: host=%s model=%s auth=%s",
                    host, model, "bearer" if api_key else "none")
        analyzer = OllamaAnalyzer(host, model, api_key=api_key)

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


async def _attach_postgres_if_configured(ctx: "QuillContext") -> None:
    """If DATABASE_URL is set, swap the in-memory repo for a Postgres-backed
    one and rewire the orchestrator + change-request service references.

    Doing the upgrade here (in lifespan) rather than inside build_context
    keeps build_context synchronous, which all existing tests rely on.
    """
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        logger.info("Persistence: in-memory (set DATABASE_URL for Postgres)")
        return
    try:
        from backend.db.postgres_repository import PostgresRepository
        pg = await PostgresRepository.create(dsn)
        # Mirror artifact-text cache: re-uploaded files set this synchronously
        # at ingest, so the cold-cache case isn't a concern for the running
        # session; old uploads survive because the texts table persists them.
        # Three references to swap in lock-step:
        ctx.repo = pg
        ctx.orchestrator.repo = pg
        ctx.cr_service.repo = pg
        logger.info("Persistence: Postgres attached — state survives restarts")
    except Exception as e:  # noqa: BLE001
        logger.error("Persistence: Postgres attach FAILED (%s); falling back "
                     "to in-memory. Set DATABASE_URL to a reachable instance "
                     "to enable persistence.", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.quill = getattr(app.state, "quill", None) or build_context()
    ctx = app.state.quill

    # Upgrade to Postgres if DATABASE_URL is set (Render production).
    await _attach_postgres_if_configured(ctx)

    # Phase II FR-CONT-01 — wire the watcher callback to the orchestrator.
    async def _on_change(ev: WatchEvent) -> None:
        from backend.services.continuous_runner import handle_watch_event
        await handle_watch_event(ctx, ev)

    ctx.watcher.on_change(_on_change)
    if os.environ.get("QUILL_WATCHER_ENABLED", "1") == "1":
        await ctx.watcher.start()

    logger.info("QUILL up — baseline=%s controls=%d air_gap=%s breaker=%d watcher=%s repo=%s",
                ctx.catalog.baseline, len(ctx.catalog.controls),
                ctx.air_gap, ctx.rubric.circuit_breaker_threshold,
                "on" if ctx.watcher._task is not None else "off",
                type(ctx.repo).__name__)
    try:
        yield
    finally:
        await ctx.watcher.stop()
        # Clean shutdown of the Postgres pool (if attached) so connections
        # don't leak on graceful restarts.
        if hasattr(ctx.repo, "close"):
            try:
                await ctx.repo.close()
            except Exception as e:  # noqa: BLE001
                logger.warning("Postgres pool close failed: %s", e)


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

    # ---- HTTP Basic Auth gate (Phase II demo deployments) -------------- #
    # When BOTH env vars are set, every request must carry a valid
    # Authorization: Basic <base64(user:pass)> header. /health stays open
    # so Render's load-balancer probes don't 401. Headers/identity (the
    # X-QUILL-* triple) still drive role-based authz inside the app —
    # Basic Auth is a perimeter gate, not a replacement for that.
    import base64
    import os as _os
    import secrets
    from fastapi import Request
    from fastapi.responses import Response

    _ba_user = _os.environ.get("QUILL_BASIC_AUTH_USER")
    _ba_pass = _os.environ.get("QUILL_BASIC_AUTH_PASSWORD")
    _ba_realm = _os.environ.get("QUILL_BASIC_AUTH_REALM", "QUILL")
    _ba_open_paths = {"/health"}        # always reachable (Render probe)

    if _ba_user and _ba_pass:
        _expected = base64.b64encode(f"{_ba_user}:{_ba_pass}".encode()).decode()
        logger.info("HTTP Basic Auth: ENABLED (user=%s, realm=%s, open=%s)",
                    _ba_user, _ba_realm, ", ".join(_ba_open_paths))

        @app.middleware("http")
        async def _basic_auth(request: Request, call_next):
            if request.url.path in _ba_open_paths:
                return await call_next(request)
            header = request.headers.get("authorization", "")
            if header.startswith("Basic "):
                supplied = header.split(" ", 1)[1].strip()
                # constant-time compare to defeat timing oracles
                if secrets.compare_digest(supplied, _expected):
                    return await call_next(request)
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": f'Basic realm="{_ba_realm}"'},
                content="Authentication required.",
            )
    else:
        logger.info("HTTP Basic Auth: disabled (set QUILL_BASIC_AUTH_USER + QUILL_BASIC_AUTH_PASSWORD to enable)")

    # Make sure dev iterations on the UI aren't served from a stale browser cache.
    @app.middleware("http")
    async def _no_cache_ui(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/ui"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    return app


app = create_app()
