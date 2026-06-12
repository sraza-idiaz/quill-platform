# System Security Plan — Atlas Logistics Risk Platform

**System:** Atlas Logistics Risk Platform (ALRP)
**Baseline:** NIST SP 800-53 Rev. 5 — Moderate
**Author:** Maria Chen, ISSO
**Status:** Draft v1 (pre-adjudication)

---

## 1. System Overview

The Atlas Logistics Risk Platform (ALRP) tracks supplier delivery risk for
the Defense Logistics Agency. It is a web application processing CUI in an
AWS GovCloud (FedRAMP Moderate) environment.

---

## 2. Control Implementations

### IA-2 Identification and Authentication

Users authenticate to ALRP with a **username and password**. The Acme
corporate directory enforces password length 14 characters with mixed
case, digits, and symbols. Multi-factor authentication is performed via
TOTP at the application layer.

> **Planted contradiction #1 (IA-2):** the Architecture Document says PIV
> smart cards are required. Map should show a coral line between this SSP
> and 02_Architecture.md on IA-2.

### AC-2 Account Management

Account types include analyst, manager, ISSO, and service. The ISSO is the
responsible role for account lifecycle. **Accounts are reviewed monthly**
by the ISSO. The enforcement mechanism is the Acme corporate directory.

> **Planted contradiction #2 (AC-2):** the Identity & Access Policy says
> accounts are reviewed quarterly (every 90 days). Map should show a coral
> line between this SSP and 03_Identity_Access_Policy.md on AC-2.

### AU-11 Audit Record Retention

Audit logs are retained for **90 days** online and 1 year offline in the
ALRP audit S3 bucket. Bucket policy enforces object-lock in compliance mode.

> **Planted contradiction #3 (AU-11):** the Operations Runbook says logs
> are retained for 365 days online. Map should show a coral line between
> this SSP and 04_Operations_Runbook.md on AU-11.

### SC-7 Boundary Protection

ALRP traffic enters through an AWS Application Load Balancer terminating
TLS 1.3. The ALB is fronted by AWS WAF for OWASP rule sets. No public
endpoints exist outside the WAF.

### CM-2 Baseline Configuration

The ALRP baseline configuration is maintained in the
`atlas-logistics/terraform/prod` repository, pinned to a git SHA. Changes
require ISSO review and Change Advisory Board approval.

### IR-4 Incident Handling

Incidents involving ALRP are triaged by the Acme SOC. Critical incidents
are escalated to the ISSO within 30 minutes of detection.

### AT-2 Literacy Training

Security awareness training is inherited from the AWS GovCloud FedRAMP
SOC 2 Type II 2024 package.

---

## 3. Authorization

This section is intentionally omitted. Authorization is the AO's decision.
