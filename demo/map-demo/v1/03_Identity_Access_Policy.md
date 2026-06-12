# Identity & Access Policy — Atlas Logistics Risk Platform

**Document type:** Supplemental policy (authoritative for IA-* and AC-*)
**Owner:** Information System Security Officer
**Applies to:** ALRP authorization boundary

---

## 1. Authoritative Scope

This policy is authoritative for identity and access management on ALRP.
Where the SSP or Architecture Document conflict with this policy, this
document controls.

---

## 2. Account Types

ALRP recognizes four account types:

| Type | Purpose | Approver |
|---|---|---|
| Standard analyst | Day-to-day analyst work | Procurement manager |
| Manager | Team-lead access | Procurement director |
| ISSO | System administration | CISO |
| Service | Programmatic access (CI/CD, integrations) | ISSO |

---

## 3. Account Lifecycle

### 3.1 Provisioning

Accounts are provisioned by the ISSO based on a written request from the
approval authority listed in §2.

### 3.2 Periodic Review

**Accounts are reviewed quarterly** (every 90 days) by the ISSO and the
procurement-system-owner jointly. Accounts not confirmed during the
review are disabled within 14 calendar days.

> Cross-doc note: this contradicts the SSP, which says monthly review.
> Cross-document map should show this as a coral edge SSP ↔ Identity Policy
> on AC-2. The map should also show a shared-controls grey edge to
> Architecture (both touch IA-2).

### 3.3 De-provisioning

De-provisioning is triggered by HR notification (next business day),
review failure (14 days), or SOC compromise indication (immediate).

---

## 4. Authentication Posture

All ALRP users must authenticate via the Acme Okta tenant. The required
authenticators are:

- **Federal personnel:** PIV smart card. Username + password is NOT
  acceptable for federal personnel.
- **Contractor personnel:** PIV smart card OR Acme AD credentials with
  a FIDO2 hardware token. Push-based MFA is NOT acceptable.
- **Service accounts:** short-lived AWS IAM role assumption (15-minute
  STS sessions). No static credentials.

> Cross-doc note: this agrees with the Architecture Document and
> contradicts the SSP. The map will show a coral SSP↔Identity edge on
> IA-2 in addition to the SSP↔Architecture edge.

---

## 5. Roles

Role-to-permission mappings are authoritative in this document:

| Role | Reads | Writes | Admin |
|---|---|---|---|
| Standard analyst | Suppliers, scores | Annotations | — |
| Manager | All above + reports | All above + report config | — |
| ISSO | Everything | Everything | System config, audit |
| Service (ingest) | Supplier evidence | Append evidence | — |

The `admin` role does NOT auto-grant attestation authority. Attestation
is a separate explicit role grant tracked in Appendix A.
