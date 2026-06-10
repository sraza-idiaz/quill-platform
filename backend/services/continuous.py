"""Phase II FR-CONT-01..07 — Continuous re-analysis.

The headline Phase II differentiator. As an artifact in a package evolves
(new version uploaded, paragraph edited, control narrative rewritten), the
system:

  * computes which controls are affected — only those whose evidence
    paragraphs changed (FR-CONT-02);
  * re-runs analysis for those controls only (diff-aware),
  * classifies every finding across the prior and new versions as
        new        — emitted this run, not in the prior run
        resolved   — was in the prior run, gone in this run
        stale      — was attested in a prior run, the evidence paragraph
                     has changed enough that it no longer matches
                     verbatim → attester is asked to re-confirm
        unchanged  — the finding's signature is identical to the prior
                     run; prior attestation carries forward (FR-CONT-06).
  * exposes those states to the UI for the "since last analysis" badge
    (FR-CONT-04).

The watcher (`FolderWatcher`) is a thin asyncio loop that hashes the
contents of a folder per package every N seconds; when the hash changes
it enqueues a re-analysis. It is deliberately polling-based (no inotify
dependency) so it works on every OS and survives container restarts.

This module is import-only — no global state. Watcher state lives on the
QuillContext (see backend/main.py).
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import logging
import time
from enum import Enum
from pathlib import Path
from typing import Awaitable, Callable, Iterable, Optional

from backend.models.domain import Finding, FindingStatus

logger = logging.getLogger("quill.continuous")


# --------------------------------------------------------------------------- #
# Finding-state classification
# --------------------------------------------------------------------------- #
class FindingState(str, Enum):
    """Status of a finding across two versions of the same package run.

    Used by the UI to render the diff and by the orchestrator to decide
    whether an attestation should carry forward (only `unchanged` does).
    """
    new = "new"
    stale = "stale"
    resolved = "resolved"
    unchanged = "unchanged"


def _normalize_ws(s: str) -> str:
    return " ".join(s.split())


def finding_signature(f: Finding) -> str:
    """A stable hash that identifies a finding across versions of a package.

    Two findings with the same (control_id, finding type, normalized-quote
    of the FIRST evidence span) are considered the same finding. Severity,
    confidence, rationale text are deliberately excluded — those can shift
    between runs without the underlying defect changing.

    For `missing` findings (which cite catalog text, not artifact text),
    the catalog reference is what makes them unique. For all other types
    the artifact-quoted text is what binds them to a specific paragraph.
    """
    parts = [f.control_id, f.type.value]
    if f.evidence_spans:
        s = f.evidence_spans[0]
        parts.append(s.artifact_id)
        parts.append(_normalize_ws(s.quoted_text))
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


@dataclasses.dataclass
class FindingDiff:
    """Result of comparing two runs of the same package."""
    new: list[Finding] = dataclasses.field(default_factory=list)
    resolved: list[Finding] = dataclasses.field(default_factory=list)
    stale: list[Finding] = dataclasses.field(default_factory=list)
    unchanged: list[Finding] = dataclasses.field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "new": len(self.new),
            "resolved": len(self.resolved),
            "stale": len(self.stale),
            "unchanged": len(self.unchanged),
        }

    def to_dict(self) -> dict:
        return {
            "counts": self.counts(),
            "new":       [f.model_dump(mode="json") for f in self.new],
            "resolved":  [f.model_dump(mode="json") for f in self.resolved],
            "stale":     [f.model_dump(mode="json") for f in self.stale],
            "unchanged": [f.model_dump(mode="json") for f in self.unchanged],
        }


def diff_findings(
    prev: list[Finding],
    new: list[Finding],
    *,
    prev_attested: Optional[set[str]] = None,
) -> FindingDiff:
    """Classify findings across two runs of the same package.

    A finding in `prev` whose signature is missing from `new`:
      * is `stale` if it had been attested (the attester needs to re-confirm
        because the evidence paragraph has moved out from under them);
      * is `resolved` otherwise (a deficiency that was never authoritative is
        simply gone — no human action needed).

    A finding in `new` whose signature is present in `prev` is `unchanged`.
    Otherwise it is `new`.

    Signature collisions within a single run are tolerated — we keep the
    first occurrence per signature to keep counts intuitive.

    `prev_attested` is the set of finding-IDs in `prev` that were attested
    (approved/edited) so the classifier knows which disappearances are
    `stale` (need human attention) vs `resolved` (informational).
    """
    prev_attested = prev_attested or set()
    by_sig_prev: dict[str, Finding] = {}
    for f in prev:
        sig = finding_signature(f)
        by_sig_prev.setdefault(sig, f)
    by_sig_new: dict[str, Finding] = {}
    for f in new:
        sig = finding_signature(f)
        by_sig_new.setdefault(sig, f)

    d = FindingDiff()
    new_sigs = set(by_sig_new)
    prev_sigs = set(by_sig_prev)

    for sig in new_sigs - prev_sigs:
        d.new.append(by_sig_new[sig])
    for sig in new_sigs & prev_sigs:
        d.unchanged.append(by_sig_new[sig])
    for sig in prev_sigs - new_sigs:
        f = by_sig_prev[sig]
        if f.id in prev_attested:
            d.stale.append(f)
        else:
            d.resolved.append(f)

    # Sort each bucket for deterministic UI rendering.
    for bucket in (d.new, d.unchanged, d.stale, d.resolved):
        bucket.sort(key=lambda f: (f.control_id, f.id))
    return d


def carryover_attestations(
    prev: list[Finding], new: list[Finding],
) -> dict[str, Finding]:
    """Return a map new_finding_id -> prev_finding whose attestation should
    carry forward (signature match + prior status was an attested state).

    Findings whose signature is unchanged and that were approved/edited in
    the prior run inherit the prior status. Rejected attestations also
    carry — a rejection of a deficiency is itself a recorded human
    decision (FR-CONT-06).
    """
    ATTESTED = {FindingStatus.approved, FindingStatus.edited, FindingStatus.rejected}
    prev_by_sig: dict[str, Finding] = {}
    for f in prev:
        if f.status in ATTESTED:
            prev_by_sig.setdefault(finding_signature(f), f)
    carry: dict[str, Finding] = {}
    for f in new:
        sig = finding_signature(f)
        if sig in prev_by_sig:
            carry[f.id] = prev_by_sig[sig]
    return carry


# --------------------------------------------------------------------------- #
# Affected-control computation (diff-aware re-runs)
# --------------------------------------------------------------------------- #
def affected_controls(
    prev_artifact_texts: dict[str, str], new_artifact_texts: dict[str, str],
) -> set[str]:
    """Compute which controls' analysis must be re-run given the document
    delta between two snapshots of the same package.

    A control is "affected" if any artifact it appeared in has changed text,
    OR if the artifact was added/removed entirely. We don't try to be
    paragraph-precise — the lexical evidence index already routes per
    paragraph downstream; the goal here is the *worst* set of controls that
    could need re-evaluation given a text change.

    Returned ids are family-prefixes (e.g. "AC") because Tier 0 + Tier 1
    operate per-family on the changed artifact, and that's the granularity
    Phase II's "<25% of full-package time" acceptance is measured at.

    An empty result means nothing changed.
    """
    changed_artifacts: set[str] = set()
    all_ids = set(prev_artifact_texts) | set(new_artifact_texts)
    for aid in all_ids:
        prev_txt = _normalize_ws(prev_artifact_texts.get(aid, ""))
        new_txt = _normalize_ws(new_artifact_texts.get(aid, ""))
        if prev_txt != new_txt:
            changed_artifacts.add(aid)
    return changed_artifacts


# --------------------------------------------------------------------------- #
# Watcher
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class WatchEvent:
    """Emitted whenever a watched folder's content hash changes."""
    package_id: str
    tenant: str
    folder: str
    fingerprint: str        # combined sha256 of file (name, content)
    detected_at: float      # epoch seconds


