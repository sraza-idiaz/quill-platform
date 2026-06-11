-- QUILL Phase II Postgres schema (idempotent).
--
-- Tables map 1:1 to the entities in backend/models/domain.py and the ledgers
-- in backend/services/{audit_service,provenance_service}.py. JSONB is used
-- liberally for embedded structures (evidence_spans, missing_elements,
-- metadata) — these are queried as wholes; relational decomposition would
-- have been over-engineered for the access patterns we have.
--
-- All entity tables are TENANT-SCOPED via a `tenant` column. The Repository
-- layer is required to pass tenant on every read; the API layer is required
-- to derive tenant from the header. Cross-tenant leak protection lives at
-- those two layers; this schema is permissive.
--
-- Idempotent: CREATE TABLE IF NOT EXISTS + DO blocks for indexes / unique
-- constraints. Safe to run on every boot.

-- ---- programs (tenants) -------------------------------------------------- --
CREATE TABLE IF NOT EXISTS programs (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    baseline    TEXT NOT NULL DEFAULT 'moderate',
    framework   TEXT NOT NULL DEFAULT 'nist-800-53-rev5',
    owner       TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'active',
    description TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---- packages ------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS packages (
    id          TEXT NOT NULL,
    tenant      TEXT NOT NULL,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'draft',
    description TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant, id)
);
CREATE INDEX IF NOT EXISTS packages_tenant_idx ON packages (tenant);

-- ---- artifacts ---------------------------------------------------------- --
CREATE TABLE IF NOT EXISTS artifacts (
    id          TEXT NOT NULL,
    tenant      TEXT NOT NULL,
    type        TEXT NOT NULL,
    filename    TEXT NOT NULL,
    hash        TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'upload',
    uploaded_by TEXT,
    status      TEXT NOT NULL DEFAULT 'ingested',
    package_id  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant, id)
);
CREATE INDEX IF NOT EXISTS artifacts_tenant_idx ON artifacts (tenant);
CREATE INDEX IF NOT EXISTS artifacts_package_idx ON artifacts (tenant, package_id);

-- ---- artifact_texts (for citation validation) --------------------------- --
-- One row per artifact. Stored separately so the artifacts table stays
-- small and indexable; the normalized text can be hundreds of KB.
CREATE TABLE IF NOT EXISTS artifact_texts (
    artifact_id TEXT PRIMARY KEY,
    text        TEXT NOT NULL
);

-- ---- runs --------------------------------------------------------------- --
CREATE TABLE IF NOT EXISTS runs (
    id                      TEXT NOT NULL,
    tenant                  TEXT NOT NULL,
    artifact_id             TEXT NOT NULL,
    tier_path               JSONB NOT NULL DEFAULT '[]'::jsonb,
    model                   TEXT,
    model_version           TEXT,
    status                  TEXT NOT NULL DEFAULT 'pending',
    circuit_breaker_tripped BOOLEAN NOT NULL DEFAULT false,
    started_at              TIMESTAMPTZ,
    finished_at             TIMESTAMPTZ,
    failure_reason          TEXT,
    PRIMARY KEY (tenant, id)
);
CREATE INDEX IF NOT EXISTS runs_tenant_idx ON runs (tenant);

-- ---- findings ----------------------------------------------------------- --
CREATE TABLE IF NOT EXISTS findings (
    id                TEXT NOT NULL,
    tenant            TEXT NOT NULL,
    run_id            TEXT NOT NULL,
    control_id        TEXT NOT NULL,
    objective_id      TEXT,
    type              TEXT NOT NULL,
    severity          TEXT NOT NULL,
    confidence        DOUBLE PRECISION NOT NULL,
    recommendation    TEXT NOT NULL,
    rationale         TEXT NOT NULL DEFAULT '',
    missing_elements  JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_spans    JSONB NOT NULL DEFAULT '[]'::jsonb,
    tier              TEXT NOT NULL DEFAULT 'T0',
    status            TEXT NOT NULL DEFAULT 'unattested',
    needs_review      BOOLEAN NOT NULL DEFAULT false,
    created_at        TIMESTAMPTZ,
    PRIMARY KEY (tenant, id)
);
CREATE INDEX IF NOT EXISTS findings_run_idx ON findings (tenant, run_id);

-- ---- run_versions (Phase II FR-CONT) ------------------------------------ --
CREATE TABLE IF NOT EXISTS run_versions (
    tenant              TEXT NOT NULL,
    package_id          TEXT NOT NULL,
    run_id              TEXT NOT NULL,
    version_idx         INTEGER NOT NULL,
    fingerprint         TEXT NOT NULL DEFAULT '',
    finding_signatures  JSONB NOT NULL DEFAULT '[]'::jsonb,
    diff_counts         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (tenant, package_id, version_idx)
);
CREATE INDEX IF NOT EXISTS run_versions_lookup_idx
    ON run_versions (tenant, package_id, version_idx);

-- ---- audit_events (hash-chained ledger) --------------------------------- --
CREATE TABLE IF NOT EXISTS audit_events (
    seq         BIGSERIAL PRIMARY KEY,
    id          TEXT UNIQUE NOT NULL,
    tenant      TEXT NOT NULL,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    prev_hash   TEXT NOT NULL,
    event_hash  TEXT NOT NULL,
    at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_events_tenant_idx ON audit_events (tenant, seq);

-- ---- provenance_records (signed attestations) --------------------------- --
CREATE TABLE IF NOT EXISTS provenance_records (
    id                TEXT PRIMARY KEY,
    tenant            TEXT NOT NULL,
    finding_id        TEXT NOT NULL,
    ai_model          TEXT NOT NULL,
    ai_model_version  TEXT NOT NULL,
    proposed          JSONB NOT NULL DEFAULT '{}'::jsonb,
    decision          TEXT NOT NULL,
    edited            JSONB,
    attester          TEXT NOT NULL,
    note              TEXT NOT NULL DEFAULT '',
    signature         TEXT NOT NULL,
    signature_key_id  TEXT NOT NULL,
    signature_scheme  TEXT NOT NULL,
    signed_at         TEXT NOT NULL,
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS provenance_records_finding_idx
    ON provenance_records (tenant, finding_id);
