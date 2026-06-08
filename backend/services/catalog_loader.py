"""Catalog + rubric loader (FR-CAT-01..04).

Generic-first: controls, objectives, baselines, and the rubric are loaded from
YAML/OSCAL config — never hardcoded (NFR-MNT-01). Swapping the config file
changes the loaded catalog with no code change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from backend.models.domain import AssessmentObjective, Control


class Catalog:
    """Loaded control catalog + assessment objectives + selected baseline."""

    def __init__(self, data: dict):
        self.version = data.get("version", 1)
        self.source_catalog = data.get("source_catalog", "nist-800-53-rev5")
        self.assessment_catalog = data.get("assessment_catalog", "nist-800-53a-rev5")
        self.baseline = data.get("baseline", "moderate")

        self.controls: dict[str, Control] = {}
        self.objectives: dict[str, list[AssessmentObjective]] = {}
        self._required_fields: dict[str, list[str]] = {}

        for c in data.get("controls", []):
            ctrl = Control(
                control_id=c["control_id"],
                family=c.get("family", c["control_id"].split("-")[0]),
                title=c.get("title", ""),
                baselines=c.get("baselines", []),
                source_catalog=self.source_catalog,
            )
            self.controls[ctrl.control_id] = ctrl
            self._required_fields[ctrl.control_id] = c.get("required_fields", [])
            self.objectives[ctrl.control_id] = [
                AssessmentObjective(
                    objective_id=o["objective_id"],
                    control_id=ctrl.control_id,
                    text=o.get("text", ""),
                    required_methods=o.get("required_methods", []),
                )
                for o in c.get("objectives", [])
            ]

    # -- queries (FR-CAT-01..03) -------------------------------------------- #
    def get_control(self, control_id: str) -> Optional[Control]:
        return self.controls.get(control_id)

    def required_fields(self, control_id: str) -> list[str]:
        return self._required_fields.get(control_id, [])

    def baseline_controls(self, baseline: Optional[str] = None) -> list[Control]:
        """Controls required by the selected baseline (FR-CAT-03)."""
        b = baseline or self.baseline
        return [c for c in self.controls.values() if b in c.baselines]

    def objectives_for(self, control_id: str) -> list[AssessmentObjective]:
        return self.objectives.get(control_id, [])


class Rubric:
    """The evidence-sufficiency rubric (docs/03 §7)."""

    def __init__(self, data: dict):
        self.data = data
        self.family_rules: dict = data.get("family_rules", {})
        self.severity_model: dict = data.get("severity_model", {})
        self.confidence_thresholds: dict = data.get("confidence_thresholds", {})
        self.circuit_breaker_threshold: int = data.get("circuit_breaker", {}).get("threshold", 3)
        self.odp_unfilled_patterns: list[str] = data.get("odp_unfilled_patterns", [])
        self.not_determinable_methods: list[str] = data.get(
            "documentation_boundary", {}
        ).get("not_determinable_methods", ["interview", "test"])

    def required_elements(self, family: str) -> list[str]:
        return self.family_rules.get(family, {}).get("required_elements", [])

    def high_impact_families(self) -> list[str]:
        return self.severity_model.get("high_impact_families", [])

    def type_rank(self, finding_type: str) -> int:
        return self.severity_model.get("type_rank", {}).get(finding_type, 1)


def load_catalog(path: str | Path) -> Catalog:
    with open(path, "r", encoding="utf-8") as fh:
        return Catalog(yaml.safe_load(fh))


def load_rubric(path: str | Path) -> Rubric:
    with open(path, "r", encoding="utf-8") as fh:
        return Rubric(yaml.safe_load(fh))
