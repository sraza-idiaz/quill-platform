# Security Policy

## Reporting a Vulnerability

**Do not report security vulnerabilities through public GitHub issues.**

For exploitable vulnerabilities, email the project maintainer directly. Include:
- Description of the vulnerability
- Steps to reproduce (using synthetic data only)
- Potential impact (CUI/ITAR, audit chain, attestation bypass, etc.)
- Affected NIST SP 800-53 controls
- Suggested remediation (if known)

We will acknowledge receipt within 48 hours.

For non-exploitable concerns, use the [Security Issue](../../issues/new?template=security.md) template.

## Security Architecture

QUILL is designed for U.S. Government RMF workflows. Security is foundational, not bolted on.

### Core Principles

1. **QUILL never adjudicates.** Every finding must pass through a named-human attestation gate. No code path bypasses this.
2. **Tamper-evident audit chain.** All actions are logged with signed provenance. The chain is verifiable end-to-end.
3. **Citation preservation.** Every claim is traceable to its source artifact and NIST control.
4. **No CUI in code or repo.** All test fixtures are synthetic.

### NIST SP 800-53 Alignment

QUILL implements controls relevant to its operation as a pre-adjudication aid:

- **AC-3** Access Enforcement
- **AC-6** Least Privilege
- **AU-2** Audit Events
- **AU-3** Content of Audit Records
- **AU-9** Protection of Audit Information
- **AU-10** Non-repudiation
- **AU-12** Audit Record Generation
- **IA-5** Authenticator Management
- **SC-12** Cryptographic Key Establishment
- **SC-13** Cryptographic Protection
- **SI-7** Software, Firmware, and Information Integrity

### Data Handling
- See `docs/05_DATA_HANDLING_CUI_ITAR_POLICY.md` for the full policy
- No real CUI/ITAR/PII data in this repository
- Synthetic corpus only in `eval/`

### Cryptographic Provenance
- All findings and attestations GPG-signed
- Audit chain uses hash linking (tamper-evident)
- Key management documented in operations runbook

### Dependencies
- Dependabot monitors pip and GitHub Actions
- Security advisories tracked
- Critical CVEs patched within 7 days
