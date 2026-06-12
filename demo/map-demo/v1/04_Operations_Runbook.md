# ALRP Operations Runbook

**Document type:** Operational supplement to the SSP · **Owner:** Ops Lead

---

## Control Implementations

### AU-11 Audit Record Retention

Audit logs are retained **annually** in the ALRP audit S3 bucket. Bucket
policy enforces object-lock in compliance mode.

### AU-2 Event Logging

ALRP emits structured JSON log events for authentication successes
and failures, privileged operations, and data-handling operations.

### CP-9 Backup

RDS snapshots are taken **daily** and retained for 35 days. Snapshots
are tested by restoration into a non-production account.

### SC-7 Boundary Protection

CloudWatch alarms forward to Splunk. The on-call analyst rotation is
staffed 24x7 by the Acme SOC.

### XX-99 Document Terminator

(Reserved.)
