# Atlas Logistics Risk Platform — Architecture Document

**System:** Atlas Logistics Risk Platform (ALRP)
**Architecture version:** 0.4 draft
**Author:** Daniel Park, Lead Architect

---

## 1. Topology

ALRP is a three-tier web application:
- Presentation tier: React SPA served from CloudFront
- Application tier: FastAPI on AWS ECS Fargate
- Data tier: Amazon RDS PostgreSQL 16 (Multi-AZ) + S3 evidence bucket

All tiers live in a single VPC in us-gov-west-1. No public subnets except
for the load balancer.

---

## 2. Authentication Architecture

The Acme Okta tenant authenticates all ALRP users. The Okta policy requires
**PIV smart card authentication for every federal personnel account**.
Contractor accounts authenticate with PIV smart card OR with their Acme AD
credentials followed by a FIDO2 hardware token.

> Cross-doc note: this contradicts the SSP, which says password+TOTP. The
> Identity & Access Policy agrees with this document (both require PIV).
> Cross-document map should show this as a coral edge SSP ↔ Architecture.

Session length is 8 hours. Refresh tokens are not issued. The ISSO Okta
group is reviewed every 90 days by the ISSO and the system owner jointly.

---

## 3. Boundary Protection

ALRP traffic enters through AWS WAF (geo-block + OWASP rules) → AWS
Application Load Balancer (TLS 1.3 termination) → ECS task targets.

Outbound flows are restricted to AWS service VPC endpoints (S3, KMS,
Secrets Manager). No general internet egress from application tier.

The boundary components for SC-7 are: WAF, ALB, security groups, NACLs.
The monitoring mechanism is VPC Flow Logs + GuardDuty, both feeding the
Acme SOC's Splunk SIEM.

---

## 4. Configuration Management

The ALRP infrastructure baseline is defined in the
`atlas-logistics/terraform/prod` Terraform module pinned to a git SHA.
Configuration drift is detected by AWS Config and reconciled within 5
business days per the Operations Runbook §2.

---

## 5. Data Encryption

| Layer | At-rest | In-transit |
|---|---|---|
| RDS PostgreSQL | KMS AES-256 | TLS 1.3 |
| S3 evidence bucket | KMS AES-256 | TLS 1.3 |
| Secrets Manager | KMS AES-256 | TLS 1.3 |

KMS key rotation is enabled (annual). The key (`alias/alrp-prod`) is
owned by the ALRP AWS account.

---

## 6. Inheritance

ALRP inherits the following from AWS GovCloud under AWS's FedRAMP
Moderate SOC 2 Type II 2024 authorization:

- PE-3 Physical Access Control
- PE-6 Monitoring Physical Access
- MA-2 Controlled Maintenance
- CM-4 Impact Analyses (platform-level changes)
