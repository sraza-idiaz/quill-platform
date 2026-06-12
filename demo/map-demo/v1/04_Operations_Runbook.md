# ALRP Operations Runbook

**Document type:** Operational supplement to the SSP
**Owner:** ALRP Operations Lead
**Applies to:** Production environment

---

## 1. Configuration Baseline Management (CM-2)

The ALRP production baseline is defined by the Terraform module
`atlas-logistics/terraform/prod` pinned to a git SHA. The currently
authoritative SHA is published in `atlas-logistics/BASELINE.md` and
updated at every quarterly review.

Changes follow the Acme Change Advisory Board process. Drift detection
is performed by AWS Config; drift is reconciled within 5 business days
unless explicitly accepted by the ISSO.

---

## 2. Audit Logging Operations (AU-2, AU-11)

### 2.1 Event Types

ALRP emits structured JSON log events for:
- Authentication successes and failures
- Privileged operations (role assignment, account lifecycle,
  configuration changes, audit-log access)
- Data-handling operations (supplier-evidence read, write, delete;
  score recomputation)
- Inter-service calls (supplier API egress; procurement inbound)
- Application errors at WARNING and above

### 2.2 Retention

**Audit logs are retained for 365 days online** in the ALRP audit S3
bucket. After 365 days they transition to S3 Glacier Deep Archive for
an additional 6 years. Bucket policy enforces object-lock in
compliance mode; deletion before retention expiry is impossible even
for account admins.

> Cross-doc note: this contradicts the SSP, which says retention is 90
> days online. Map should show a coral edge SSP ↔ Operations Runbook
> on AU-11.

### 2.3 Review Mechanism

The Acme SOC reviews ALRP log events via Splunk dashboards aligned to
MITRE ATT&CK. Alert rules trigger analyst notification within 30
minutes for:
- 5+ authentication failures from one source IP in 10 minutes
- Privileged operations outside business hours (06:00–20:00 ET, M–F)
- Audit-S3 bucket policy changes
- Outbound flows outside the documented egress allow-list

---

## 3. Monitoring (SI-4)

Monitoring objectives:
- Availability: 5-minute detection target
- Integrity: 1-hour detection target
- Confidentiality: 15-minute detection for exfiltration patterns
- Performance: 5-minute detection on SLO breach

CloudWatch alarms forward to Splunk; Splunk pages PagerDuty; the on-call
analyst rotation is 24×7 staffed by the Acme SOC.

---

## 4. Incident Response (IR-4)

The SOC acknowledges alerts within 30 minutes. True positives open a
Jira ticket in `ALRP-IR` and escalate to the ALRP operations lead;
the operations lead engages the ISSO within 1 business hour. A written
incident report is filed with the AO within 7 business days.

> Cross-doc note: this matches the SSP on IR-4 (no contradiction).
> Map will show a shared-controls grey edge between this doc and the
> SSP through IR-4 and other matching controls.

---

## 5. Backup & Recovery (CP-9, CP-10)

- RDS snapshots: automated daily, retained 35 days, tested quarterly
  into a non-production account.
- S3 evidence bucket: cross-region replication to us-gov-east-1.
- Recovery time objective (RTO): 4 hours.
- Recovery point objective (RPO): 1 hour.
