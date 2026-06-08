-- Role enum for QUILL users (FR-API-02). The full users table is added in the
-- WP-4 auth migration; this migration is a placeholder to record the canonical
-- role set so future migrations reference a stable enum:
--
--   admin | engineer | attester | viewer
--
-- `attester` is the role required to approve/edit/reject findings (FR-ATT-03).
SELECT 1;
