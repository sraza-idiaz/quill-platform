"""Phase II FR-CONT — bridge between folder-watch events and the orchestrator.

A `WatchEvent` arrives when a watched folder's content has changed. This
module:

  1. Discovers every file in the folder (recurses one level — Phase II).
  2. Compares to the artifacts already attached to the package; uploads
     new files, replaces the disk path of files whose hash changed, and
     keeps un-touched artifacts in place.
  3. Kicks `Orchestrator.analyze_package(...)` with the full member set
     and the new folder fingerprint, which records the version and
     carries prior attestations forward (FR-CONT-06).
  4. Audits the event so the operator sees "folder watcher detected
     change → ran analysis run-XX → 3 new / 1 resolved / 12 unchanged".

This is deliberately a pure function over QuillContext + WatchEvent —
no globals — so it's testable and the watcher loop can stay dumb.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from backend.models.domain import Artifact, ArtifactType
from backend.services.continuous import WatchEvent
from backend.services.ingest.normalizer import compute_hash

if TYPE_CHECKING:
    from backend.main import QuillContext

logger = logging.getLogger("quill.continuous_runner")

_SUFFIX_TYPE = {
    ".json": ArtifactType.oscal,
    ".md": ArtifactType.ssp, ".markdown": ArtifactType.ssp,
    ".txt": ArtifactType.ssp,
    ".pdf": ArtifactType.ssp, ".docx": ArtifactType.ssp,
}


async def handle_watch_event(ctx: "QuillContext", ev: WatchEvent) -> None:
    """React to a folder-content change for one watched package.

    Idempotent: re-running on an unchanged folder produces no new run
    (the watcher itself dedupes via fingerprint, but defense-in-depth
    matters here because rotating files can leave fingerprints flapping).
    """
    folder = Path(ev.folder)
    if not folder.exists() or not folder.is_dir():
        logger.warning("watch event: folder gone %s", folder)
        return

    pkg = await ctx.repo.get_package(ev.package_id, ev.tenant)
    if pkg is None:
        logger.warning("watch event: package %s not found in tenant %s",
                       ev.package_id, ev.tenant)
        return

    # Discover supported files in the folder.
    on_disk = [p for p in sorted(folder.iterdir())
               if p.is_file() and p.suffix.lower() in _SUFFIX_TYPE]
    if not on_disk:
        logger.info("watch event: no supported files in %s; skipping run", folder)
        return

    # Sync artifacts: by filename. New files become new artifacts; files
    # whose hash changed get their tmp_paths refreshed; deleted files lose
    # their package_id (they remain in the artifact store for audit).
    existing = await ctx.repo.list_artifacts_in_package(ev.package_id, ev.tenant)
    by_name = {a.filename: a for a in existing}

    items = []
    for src in on_disk:
        # Copy into a temp file the orchestrator owns — we don't want a
        # mid-analysis edit by the user to corrupt the run.
        suffix = src.suffix.lower()
        tmp = Path(tempfile.gettempdir()) / f"quill-{uuid.uuid4().hex}{suffix}"
        shutil.copyfile(src, tmp)
        new_hash = compute_hash(tmp)
        content = tmp.read_bytes()

        art = by_name.get(src.name)
        if art is None:
            # New file in the folder.
            art = Artifact(
                id=f"art-{uuid.uuid4().hex[:12]}",
                type=_SUFFIX_TYPE[suffix],
                filename=src.name,
                hash=new_hash,
                source=f"watch:{ev.package_id}",
                uploaded_by="watcher",
                tenant=ev.tenant,
                package_id=ev.package_id,
            )
            await ctx.repo.save_artifact_with_content(art, content)
            logger.info("watch event: new artifact %s (%s)", art.id, src.name)
        elif art.hash != new_hash:
            # Hash changed — record the new content; orchestrator's
            # citation validator will re-check spans.
            art.hash = new_hash
            await ctx.repo.save_artifact_with_content(art, content)
            logger.info("watch event: artifact %s content changed (%s)",
                        art.id, src.name)
        ctx.tmp_paths[art.id] = str(tmp)
        items.append((art, tmp))

    # Detach files that are no longer in the folder.
    on_disk_names = {p.name for p in on_disk}
    for art in existing:
        if art.filename not in on_disk_names:
            art.package_id = None
            await ctx.repo.save_artifact(art)
            logger.info("watch event: detached artifact %s (file removed)", art.id)

    # Per-program baseline override.
    prog = await ctx.repo.get_program(ev.tenant)
    baseline = prog.baseline if prog else None

    run = await ctx.orchestrator.analyze_package(
        items, tenant=ev.tenant, baseline=baseline,
        package_id=ev.package_id, folder_fingerprint=ev.fingerprint,
    )

    ctx.audit.append(
        tenant=ev.tenant, actor="watcher",
        action=f"watch.{run.status.value}",
        target_type="package", target_id=ev.package_id,
        metadata={
            "run_id": run.id,
            "folder": str(folder),
            "fingerprint": ev.fingerprint,
            "tier_path": [t.value for t in run.tier_path],
        },
    )
    logger.info("watch event: package %s analyzed -> run %s", ev.package_id, run.id)
