# System Security Plan — Atlas Logistics Risk Platform

**System:** ALRP · **Baseline:** NIST 800-53 Rev. 5 Moderate · **Status:** Draft v1

---

## Control Implementations

### AC-2 Account Management

Accounts are reviewed **monthly** by the ISSO. The enforcement
mechanism is the Acme corporate directory.

### AU-11 Audit Record Retention

Audit logs are retained for **90 days** online in the ALRP audit S3
bucket. Bucket policy enforces object-lock in compliance mode.

### AT-2 Literacy Training

Security awareness training is delivered to all ALRP personnel
**annually**. Training records are tracked in the Acme corporate LMS.

### SC-7 Boundary Protection

ALRP traffic enters through AWS WAF, then an AWS Application Load
Balancer terminating TLS 1.3. Outbound flows are restricted to AWS
service VPC endpoints.

### IA-5 Authenticator Management

Where passwords are used, the Acme directory enforces 14-character
minimum length, complexity, and rotation **every 90 days**.

### XX-99 Document Terminator

(Reserved.)
