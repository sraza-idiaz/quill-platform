"""Phase II FR-CAT-01..04 — convert the NIST OSCAL JSON catalog + Low/Moderate/
High baseline profiles into a compact QUILL catalog YAML.

Inputs (relative to repo root):
  config/oscal-cache/catalog.json
  config/oscal-cache/profile-LOW.json
  config/oscal-cache/profile-MODERATE.json
  config/oscal-cache/profile-HIGH.json

Output:
  config/catalog-nist-800-53-rev5.yaml

The output keeps QUILL's existing schema (`Catalog`/`load_catalog`) — no
loader change required to use it. Family-level `required_fields` carry from
the small sample catalog where defined; new families get an empty list so
Tier 0's required-field check is silent for them (rubric.yaml can fill in
per-family elements over time).

Run:
    python -m scripts.convert_oscal_catalog
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "config" / "oscal-cache"
OUT = ROOT / "config" / "catalog-nist-800-53-rev5.yaml"

# Inherit required_fields from the existing sample catalog so the few
# families we've already authored rules for keep working.
REQUIRED_FIELDS: dict[str, list[str]] = {
    "AC-2":  ["account_types", "responsible_role", "review_frequency", "enforcement_mechanism"],
    "AU-2":  ["event_types", "review_mechanism"],
    "IA-2":  ["authenticator_types", "mfa_scope"],
    "CM-2":  ["baseline_reference", "change_control"],
    "SC-7":  ["boundary_components", "monitoring_mechanism"],
    "SI-4":  ["monitoring_objectives", "alerting_mechanism"],
}


def _norm_id(raw: str) -> str:
    """OSCAL stores control ids as `ac-2`, `ac-2.1`. QUILL uses `AC-2`,
    `AC-2(1)` (NIST 800-53 native form). Convert."""
    raw = raw.strip().upper()
    # `AC-2.1` → `AC-2(1)`; leave plain `AC-2` alone
    m = re.match(r"^([A-Z]{2})-(\d+)(?:\.(\d+))?$", raw)
    if not m:
        return raw
    fam, base, enh = m.groups()
    if enh:
        return f"{fam}-{base}({enh})"
    return f"{fam}-{base}"


def _flatten_controls(node: dict, out: list[dict]) -> None:
    """OSCAL catalogs nest enhancements (`ac-2.1`) inside their parent
    (`ac-2`). Flatten so the QUILL catalog sees them as siblings."""
    for c in node.get("controls", []) or []:
        out.append(c)
        _flatten_controls(c, out)


def _props_get(node: dict, name: str) -> list[str]:
    """Return all values of OSCAL property `name` on a node."""
    return [p.get("value") for p in (node.get("props") or []) if p.get("name") == name]


def _baseline_membership(profile_path: Path) -> set[str]:
    """A profile JSON includes the set of control ids in that baseline."""
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    ids: set[str] = set()
    for imp in data["profile"].get("imports", []):
        for inc in (imp.get("include-controls") or []):
            for raw_id in inc.get("with-ids", []) or []:
                ids.add(_norm_id(raw_id))
    return ids


def _statement_text(stmt: dict) -> str:
    """Strip the OSCAL prose of trivial control-tag wrappers and return a
    short, human-readable text for the assessment objective. We use the
    statement's prose if present, otherwise its name."""
    parts = []
    if "prose" in stmt:
        parts.append(re.sub(r"\{\{\s*[\w\-.]+\s*\}\}", "[parameter]",
                            stmt["prose"]).strip())
    return " ".join(parts).strip()


def _objectives_from_statements(control: dict) -> list[dict]:
    """OSCAL controls have a tree of `parts` whose `name == 'statement'`.
    Each top-level statement is an assessment objective candidate. We take
    the immediate-child statements and emit one objective per statement,
    using the statement id + prose."""
    parts = control.get("parts") or []
    statements = [p for p in parts if p.get("name") == "statement"]
    objectives: list[dict] = []
    for s in statements:
        text = _statement_text(s)
        if not text:
            continue
        objectives.append({
            "objective_id": s.get("id", "").upper() or f"{control['id'].upper()}_obj",
            "text": text,
            "required_methods": ["examine"],   # default; assessment-procedures catalog refines this
        })
    # If the control has no parts (rare), synthesize a single objective from the control title.
    if not objectives and control.get("title"):
        objectives.append({
            "objective_id": f"{control['id'].upper().replace('.', '_')}_obj.a",
            "text": control["title"],
            "required_methods": ["examine"],
        })
    return objectives[:8]  # keep at most 8 to bound prompt size


def convert() -> dict:
    catalog_data = json.loads((CACHE / "catalog.json").read_text(encoding="utf-8"))
    catalog_root = catalog_data["catalog"]

    low_ids = _baseline_membership(CACHE / "profile-LOW.json")
    mod_ids = _baseline_membership(CACHE / "profile-MODERATE.json")
    high_ids = _baseline_membership(CACHE / "profile-HIGH.json")

    out_controls: list[dict] = []
    for group in catalog_root.get("groups", []):
        family = group.get("id", "").upper()
        flat: list[dict] = []
        _flatten_controls(group, flat)
        for c in flat:
            cid = _norm_id(c.get("id", ""))
            if not cid:
                continue
            baselines: list[str] = []
            if cid in low_ids:  baselines.append("low")
            if cid in mod_ids:  baselines.append("moderate")
            if cid in high_ids: baselines.append("high")
            # Skip controls that aren't in ANY baseline (PM family etc.); they're
            # informational and don't drive coverage findings.
            if not baselines:
                continue
            entry: dict = {
                "control_id": cid,
                "family": family,
                "title": c.get("title", "").strip(),
                "baselines": baselines,
                "objectives": _objectives_from_statements(c),
            }
            if cid in REQUIRED_FIELDS:
                entry["required_fields"] = REQUIRED_FIELDS[cid]
            out_controls.append(entry)

    out_controls.sort(key=lambda x: (x["family"], _sort_within_family(x["control_id"])))
    return {
        "version": 1,
        "source_catalog": "nist-800-53-rev5",
        "assessment_catalog": "nist-800-53a-rev5",
        "baseline": "moderate",
        "controls": out_controls,
    }


def _sort_within_family(cid: str) -> tuple:
    m = re.match(r"^([A-Z]{2})-(\d+)(?:\((\d+)\))?$", cid)
    if not m:
        return (999, 999)
    return (int(m.group(2)), int(m.group(3) or 0))


if __name__ == "__main__":
    out = convert()
    OUT.write_text(yaml.safe_dump(out, sort_keys=False, width=120), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  controls: {len(out['controls'])}")
    by_baseline = {b: sum(1 for c in out['controls'] if b in c['baselines'])
                   for b in ("low", "moderate", "high")}
    print(f"  in low:      {by_baseline['low']}")
    print(f"  in moderate: {by_baseline['moderate']}")
    print(f"  in high:     {by_baseline['high']}")
    fams = sorted({c['family'] for c in out['controls']})
    print(f"  families:    {len(fams)} ({', '.join(fams)})")
