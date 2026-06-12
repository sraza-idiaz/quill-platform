# System Security Plan — Atlas Logistics Risk Platform

**System:** Atlas Logistics Risk Platform (ALRP)
**Baseline:** NIST SP 800-53 Rev. 5 — Moderate
**Author:** Maria Chen, ISSO
**Status:** Draft v2 — after first QUILL review

> Changes since v1 (resolves all three cross-document contradictions
> QUILL flagged):
> - IA-2: now consistent with Architecture + Identity Policy (PIV required)
> - AC-2: review frequency now consistent with Identity Policy (quarterly)
> - AU-11: retention now consistent with Operations Runbook (365 days)

---

## 1. System Overview

The Atlas Logistics Risk Platform (ALRP) tracks supplier delivery risk for
the Defense Logistics Agency. It is a web application processing CUI in an
AWS GovCloud (FedRAMP Moderate) environment.

---

## 2. Control Implementations

### IA-2 Identification and Authentication

ALRP authentication is delegated to the Acme Okta tenant. The
authentication posture is consistent across the SSP, Architecture
Document, and Identity & Access Policy:

- **Federal personnel:** PIV smart card. Username + password is not
  permitted for federal personnel.
- **Contractor personnel:** PIV smart card or Acme AD credentials with
  a FIDO2 hardware token. Push-based MFA is explicitly not accepted
  due to MFA-fatigue risk.
- **Service accounts:** short-lived AWS IAM role assumption (15-min STS
  sessions). No static credentials are issued.

### AC-2 Account Management

Account types are: analyst, manager, ISSO, and service. The ISSO is the
responsible role for account lifecycle.

**Accounts are reviewed quarterly** (every 90 days) jointly by the ISSO
and the procurement-system-owner, per the Identity & Access Policy §3.2.
Accounts not confirmed during review are disabled within 14 calendar
days. The enforcement mechanism is the Acme Okta tenant.

### AU-11 Audit Record Retention

**Audit logs are retained for 365 days online** in the ALRP audit S3
bucket, per the Operations Runbook §2.2. After 365 days they transition
to S3 Glacier Deep Archive for an additional 6 years. Bucket policy
enforces object-lock in compliance mode.

### SC-7 Boundary Protection

ALRP traffic enters through AWS WAF (geo-block + OWASP rules) → AWS
Application Load Balancer (TLS 1.3 termination) → ECS task targets.
Outbound flows are restricted to AWS service VPC endpoints. The
boundary monitoring mechanism is VPC Flow Logs + AWS GuardDuty feeding
the Acme SOC's Splunk SIEM.

### CM-2 Baseline Configuration

The ALRP baseline configuration is maintained in
`atlas-logistics/terraform/prod`, pinned to a git SHA. Changes follow
the Acme Change Advisory Board process; drift is detected by AWS
Config and reconciled within 5 business days unless explicitly
accepted by the ISSO.

### IR-4 Incident Handling

Incidents involving ALRP are triaged by the Acme SOC per the Operations
Runbook §4. Critical incidents escalate to the ISSO within 30 minutes;
a written incident report is filed with the AO within 7 business days.

### AT-2 Literacy Training

Security awareness training is inherited from the AWS GovCloud FedRAMP
SOC 2 Type II 2024 package.

---

## 3. Authorization

This section is intentionally omitted. Authorization is the AO's decision.
