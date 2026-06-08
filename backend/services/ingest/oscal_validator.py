"""Lightweight OSCAL structural validation (FR-T0-04). Deterministic, no LLM.

Full OSCAL JSON-Schema validation (via jsonschema against the official OSCAL
schema) is wired in at scaffold hardening; this structural check catches the
common, high-signal violations without the heavy schema dependency so Tier 0
can flag malformed OSCAL packages today. Returns a list of human-readable
violation strings (empty = structurally valid).
"""

from __future__ import annotations

import json
from pathlib import Path


def validate_oscal_structure(data: dict) -> list[str]:
    violations: list[str] = []
    ssp = data.get("system-security-plan")
    if ssp is None:
        # Allow bare control-implementation docs, else require the SSP root.
        if "control-implementation" not in data:
            return ["missing 'system-security-plan' root (or 'control-implementation')"]
        ssp = data

    if "uuid" not in ssp and "system-security-plan" in data:
        violations.append("system-security-plan: missing 'uuid'")
    if "metadata" not in ssp and "system-security-plan" in data:
        violations.append("system-security-plan: missing 'metadata'")

    impl = ssp.get("control-implementation", {})
    reqs = impl.get("implemented-requirements")
    if not reqs:
        violations.append("control-implementation: no 'implemented-requirements'")
        return violations

    for i, req in enumerate(reqs):
        if not req.get("control-id"):
            violations.append(f"implemented-requirements[{i}]: missing 'control-id'")
    return violations


def validate_oscal_file(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return [f"invalid JSON: {e}"]
    return validate_oscal_structure(data)
