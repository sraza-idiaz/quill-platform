# System Security Plan (Draft v2 — addresses ISSO review)

**System name:** Acme Aerospace Supply Chain Risk System (AASCRS)
**Sponsor:** Defense Logistics Agency — Program ID DLA-26-AERO-014
**Classification:** Controlled Unclassified Information (CUI)
**Baseline:** NIST SP 800-53 Rev. 5 — Moderate
**Author:** Maria Chen, ISSO
**Last updated:** Draft v2 — after first QUILL review

> Changes since v1 (per QUILL pre-adjudication findings):
> - AC-2 narrative now describes account types, responsible role, review
>   frequency, and enforcement mechanism
> - AU-2 narrative now describes event types and the review mechanism
> - IA-2 narrative now consistently states PIV-required posture
>   (matching architecture and identity policy)
> - CM-2 narrative now references the baseline-config location and the
>   change-control board
> - SC-7 narrative now describes boundary components and monitoring
>   mechanism
> - SI-4 narrative now describes monitoring objectives and alerting
>   mechanism
> - AT-2 inheritance from AWS GovCloud is now attributed to the
>   AWS FedRAMP SOC 2 Type II 2024 report

---

## 1. System Description

The Acme Aerospace Supply Chain Risk System (AASCRS) provides risk visibility
across tier-1 and tier-2 suppliers of aerospace components delivered to the
Defense Logistics Agency. The system ingests supplier financial filings,
delivery performance data, and open-source intelligence; produces a composite
supplier-risk score; and surfaces alerts when the score crosses an
organization-defined threshold.

AASCRS is deployed in an FedRAMP Moderate environment hosted on AWS GovCloud
(us-gov-west-1) under the Acme Aerospace AWS account `acme-prod-gov-001`. It
is a web application with a REST API consumed by procurement analysts. There
is no public-facing endpoint; all access is via the Acme corporate VPN with
enforced MFA.

The system processes CUI but does not process classified information.

---

## 2. System Boundary

The authorization boundary includes:

- The AASCRS web application (Python 3.12 / FastAPI)
- The supplier-risk-scoring engine (Python worker pool)
- The application database (PostgreSQL 16, managed via AWS RDS GovCloud)
- The S3 bucket `acme-aascrs-evidence-prod` containing ingested supplier filings
- The internal admin dashboard

---

## 3. Control Implementations

### AC-2 Account Management

AASCRS recognizes four **account types**: standard analyst accounts, manager
accounts, ISSO accounts, and service accounts (with an additional emergency
"break-glass" account sealed in a physical safe). Each account type carries a
distinct role and permission scope as defined in the Identity & Access
Policy §2.

The **responsible role** for account lifecycle is the Information System
Security Officer (ISSO). Account provisioning, modification, and
de-provisioning all require explicit ISSO action; emergency accounts
additionally require CISO co-signature.

Accounts are **reviewed quarterly** (every 90 days) jointly by the ISSO and
the procurement-system-owner. Accounts not confirmed during the review are
disabled within 14 calendar days. HR-driven departures trigger disable on
the next business day.

The **enforcement mechanism** is implemented via the Acme Okta tenant. Okta
group membership controls all AASCRS access; deletion from the relevant
Okta group disables access within 5 minutes. AASCRS itself performs no
local authentication.

### AC-3 Access Enforcement

Access is enforced by the application based on role assignments stored in
the user account record. Roles include analyst, manager, ISSO, and service.
Role-permission mappings are defined authoritatively in the Identity &
Access Policy §5.

### AC-17 Remote Access

Remote access to AASCRS is only allowed through the Acme corporate VPN.
Remote users must authenticate per the AASCRS authentication posture
described under IA-2.

### AT-2 Literacy Training and Awareness

Security awareness training for AASCRS personnel is **inherited from AWS
GovCloud SOC 2 Type II 2024**. A copy of the AWS GovCloud SOC 2 Type II
report (issued 2024-09) is on file with the Acme Compliance team. Acme
also provides supplemental quarterly security awareness training to all
personnel with AASCRS access; the supplemental training is owned by the
Acme CISO.

### AU-2 Event Logging

The system logs the following **event types**:

- Authentication successes and failures (per user, per source IP)
- Privileged operations (role assignment, account lifecycle, configuration
  changes, audit-log access)
- Data-handling operations (supplier-evidence read, write, delete; score
  recomputation)
- Inter-service calls (outbound supplier API; inbound procurement systems)
- Application errors at WARNING and above

The **review mechanism** is the Acme SOC's Splunk SIEM. Alert rules
aligned to the MITRE ATT&CK enterprise matrix generate analyst pages
within 30 minutes for authentication-failure bursts, off-hours privileged
operations, audit-policy changes, and unexpected outbound flows
(Operations Runbook §3.2).

