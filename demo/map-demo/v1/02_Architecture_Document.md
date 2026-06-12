# Atlas Logistics Risk Platform — Architecture Document

**Architecture version:** 0.4 draft · **Author:** Daniel Park

---

## Control Implementations

### IA-2 Identification and Authentication

The Acme Okta tenant authenticates all ALRP users. Federal personnel
must authenticate via PIV smart card. The ISSO Okta group membership
is reviewed **quarterly**.

### SC-7 Boundary Protection

ALRP traffic enters through AWS WAF, an AWS Application Load Balancer
terminating TLS 1.3, then ECS task targets. Outbound flows are
restricted to AWS service VPC endpoints.

### SC-13 Cryptographic Protection

All data is encrypted at rest using KMS-managed AES-256 keys. Key
rotation is enabled **annually**.

### AC-3 Access Enforcement

The Acme Okta tenant enforces role-based access at sign-in. ALRP roles
map to Okta groups; group membership controls all access.

### XX-99 Document Terminator

(Reserved.)
