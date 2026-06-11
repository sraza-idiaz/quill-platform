# System Security Plan (Draft v1)

**System name:** Acme Aerospace Supply Chain Risk System (AASCRS)
**Sponsor:** Defense Logistics Agency — Program ID DLA-26-AERO-014
**Classification:** Controlled Unclassified Information (CUI)
**Baseline:** NIST SP 800-53 Rev. 5 — Moderate
**Author:** Maria Chen, ISSO
**Last updated:** Draft — pre-adjudication

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

Out of scope for this SSP (covered under separate authorizations):

- The Acme corporate identity provider
- AWS GovCloud platform services (inherited from FedRAMP)
- The Acme network perimeter

---

## 3. Control Implementations

### AC-2 Account Management

User accounts in AASCRS include procurement analyst accounts and ISSO
administrator accounts. Account creation is initiated by the procurement
manager and confirmed by the Information System Security Officer (ISSO).

### AC-3 Access Enforcement

Access is enforced by the application based on role assignments stored in the
user account record. Roles include analyst, manager, and ISSO.

### AC-17 Remote Access

Remote access to AASCRS is only allowed through the Acme corporate VPN.
Remote users must authenticate with a password and use multi-factor
authentication.

### AT-2 Literacy Training and Awareness

Security awareness training is inherited from AWS GovCloud.

### AU-2 Event Logging

The system logs authentication events, configuration changes, and access to
supplier evidence files.

### CA-2 Control Assessments

Control assessments will be conducted as part of the RMF authorization
process.

### CM-2 Baseline Configuration

A baseline configuration is maintained for the AASCRS production environment.

### IA-2 Identification and Authentication

All AASCRS users authenticate with a username and password. The system
enforces multi-factor authentication on the Acme corporate identity provider.
PIV smart cards are accepted for federal personnel.

### IA-5 Authenticator Management

Passwords must be at least 14 characters, contain mixed case, numbers, and
symbols. Passwords are rotated every 90 days. Initial passwords are
distributed out-of-band to the user.

### IR-4 Incident Handling

Incidents involving AASCRS follow the Acme incident response procedure.

### PE-3 Physical Access Control

Physical access to AWS GovCloud data centers is inherited from AWS.

### RA-3 Risk Assessment

A risk assessment for AASCRS was conducted in 2025 by Acme's internal risk
team. The assessment identified supplier-data-integrity as the highest-risk
area.

### SC-7 Boundary Protection

Network traffic to AASCRS passes through an AWS Application Load Balancer
configured to terminate TLS 1.3. The load balancer enforces an allow-list of
Acme corporate IP ranges.

### SI-4 System Monitoring

AASCRS is monitored by the Acme SOC. Alerts above the configured threshold
are forwarded to the on-call analyst.

---

## 4. Continuous Monitoring Strategy

Continuous monitoring will be performed by the AASCRS development team in
coordination with the Acme SOC. Monthly reports will be provided to the AO.

---

## 5. Plan of Action and Milestones

POA&M items will be tracked separately in the AASCRS POA&M document.

---

## 6. Authorization Recommendation

This section is intentionally omitted. Authorization is a decision reserved
for the Authorizing Official.
