"""Tier 3 safety gates (FR-T3-01/02) + folder-watch ingestion (FR-ING-07)."""
import shutil

import pytest

from backend.db.repository import InMemoryRepository
from backend.services.audit_service import AuditLedger
from backend.services.analysis.tier3_escalation import GuardedTier3Analyzer, Tier3Disabled
from backend.services.ingest.folder_watch import FolderWatcher


class _Upstream:
    name = "x"; version = "v"
    def score(self, **kw): pass


def test_tier3_disabled_by_default():
    with pytest.raises(Tier3Disabled):
        GuardedTier3Analyzer(enabled=False, air_gap=False, restricted=False, upstream=_Upstream())


def test_tier3_blocked_in_air_gap():
    with pytest.raises(Tier3Disabled, match="air-gap"):
        GuardedTier3Analyzer(enabled=True, air_gap=True, restricted=False, upstream=_Upstream())


def test_tier3_blocked_for_restricted_artifact():
    with pytest.raises(Tier3Disabled, match="restricted"):
        GuardedTier3Analyzer(enabled=True, air_gap=False, restricted=True, upstream=_Upstream())


def test_tier3_blocked_when_no_upstream():
    with pytest.raises(Tier3Disabled, match="no upstream"):
        GuardedTier3Analyzer(enabled=True, air_gap=False, restricted=False, upstream=None)


def test_tier3_constructs_when_all_gates_pass():
    a = GuardedTier3Analyzer(enabled=True, air_gap=False, restricted=False, upstream=_Upstream())
    assert a.name == "tier3-claude"


@pytest.mark.asyncio
async def test_folder_watch_ingests_new_files(tmp_path, fixtures_dir):
    shutil.copy(fixtures_dir / "ssp_weak_ac2.md", tmp_path / "weak.md")
    shutil.copy(fixtures_dir / "ssp_sample.oscal.json", tmp_path / "sample.json")
    repo, audit = InMemoryRepository(), AuditLedger()
    watcher = FolderWatcher(repo, audit, folder=tmp_path, tenant="t1")
    n = await watcher._scan_once()
    assert n == 2
    # Second scan: hashes already seen -> no duplicates ingested
    assert await watcher._scan_once() == 0
    arts = await repo.list_artifacts("t1")
    assert {a.filename for a in arts} == {"weak.md", "sample.json"}
    # Hash-collision check: dropping a byte-identical file with a new name -> dedup
    shutil.copy(fixtures_dir / "ssp_weak_ac2.md", tmp_path / "weak_copy.md")
    assert await watcher._scan_once() == 0
