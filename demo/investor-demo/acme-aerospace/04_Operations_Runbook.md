# AASCRS Operations Runbook

**Document type:** Operational supplement to SSP
**Owner:** AASCRS Operations Lead
**Applies to:** Production environment (acme-prod-gov-001)
**Last revised:** 2026-05

---

## 1. Purpose

This runbook documents the operational procedures that implement the
technical controls described in the SSP. Each section maps to one or more
NIST SP 800-53 Rev. 5 controls; where the SSP states a control narrative,
this runbook describes the as-built procedure.

---

## 2. Configuration Baseline Management (CM-2)

### 2.1 Baseline reference

The AASCRS production baseline is defined by:

- Terraform module `acme-aascrs/terraform/prod` pinned to a git SHA
- ECS task definitions in `acme-aascrs/ecs/prod-tasks.json`
- The frozen Amazon Machine Image (AMI) ID for the build agents

The current baseline is published in `acme-aascrs/BASELINE.md` and the
git SHA + AMI ID is updated on every quarterly review.

### 2.2 Change control

Configuration changes follow Acme's change-advisory-board (CAB) process.
A change request must include:

- The proposed configuration delta
- The justification
- A roll-back plan
- The ISSO's review note

Emergency changes (e.g. incident response patches) skip the CAB and are
documented within 24 hours in the next CAB meeting. The ISSO must
counter-sign any emergency change record.

### 2.3 Drift detection

AWS Config rules detect drift from the baseline and forward alerts to the
SOC. The most recent drift-detection report is filed in the AASCRS audit
S3 bucket. Drift is reconciled within 5 business days unless explicitly
accepted by the ISSO with a documented justification.

---

## 3. Audit Logging Operations (AU-2, AU-6)

### 3.1 Event types captured

The AASCRS application emits structured JSON log events for:

- Authentication successes and failures
- Privileged operations (role assignment, account lifecycle, configuration
  changes, audit-log access)
- Data-handling operations (supplier-evidence read, write, delete; score
  recomputation)
- Inter-service calls (outbound to supplier API, inbound from procurement
  systems)
- Application errors at WARNING or above

Each event carries: timestamp (RFC3339), actor (Okta sub claim), action,
resource, source IP, request ID, outcome.

### 3.2 Review mechanism

The Acme SOC reviews AASCRS log events via Splunk dashboards aligned to
the MITRE ATT&CK enterprise matrix. Alert rules trigger an analyst
notification within 30 minutes for:

- 5 or more authentication failures from one source IP within 10 minutes
- Any privileged operation outside business hours (defined as 06:00–20:00
  US ET, Monday–Friday)
- Any change to the AASCRS audit-S3 bucket policy
- Any outbound flow that doesn't match the documented egress allow-list

### 3.3 Retention

Audit records are retained for 365 days online and 7 years offline in the
AASCRS audit S3 bucket. Bucket policy enforces object-lock in compliance
mode; logs cannot be deleted before retention expiry, even by an account
admin.

---

## 4. System Monitoring (SI-4)

### 4.1 Monitoring objectives

- **Availability:** detect AASCRS application outages within 5 minutes
- **Integrity:** detect unexpected database writes or unauthorized
  configuration changes within 1 hour
- **Confidentiality:** detect data exfiltration patterns (large outbound
  S3 transfers, off-hours bulk supplier-data exports) within 15 minutes
- **Performance:** detect API latency degradation crossing the
  organization-defined SLO threshold within 5 minutes

### 4.2 Alerting mechanism

CloudWatch alarms forward to Splunk via the AASCRS log pipeline. Splunk
alert rules generate PagerDuty pages to the on-call analyst rotation.
The SOC queue is monitored 24×7.

### 4.3 Threshold tuning

Alert thresholds are reviewed quarterly during the AASCRS quarterly
attestation cycle. Threshold changes require ISSO sign-off and are
documented in the threshold-history log retained alongside the audit
records.

---

## 5. Incident Response (IR-4)

### 5.1 Detection sources

Incidents are detected by:

- Splunk alerts (§4.2)
- AWS GuardDuty findings forwarded to the SOC
- User reports via the Acme Service Desk (`servicedesk@acme.com`)
- External notifications (e.g. CISA bulletins, third-party threat intel)

### 5.2 Response procedure

For any AASCRS-related incident, the on-call analyst:

1. Acknowledges the alert within 30 minutes
2. Validates the alert (true positive vs. tuning issue)
3. If true positive: opens a Jira ticket in project `AASCRS-IR` and
   escalates to the AASCRS operations lead
4. The operations lead engages the ISSO within 1 business hour
5. Containment actions are documented as they are taken
6. Post-incident, a written incident report is filed within 7 business
   days with the AO

---

## 6. Vulnerability Management (RA-5, SI-2)

- **Container image scanning:** Trivy runs on every CI build and on a
  weekly cron scan of the production registry.
- **Dependency scanning:** Snyk runs on every pull-request and weekly on
  the main branch.
- **OS patching:** Fargate-managed; we pin to the latest Amazon ECS
  optimized image and rebuild monthly.
- **Critical CVEs** (CVSS ≥ 9.0 affecting AASCRS components) are
  remediated within 7 calendar days. High CVEs (7.0–8.9): 30 calendar
  days. Medium CVEs: next quarterly review.

A vulnerability scan summary is filed quarterly with the Acme CISO.

---

## 7. Backup & Recovery (CP-9, CP-10)

- RDS snapshots: automated daily, retained 35 days. Tested restoration
  quarterly into a non-production account.
- S3 evidence bucket: cross-region replication to `us-gov-east-1` with a
  35-day lifecycle to Glacier Deep Archive.
- Application config (Terraform state): versioned in S3 with object lock.

Recovery-time objective (RTO): 4 hours for the application tier; 24
hours for evidence retrieval from cold storage. Recovery-point
objective (RPO): 1 hour.

---

## 8. Documentation Bibliography

This runbook references but does not duplicate:

- The AASCRS SSP (master compliance document)
- The AASCRS Architecture Document (technical topology)
- The AASCRS Identity & Access Policy (account lifecycle authority)
- The Acme Incident Response Plan (corporate-level IR procedures)
- The AWS GovCloud FedRAMP authorization letter (platform inheritance)
