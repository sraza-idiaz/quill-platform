-- QUILL schema (T-2.1). Standalone — no external schema dependencies.
-- Auth/provenance/audit/change-request tables are QUILL-native and added in
-- subsequent WP-4 migrations (003+). `uploaded_by` is an INTEGER FK to the
-- QUILL `quill_users` table introduced in 003.

CREATE TABLE IF NOT EXISTS quill_artifacts (
    id              TEXT PRIMARY KEY,
    tenant          TEXT NOT NULL DEFAULT 'default',
    type            TEXT NOT NULL CHECK (type IN ('control_impl_stmt','ssp','architecture','oscal')),
    filename        TEXT NOT NULL,
    hash            TEXT NOT NULL,
    source          TEXT NOT NULL DEFAULT 'upload',
    uploaded_by     INTEGER,
    status          TEXT NOT NULL DEFAULT 'ingested'
                    CHECK (status IN ('ingested','analyzing','reviewed','attested','failed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_quill_artifacts_tenant ON quill_artifacts(tenant);

CREATE TABLE IF NOT EXISTS quill_runs (
    id                      TEXT PRIMARY KEY,
    tenant                  TEXT NOT NULL DEFAULT 'default',
    artifact_id             TEXT NOT NULL REFERENCES quill_artifacts(id) ON DELETE CASCADE,
    tier_path               TEXT[] NOT NULL DEFAULT '{}',
    model                   TEXT,
    model_version           TEXT,
    status                  TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','analyzing','completed','failed')),
    circuit_breaker_tripped BOOLEAN NOT NULL DEFAULT FALSE,
    failure_reason          TEXT,
    started_at              TIMESTAMPTZ,
    finished_at             TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_quill_runs_artifact ON quill_runs(artifact_id);

CREATE TABLE IF NOT EXISTS quill_findings (
    id                TEXT PRIMARY KEY,
    tenant            TEXT NOT NULL DEFAULT 'default',
    run_id            TEXT NOT NULL REFERENCES quill_runs(id) ON DELETE CASCADE,
    control_id        TEXT NOT NULL,
    objective_id      TEXT,
    type              TEXT NOT NULL CHECK (type IN
                      ('missing','inconsistent','weak_narrative',
                       'insufficient_evidence','narrative_present_evidence_unclear')),
    severity          TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low')),
    confidence        DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    recommendation    TEXT NOT NULL,
    rationale         TEXT NOT NULL DEFAULT '',
    missing_elements  TEXT[] NOT NULL DEFAULT '{}',
    tier              TEXT NOT NULL CHECK (tier IN ('T0','T1','T2','T3')),
    status            TEXT NOT NULL DEFAULT 'unattested'
                      CHECK (status IN ('unattested','approved','edited','rejected','flag_for_review')),
    needs_review      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_quill_findings_run ON quill_findings(run_id);

-- Evidence spans: a finding derived from narrative MUST have >=1 (FR-T2-03).
CREATE TABLE IF NOT EXISTS quill_evidence_spans (
    id            BIGSERIAL PRIMARY KEY,
    finding_id    TEXT NOT NULL REFERENCES quill_findings(id) ON DELETE CASCADE,
    artifact_id   TEXT NOT NULL,
    locator       TEXT NOT NULL,
    quoted_text   TEXT NOT NULL,
    char_start    INTEGER,
    char_end      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_quill_spans_finding ON quill_evidence_spans(finding_id);

-- Attestations reuse AXO provenance + GPG; this table links a finding to its
-- signed provenance record (provenance_records lives in AXO).
CREATE TABLE IF NOT EXISTS quill_attestations (
    id                 TEXT PRIMARY KEY,
    tenant             TEXT NOT NULL DEFAULT 'default',
    finding_id         TEXT NOT NULL REFERENCES quill_findings(id) ON DELETE CASCADE,
    attester           INTEGER NOT NULL,                 -- users(id)
    decision           TEXT NOT NULL CHECK (decision IN ('approved','edited','rejected')),
    note               TEXT NOT NULL DEFAULT '',
    signature          TEXT,                              -- GPG signature (AXO git_signer)
    signature_key_id   TEXT,
    provenance_id      INTEGER,                           -- provenance_records(id)
    signed_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_quill_attestations_finding ON quill_attestations(finding_id);