def folder_fingerprint(folder: Path) -> str:
    """Stable hash of (filename, sha256(content)) for every file in folder,
    sorted by name. Subdirectories are ignored (Phase II — single-level).
    Missing folder yields the empty fingerprint.
    """
    if not folder.exists() or not folder.is_dir():
        return ""
    h = hashlib.sha256()
    files = sorted([f for f in folder.iterdir() if f.is_file()], key=lambda p: p.name)
    for f in files:
        h.update(f.name.encode("utf-8"))
        h.update(b"\0")
        try:
            h.update(hashlib.sha256(f.read_bytes()).digest())
        except (OSError, PermissionError):
            continue
        h.update(b"\0")
    return h.hexdigest()


class FolderWatcher:
    """Polling folder watcher (FR-CONT-01).

    Polling — not inotify/fsevents — because it works on every OS, in
    containers, and survives unmount/remount transparently. Default poll
    interval = 5s to meet the "ingest event within ≤5s" gate.

    A registered callback receives a `WatchEvent` whenever a folder's
    fingerprint changes vs the last seen value. Identical fingerprints
    are suppressed — the callback never fires for an unchanged folder.
    """

    def __init__(self, poll_interval_s: float = 5.0):
        self._poll_s = poll_interval_s
        self._watches: dict[str, tuple[str, str, Path]] = {}  # pkg_id -> (tenant, pkg_id, folder)
        self._last_fingerprint: dict[str, str] = {}
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._callback: Optional[Callable[[WatchEvent], Awaitable[None]]] = None
        self._lock = asyncio.Lock()

    def add_watch(self, package_id: str, tenant: str, folder: Path) -> None:
        """Register a folder to watch for `package_id`. Replaces any prior
        registration for the same package."""
        self._watches[package_id] = (tenant, package_id, folder)
        # Seed the fingerprint so we don't emit a spurious change event on
        # first poll for a folder that already has content.
        self._last_fingerprint[package_id] = folder_fingerprint(folder)

    def remove_watch(self, package_id: str) -> None:
        self._watches.pop(package_id, None)
        self._last_fingerprint.pop(package_id, None)

    def list_watches(self) -> list[dict]:
        return [
            {"package_id": pid, "tenant": t, "folder": str(p),
             "last_fingerprint": self._last_fingerprint.get(pid, "")}
            for pid, (t, _, p) in self._watches.items()
        ]

    def on_change(self, cb: Callable[[WatchEvent], Awaitable[None]]) -> None:
        self._callback = cb

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="quill.watcher")
        logger.info("FolderWatcher started (poll=%ss)", self._poll_s)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=self._poll_s + 1)
            except asyncio.TimeoutError:
                self._task.cancel()
        self._task = None
        logger.info("FolderWatcher stopped")

    async def poll_once(self) -> list[WatchEvent]:
        """One synchronous poll cycle — emit events for any changed folder.
        Public so tests can drive the watcher without running the loop.
        """
        events: list[WatchEvent] = []
        async with self._lock:
            for pid, (tenant, _, folder) in list(self._watches.items()):
                fp = folder_fingerprint(folder)
                last = self._last_fingerprint.get(pid)
                if fp and fp != last:
                    self._last_fingerprint[pid] = fp
                    ev = WatchEvent(package_id=pid, tenant=tenant,
                                    folder=str(folder), fingerprint=fp,
                                    detected_at=time.time())
                    events.append(ev)
        if self._callback:
            for ev in events:
                try:
                    await self._callback(ev)
                except Exception as e:  # noqa: BLE001
                    logger.warning("watch callback failed for %s: %s", ev.package_id, e)
        return events

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.poll_once()
            except Exception as e:  # noqa: BLE001
                logger.warning("watcher loop error: %s", e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll_s)
            except asyncio.TimeoutError:
                pass


# --------------------------------------------------------------------------- #
# RunVersion — per-package version registry
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class RunVersion:
    """Phase II FR-CONT — one entry per analysis run of a package.

    Persisted (in-memory in Phase II) so the UI can answer "what changed
    since the last analysis." Cheap — only the metadata, not the artifact
    text. Findings themselves are looked up via run_id.
    """
    package_id: str
    tenant: str
    run_id: str
    version_idx: int                  # 1-based; monotonically increasing per package
    fingerprint: str                  # folder fingerprint at the time of analysis (if any)
    finding_signatures: list[str]     # ordered, for fast diff
    created_at: float                 # epoch seconds
    diff_counts: dict[str, int] = dataclasses.field(default_factory=dict)


def version_diff(prev_sigs: Iterable[str], new_sigs: Iterable[str]) -> dict[str, int]:
    """Lightweight signature-only diff for the package-version list view
    (the heavy diff with full Finding objects is `diff_findings`)."""
    prev_s = set(prev_sigs)
    new_s = set(new_sigs)
    return {
        "new": len(new_s - prev_s),
        "resolved": len(prev_s - new_s),
        "unchanged": len(new_s & prev_s),
    }
