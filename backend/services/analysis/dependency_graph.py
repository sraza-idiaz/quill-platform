"""Phase II FR-XA-03 — Cross-artifact dependency graph.

Builds a directed graph of control-to-control references within a package
(or a single artifact). An edge `X -> Y` means: control X's narrative
mentioned control Y's identifier (e.g. AC-2's section says "in accordance
with AC-1"). The edge carries the artifact + locator + the quoted text so
the UI can deep-link to the reference.

Why this matters operationally:
  * An assessor reviewing an AC-2 finding wants to know what else in the
    package touches AC-2 — both directions:
        - controls AC-2 mentions ("AC-2 references AC-1, IA-2, ...")
        - controls that mention AC-2 ("AC-2 is referenced from CM-2, AU-2")
  * It surfaces architectural relationships and hidden dependencies that
    would otherwise require manual cross-referencing.

Deterministic Tier-0 style — no LLM. Reuses the same CONTROL_RE the
ingestion normalizer uses, so what shows up here matches what shows up in
the source pane.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from backend.models.domain import NormalizedSegment
from backend.services.catalog_loader import Catalog

# Same pattern the normalizer uses for control IDs.
CONTROL_RE = re.compile(r"\b([A-Z]{2})-(\d{1,3})(?:\(\d+\))?\b")


@dataclass
class GraphNode:
    control_id: str                        # e.g. "AC-2"
    family: str                            # e.g. "AC"
    title: str                             # e.g. "Account Management"
    in_baseline: bool                      # whether the current baseline requires it
    found_in_artifacts: list[str] = field(default_factory=list)
    inbound_degree: int = 0                # how many controls reference this one
    outbound_degree: int = 0               # how many controls this one references


@dataclass
class GraphEdge:
    from_control: str                      # the narrative belongs to this control
    to_control: str                        # this id was mentioned
    artifact_id: str
    locator: str
    quoted_text: str                       # the surrounding sentence (truncated)


@dataclass
class DependencyGraph:
    nodes: list[GraphNode]
    edges: list[GraphEdge]

    def neighbors(self, control_id: str) -> dict:
        """Convenience accessor used by the UI: returns
            { 'references': [...edges where this control is the source...],
              'referenced_by': [...edges where this control is the target...] }.
        """
        return {
            "references": [e for e in self.edges if e.from_control == control_id],
            "referenced_by": [e for e in self.edges if e.to_control == control_id],
        }

    def to_dict(self) -> dict:
        return {
            "nodes": [{
                "control_id": n.control_id, "family": n.family, "title": n.title,
                "in_baseline": n.in_baseline,
                "found_in_artifacts": n.found_in_artifacts,
                "inbound_degree": n.inbound_degree,
                "outbound_degree": n.outbound_degree,
            } for n in self.nodes],
            "edges": [{
                "from_control": e.from_control, "to_control": e.to_control,
                "artifact_id": e.artifact_id, "locator": e.locator,
                "quoted_text": e.quoted_text,
            } for e in self.edges],
        }


def build_graph(
    segments: Iterable[NormalizedSegment],
    catalog: Catalog,
    baseline: Optional[str] = None,
) -> DependencyGraph:
    """Construct the dependency graph from normalized segments.

    Nodes are added for every control that appears (either as a section
    heading in an artifact, or referenced from another control's narrative).
    Self-references are ignored. Unknown control IDs (not in the catalog)
    are skipped to keep noise out.
    """
    active = baseline or catalog.baseline
    baseline_ids = {c.control_id for c in catalog.baseline_controls(active)}
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    seen_edge: set[tuple[str, str, str, str]] = set()   # (from, to, artifact, locator)

    def _ensure_node(cid: str) -> Optional[GraphNode]:
        if cid in nodes:
            return nodes[cid]
        ctrl = catalog.get_control(cid)
        if ctrl is None:
            return None
        nodes[cid] = GraphNode(
            control_id=cid, family=ctrl.family, title=ctrl.title,
            in_baseline=cid in baseline_ids,
        )
        return nodes[cid]

    # Pass 1 — every control hosted in an artifact becomes a node, and we
    # remember which artifacts host it.
    for s in segments:
        if not s.control_hint:
            continue
        n = _ensure_node(s.control_hint)
        if n and s.artifact_id not in n.found_in_artifacts:
            n.found_in_artifacts.append(s.artifact_id)

    # Pass 2 — for each control-hinted segment, find every other valid
    # control id mentioned in its text; that's an edge from the hint to the
    # mention. De-dup on (from, to, artifact, locator) so identical hits
    # in the same paragraph don't double-count.
    for s in segments:
        if not s.control_hint:
            continue
        source_node = nodes.get(s.control_hint)
        if source_node is None:
            continue
        for fam, num in CONTROL_RE.findall(s.text):
            target_id = f"{fam}-{int(num)}"
            if target_id == s.control_hint:
                continue
            target_node = _ensure_node(target_id)
            if target_node is None:
                continue
            key = (s.control_hint, target_id, s.artifact_id, s.locator)
            if key in seen_edge:
                continue
            seen_edge.add(key)
            edges.append(GraphEdge(
                from_control=s.control_hint,
                to_control=target_id,
                artifact_id=s.artifact_id,
                locator=s.locator,
                quoted_text=s.text[:240],
            ))
            source_node.outbound_degree += 1
            target_node.inbound_degree += 1

    # Sort nodes for stable, scannable output (family then numeric id).
    def _sort_key(n: GraphNode) -> tuple:
        m = re.match(r"^([A-Z]+)-(\d+)", n.control_id)
        return (n.family, int(m.group(2)) if m else 999, n.control_id)
    sorted_nodes = sorted(nodes.values(), key=_sort_key)
    return DependencyGraph(nodes=sorted_nodes, edges=edges)
