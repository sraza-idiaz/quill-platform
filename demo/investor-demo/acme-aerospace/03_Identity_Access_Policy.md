# Identity & Access Policy — AASCRS

**Document type:** Supplemental Policy
**Owner:** Information System Security Officer
**Applies to:** AASCRS authorization boundary
**Last revised:** 2026-04

---

## 1. Purpose

This policy describes the authoritative identity and access management
requirements for the Acme Aerospace Supply Chain Risk System. It complements
the SSP and the Architecture Document; where they conflict with this
document, this policy is authoritative.

---

## 2. Account Types

AASCRS recognizes four account types. The Information System Security
Officer (ISSO) maintains an authoritative list of accounts of each type:

| Account type | Purpose | Approval authority |
|---|---|---|
| Standard analyst | Procurement analyst day-to-day work | Procurement manager |
| Manager | Procurement-team lead with reporting access | Procurement director |
| ISSO | System-administrative control | CISO |
| Service | Programmatic API access (CI/CD, integrations) | ISSO |
| Emergency | Break-glass account, sealed until incident | CISO + ISSO (dual approval) |

The emergency account is a single shared account whose credentials are
sealed in a physical safe at the Acme operations center. Use of the
emergency account triggers an automatic SOC notification.

---

## 3. Account Lifecycle

### 3.1 Provisioning

New accounts are provisioned by the ISSO based on a written request from
the relevant approval authority (see §2). The request must include:

- The requested account type
- The business justification
- The expected duration (if temporary)
- Identification confirming federal personnel status (for PIV requirement)

### 3.2 Modification

Role changes are approved by the same authority as initial provisioning.
A role change requires re-attestation by the new approver.

### 3.3 Review

Accounts of all types are reviewed quarterly (every 90 days) jointly by
the ISSO and the procurement-system-owner. The review confirms:

- The account is still needed for the user's role
- The role assignment is still appropriate
- The user has not departed Acme

Accounts not confirmed during the review are disabled within 14 calendar
days.

### 3.4 De-provisioning

Account de-provisioning is triggered by:

- HR notification of employee departure (next business day)
- Failure to confirm during quarterly review (14 days)
- Compromise indication from the SOC (immediate)

De-provisioned accounts are not deleted; they are disabled with a
de-provisioned tag and a retention period of 7 years to support audit
inquiries.

---

## 4. Authenticator Requirements

### 4.1 Federal personnel

Federal personnel **must** authenticate with a PIV smart card. Username +
password authentication is not permitted for federal personnel. This
matches the architecture document (§2) and is enforced by the Acme Okta
tenant.

### 4.2 Contractor personnel

Acme contractor personnel authenticate with their Acme Active Directory
credentials (username + complex password) and a second factor. Acceptable
second factors are:

- TOTP via Okta Verify
- FIDO2 hardware security key
- WebAuthn platform authenticator on an Acme-managed device

Push notifications are explicitly **not** acceptable due to MFA-fatigue
risk.

### 4.3 Service accounts

Service accounts authenticate with short-lived AWS IAM role assumption
(15-minute STS sessions, no static keys). The role-assumption policy is
restricted by source IP (corporate VPN egress range) and by the requesting
ECS task's identity.

### 4.4 Password policy (contractor accounts only)

Where passwords are used:

| Requirement | Value |
|---|---|
| Minimum length | 14 characters |
| Complexity | Must include uppercase, lowercase, digit, symbol |
| Rotation | Every 90 days |
| History | Last 24 passwords blocked |
| Lockout | 10 consecutive failures, 30-minute lockout |
| Distribution | Out-of-band only; never via email |

---

## 5. Roles and Permissions

Roles in AASCRS map to Okta groups. The following table is authoritative:

| Role | Reads | Writes | Admin |
|---|---|---|---|
| Standard analyst | Suppliers, scores | Annotations | — |
| Manager | All above + reports | All above + report config | — |
| ISSO | Everything | Everything | System config, audit |
| Service (ingest) | Supplier evidence | Append evidence only | — |
| Service (reporting) | All supplier data | — | — |

**Admin role does not auto-grant attestation authority.** Attestation
authority is a separate role held only by named individuals listed in
Appendix A of this policy.

---

## 6. Periodic Attestation

The ISSO conducts a quarterly attestation review for the AASCRS production
environment. The attestation covers:

- Active account list reconciled against HR
- Role assignments reconciled against approval requests
- Service-account scope and recent activity
- Emergency-account seal verification

A signed attestation record is filed with the Acme records-retention
service and a copy is included in the AASCRS audit bundle.

---

## Appendix A — Named Attesters

The following individuals are authorized to perform attestation actions:

- Maria Chen, ISSO (primary)
- Daniel Park, Lead Architect (backup)
- The Acme CISO (override only, on documented exception)

This list is reviewed annually and updated by the Acme CISO.
