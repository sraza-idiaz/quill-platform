"""Tier 3 cloud escalation (FR-T3-01/02). Opt-in, **disabled in air-gap mode**,
never invoked with restricted data.

The actual Claude API call is gated behind three checks any of which abort:
  1. `tier3_enabled` must be True in config.
  2. `air_gap` must be False.
  3. The artifact must not be marked `restricted`.

Implementation lives behind the same `Analyzer` Protocol so the orchestrator
can treat it identically to Tier 2 when escalation succeeds. In Phase I this is
a demo toggle: callable but disabled by default; production T3 hardening at
Phase II.
"""

from __future__ import annotations

from backend.services.analysis.tier2_sufficiency import Analyzer, SufficiencyResult


class Tier3Disabled(Exception):
    pass


class GuardedTier3Analyzer:
    """Wraps an upstream analyzer with the three safety gates."""

    name = "tier3-claude"
    version = "0"

    def __init__(self, *, enabled: bool, air_gap: bool, restricted: bool,
                 upstream: Analyzer | None = None):
        if not enabled:
            raise Tier3Disabled("tier3_enabled is False")
        if air_gap:
            raise Tier3Disabled("air-gap mode is on; Tier 3 unreachable")
        if restricted:
            raise Tier3Disabled("artifact is marked restricted; Tier 3 forbidden")
        if upstream is None:
            raise Tier3Disabled("no upstream Tier 3 analyzer configured")
        self._upstream = upstream

    def score(self, **kw) -> SufficiencyResult:  # pragma: no cover
        return self._upstream.score(**kw)