### CA-2 Control Assessments

Control assessments will be conducted as part of the RMF authorization
process.

### CM-2 Baseline Configuration

A baseline configuration is maintained for the AASCRS production
environment.

The **baseline reference** is the Terraform module
`acme-aascrs/terraform/prod`, pinned to a git SHA. The currently
authoritative SHA is published in `acme-aascrs/BASELINE.md` and updated
at every quarterly review (Operations Runbook §2.1).

**Change control** follows the Acme Change Advisory Board process. Every
change request must include the proposed delta, business justification,
roll-back plan, and ISSO review note. Emergency changes skip CAB but
must be documented within 24 hours and counter-signed by the ISSO
(Operations Runbook §2.2). AWS Config drift detection alerts the SOC on
any deviation; drift is reconciled within 5 business days unless
explicitly accepted by the ISSO with a documented justification.

### IA-2 Identification and Authentication

AASCRS authentication is delegated to the Acme Okta tenant (GovCloud
edition). The authentication posture is consistent across the SSP,
Architecture Document, and Identity & Access Policy:

- **Federal personnel** authenticate with PIV smart cards. Username +
  password is not permitted for federal personnel.
- **Acme contractor personnel** authenticate with username + password
  followed by a hardware or TOTP second factor (FIDO2 hardware key,
  Okta Verify TOTP, or WebAuthn platform authenticator on an
  Acme-managed device). Push-based MFA is explicitly **not** accepted
  due to MFA-fatigue risk.
- **Service accounts** assume short-lived AWS IAM roles via STS; no
  static credentials are issued.

The **authenticator types** in play are therefore PIV (federal), password
+ hardware/TOTP MFA (contractor), and AWS IAM STS sessions (service).
The **MFA scope** is universal: every interactive session is multi-factor.

### IA-5 Authenticator Management

Where passwords are used (contractor accounts), the Acme Okta tenant
enforces minimum length 14, complexity (upper / lower / digit / symbol),
rotation every 90 days, 24-password history, and 10-attempt lockout with
a 30-minute lockout window. Initial passwords are distributed out-of-band
only; email distribution is prohibited.

### IR-4 Incident Handling

Incidents involving AASCRS follow the procedure documented in the
AASCRS Operations Runbook §5: on-call analyst acknowledgement within 30
minutes, true-positive validation, escalation to the operations lead,
ISSO engagement within 1 business hour, and a written incident report
filed with the AO within 7 business days.

### PE-3 Physical Access Control

Physical access to AWS GovCloud data centers is inherited from the
AWS GovCloud FedRAMP authorization. Acme has no physical access to the
hosting infrastructure.

### RA-3 Risk Assessment

A risk assessment for AASCRS was conducted in 2025 by Acme's internal
risk team. The assessment identified supplier-data-integrity as the
highest-risk area. The next scheduled risk assessment is 2026-Q4.

### SC-7 Boundary Protection

The AASCRS authorization boundary terminates at the **boundary components**
described in the Architecture Document §4:

- **Inbound:** AWS WAF (geo-block + OWASP rules) in front of an AWS
  Application Load Balancer enforcing Acme corporate IP allow-listing
  and TLS 1.3 termination.
- **Outbound:** VPC routing denies general internet egress; only flows
  to AWS service VPC endpoints (S3, KMS, Secrets Manager) and the
  documented supplier-data API are permitted.

The **monitoring mechanism** is AWS VPC Flow Logs and AWS GuardDuty,
both feeding into the Acme SOC's Splunk SIEM with alerting on any
unexpected boundary-crossing flow.

### SI-4 System Monitoring

AASCRS monitoring objectives are: availability detection (5 min),
integrity detection (1 h), confidentiality detection (15 min), and
performance detection (5 min) — see Operations Runbook §4.1.

The **alerting mechanism** is CloudWatch alarms forwarded to Splunk and
generating PagerDuty pages to the on-call analyst rotation, which is
monitored 24×7 by the Acme SOC.

---

## 4. Continuous Monitoring Strategy

Continuous monitoring is performed by the AASCRS development team in
coordination with the Acme SOC. Monthly reports are provided to the AO;
the report template is published in `acme-aascrs/conmon/REPORT-TEMPLATE.md`.

---

## 5. Plan of Action and Milestones

POA&M items will be tracked separately in the AASCRS POA&M document and
generated automatically from QUILL pre-adjudication findings.

---

## 6. Authorization Recommendation

This section is intentionally omitted. Authorization is a decision reserved
for the Authorizing Official.
