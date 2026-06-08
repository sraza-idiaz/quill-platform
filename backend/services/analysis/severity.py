"""Severity computation (docs/03 §5.1). Config-driven and explainable —
severity is documentation-deficiency severity, NEVER authorization risk.
"""

from __future__ import annotations

from backend.models.domain import FindingType, Severity
from backend.services.catalog_loader import Catalog, Rubric


def compute_severity(
    control_id: str, finding_type: FindingType, catalog: Catalog, rubric: Rubric
) -> tuple[Severity, list[str]]:
    """Return (severity, factors) so every severity is explainable."""
    factors: list[str] = []
    control = catalog.get_control(control_id)
    family = control.family if control else control_id.split("-")[0]

    score = rubric.type_rank(finding_type.value)
    factors.append(f"type_rank({finding_type.value})={score}")

    if family in rubric.high_impact_families():
        score += 1
        factors.append(f"high_impact_family({family})")

    if control and catalog.baseline in control.baselines:
        score += 1
        factors.append(f"in_baseline({catalog.baseline})")

    if score >= 6:
        sev = Severity.critical
    elif score >= 5:
        sev = Severity.high
    elif score >= 3:
        sev = Severity.medium
    else:
        sev = Severity.low
    return sev, factors
