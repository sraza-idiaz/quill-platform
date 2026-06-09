"""QUILL domain models — Pydantic schemas.

Mirrors AXO's model style (`backend/models/*.py`). These are the core entities
from docs/04 and the PRD §4 domain model. Auth/provenance/audit models are
REUSED from AXO and not redefined here.

Hard rules enforced at the type level where possible:
  - A finding with narrative present/partial MUST carry >=1 evidence span
    (validated in the analysis pipeline; see services/analysis/citation_validator.py).
  - Finding types and statuses are constrained enums.
  - QUILL never represents an authorize/deny decision — there is deliberately
    no such field anywhere in this module.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Enums (constrained vocabularies — generic-first values live in config, but
# these structural enums are part of the contract)
# --------------------------------------------------------------------------- #
class ArtifactType(str, Enum):
    control_impl_stmt = "control_impl_stmt"
    ssp = "ssp"
    architecture = "architecture"
    oscal = "oscal"


class ArtifactStatus(str, Enum):
    ingested = "ingested"
    analyzing = "analyzing"
    reviewed = "reviewed"
    attested = "attested"
    failed = "failed"


class RunStatus(str, Enum):
    pending = "pending"
    analyzing = "analyzing"
    completed = "completed"
    failed = "failed"


class FindingType(str, Enum):
    """The finding taxonomy (FR-T2-05 / docs/03 §4)."""
    missing = "missing"
    inconsistent = "inconsistent"
    weak_narrative = "weak_narrative"
    insufficient_evidence = "insufficient_evidence"
    narrative_present_evidence_unclear = "narrative_present_evidence_unclear"


class Severity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class FindingStatus(str, Enum):
    """Finding lifecycle (FR-ATT-01). 'flag_for_review' is a deferral, not an
    asserted finding (FR-CONF-01)."""
    unattested = "unattested"
    approved = "approved"
    edited = "edited"
    rejected = "rejected"
    flag_for_review = "flag_for_review"


class Tier(str, Enum):
    t0 = "T0"
    t1 = "T1"
    t2 = "T2"
    t3 = "T3"


# --------------------------------------------------------------------------- #
# Catalog entities (loaded from config — FR-CAT)
# --------------------------------------------------------------------------- #
class Control(BaseModel):
    """An SP 800-53 Rev.5 control loaded from the OSCAL/YAML catalog."""
    control_id: str = Field(..., description="e.g. 'AC-2'")
    family: str = Field(..., description="e.g. 'AC'")
    title: str = ""
    baselines: list[str] = Field(default_factory=list, description="low|moderate|high membership")
    source_catalog: str = "nist-800-53-rev5"


class AssessmentObjective(BaseModel):
    """An 800-53A determination statement used to grade sufficiency."""
    objective_id: str = Field(..., description="e.g. 'AC-2_obj.1_det.a'")
    control_id: str
    text: str
    required_methods: list[str] = Field(
        default_factory=list,
        description="examine|interview|test — informs the documentation-boundary rule (docs/03 §3.3)",
    )


# --------------------------------------------------------------------------- #
# Artifact / run / finding entities
# --------------------------------------------------------------------------- #
class EvidenceSpan(BaseModel):
    """A traceable source span. REQUIRED on any present/partial finding (FR-T2-03).

    `quoted_text` MUST be verbatim-present in the artifact — enforced by the
    citation validator. A finding without a valid span is invalid.
    """
    artifact_id: str
    locator: str = Field(..., description="page/section/char-offset, e.g. 'p4 §2.1' or 'char:1024-1180'")
    quoted_text: str
    char_start: Optional[int] = None
    char_end: Optional[int] = None


class Artifact(BaseModel):
    id: str
    type: ArtifactType
    filename: str
    hash: str = Field(..., description="content hash computed at ingest (FR-ING-03)")
    source: str = "upload"
    uploaded_by: Optional[str] = None
    status: ArtifactStatus = ArtifactStatus.ingested
    tenant: str = "default"
    package_id: Optional[str] = Field(
        None,
        description="Phase II FR-PKG-02 — artifact's parent package (None = unassigned)."
    )
    created_at: Optional[datetime] = None


class NormalizedSegment(BaseModel):
    """Control-keyed normalized text with preserved locators (FR-ING-02)."""
    artifact_id: str
    text: str
    locator: str
    char_start: int
    char_end: int
    control_hint: Optional[str] = Field(None, description="control id if detectable deterministically")


class Run(BaseModel):
    id: str
    artifact_id: str
    tier_path: list[Tier] = Field(default_factory=list)
    model: Optional[str] = None
    model_version: Optional[str] = None
    status: RunStatus = RunStatus.pending
    circuit_breaker_tripped: bool = False
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    failure_reason: Optional[str] = None


class Finding(BaseModel):
    id: str
    run_id: str
    control_id: str
    objective_id: Optional[str] = None
    type: FindingType
    severity: Severity
    confidence: float = Field(..., ge=0.0, le=1.0, description="calibrated 0-1 (docs/03 §5.2)")
    recommendation: str
    rationale: str = ""
    missing_elements: list[str] = Field(default_factory=list)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    tier: Tier = Tier.t0
    status: FindingStatus = FindingStatus.unattested
    needs_review: bool = False
    created_at: Optional[datetime] = None


class Deferral(BaseModel):
    """A low-confidence deferral — NOT an asserted finding (FR-CONF-01)."""
    run_id: str
    control_id: str
    objective_id: Optional[str] = None
    reason: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)


class Attestation(BaseModel):
    """Reuses AXO provenance chain + GPG signature (FR-ATT-03)."""
    id: str
    finding_id: str
    attester: str
    decision: FindingStatus  # approved | edited | rejected
    note: str = ""
    signed_at: Optional[datetime] = None
    signature: Optional[str] = Field(None, description="GPG signature via AXO git_signer")
    signature_key_id: Optional[str] = None


# --------------------------------------------------------------------------- #
# Phase II — Program (multi-tenant) (docs/13_PHASE_II_PLAN §4.A FR-MT-*)
# --------------------------------------------------------------------------- #
class ProgramStatus(str, Enum):
    active = "active"
    disabled = "disabled"   # read-only; no new actions accepted


class Program(BaseModel):
    """A program (tenant) is the unit of isolation in Phase II.

    Every artifact / run / finding / attestation lives inside exactly one
    program. Users declare their active program via the X-QUILL-Tenant
    header (Phase II identity model — see §4.A FR-ID-*).

    The 'default' program exists for back-compat with Phase I and is created
    automatically at startup.
    """
    id: str                                # tenant id (used as foreign key everywhere)
    name: str                              # display name
    baseline: str = "moderate"             # low | moderate | high
    framework: str = "nist-800-53-rev5"    # catalog key
    owner: str = ""                        # declared owner identity (Phase II: just a name)
    status: ProgramStatus = ProgramStatus.active
    created_at: Optional[datetime] = None
    description: str = ""


# --------------------------------------------------------------------------- #
# Phase II — Packages (docs/13_PHASE_II_PLAN §4.C FR-PKG-*)
# --------------------------------------------------------------------------- #
class PackageStatus(str, Enum):
    """Lifecycle of an RMF package as it moves through pre-adjudication.

    Transitions (enforced server-side):
      draft -> under_review        (engineer marks ready for attestation)
      under_review -> submitted    (all findings attested + exported)
      under_review -> draft        (sent back for more work)
      submitted -> archived        (terminal; read-only)
      draft -> archived            (abandoned)
    """
    draft = "draft"
    under_review = "under_review"
    submitted = "submitted"
    archived = "archived"


# Legal status transitions. Keys = current state, values = allowed next states.
PACKAGE_STATE_MACHINE: dict[PackageStatus, set[PackageStatus]] = {
    PackageStatus.draft:        {PackageStatus.under_review, PackageStatus.archived},
    PackageStatus.under_review: {PackageStatus.draft, PackageStatus.submitted, PackageStatus.archived},
    PackageStatus.submitted:    {PackageStatus.archived},
    PackageStatus.archived:     set(),    # terminal
}


class Package(BaseModel):
    """An RMF package — a bundle of related artifacts (SSP + architecture +
    OSCAL + supplemental docs) that travel together through pre-adjudication.

    Phase II makes packages the unit of analysis: the orchestrator's
    analyze_package() runs the full pipeline across every artifact in the
    package as one logical run, so cross-artifact reasoning (FR-T0-03,
    FR-XA-*) fires across the whole bundle.
    """
    id: str                                # PKG-YYYY-XXXX or user-supplied
    tenant: str = "default"
    name: str
    status: PackageStatus = PackageStatus.draft
    description: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

