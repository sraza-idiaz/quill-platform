"""Folder-watch ingest (FR-ING-07). Polls a directory at a configured interval
and ingests any artifact whose content hash hasn't been seen yet. Single-process,
no external dependencies (watchdog would be the Phase II upgrade).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Optional

from backend.models.domain import Artifact, ArtifactType
from backend.services.ingest.normalizer import compute_hash

logger = logging.getLogger("quill.folder_watch")

_SUFFIX_TYPE = {
    ".json": ArtifactType.oscal,
    ".md": ArtifactType.ssp, ".markdown": ArtifactType.ssp, ".txt": ArtifactType.ssp,
    ".pdf": ArtifactType.ssp, ".docx": ArtifactType.ssp,
}


class FolderWatcher:
    def __init__(self, repo, audit, *, folder: Path, tenant: str = "default",
                 interval: float = 2.0):
        self.repo = repo
        self.audit = audit
        self.folder = Path(folder)
        self.tenant = tenant
        self.interval = interval
        self._seen: set[str] = set()
        self._task: Optional[asyncio.Task] = None

    async def _scan_once(self) -> int:
        if not self.folder.exists():
            return 0
        ingested = 0
        for path in self.folder.iterdir():
            suffix = path.suffix.lower()
            if not path.is_file() or suffix not in _SUFFIX_TYPE:
                continue
            try:
                h = compute_hash(path)
            except Exception as e:  # noqa: BLE001
                logger.warning("hash failed for %s: %s", path.name, e)
                continue
            if h in self._seen:
                continue
            self._seen.add(h)
            artifact = Artifact(
                id=f"art-{uuid.uuid4().hex[:12]}",
                type=_SUFFIX_TYPE[suffix], filename=path.name, hash=h,
                source="folder_watch", tenant=self.tenant,
            )
            await self.repo.save_artifact(artifact)
            self.audit.append(
                tenant=self.tenant, actor="system", action="artifact.ingested",
                target_type="artifact", target_id=artifact.id,
                metadata={"filename": artifact.filename, "hash": h, "source": "folder_watch"},
            )
            ingested += 1
        return ingested

    async def _loop(self):  # pragma: no cover
        while True:
            try:
                n = await self._scan_once()
                if n:
                    logger.info("folder_watch ingested %d artifact(s) from %s", n, self.folder)
            except Exception as e:  # noqa: BLE001
                logger.warning("folder_watch error: %s", e)
            await asyncio.sleep(self.interval)

    def start(self):  # pragma: no cover
        self._task = asyncio.create_task(self._loop())

    async def stop(self):  # pragma: no cover
        if self._task:
            self._task.cancel()
