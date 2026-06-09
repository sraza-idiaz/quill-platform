# Contributing to QUILL

QUILL is an AI-assisted RMF pre-adjudication terminal for DLA SBIR topic DLA26BZ02-NV006. It informs; humans decide. QUILL **never** makes the authorization decision.

## How to Contribute

### Reporting Bugs
- Use the [Bug Report](../../issues/new?template=bug-report.md) template
- Include QUILL version, Python version, active tier (T0–T3)
- **Never include actual CUI/ITAR/PII data** in bug reports

### Eval Gate Failures
- Use the [Eval Failure](../../issues/new?template=eval-failure.md) template
- Include before/after metrics and run references

### Security / Compliance Issues
- Use the [Security](../../issues/new?template=security.md) template
- For exploitable vulnerabilities, email the maintainer directly

### Submitting Code

1. Fork the repository
2. Create a branch: `git checkout -b feature/your-feature`
3. Make changes following standards below
4. Run tests: `pytest tests/`
5. Run eval gates locally: `python -m eval.harness`
6. Commit: `git commit -m "feat(analysis): improve T1 citation validator"`
7. Push and open a Pull Request

## Development Setup

### Prerequisites
- Python 3.12+
- `ollama` (for T2/T3 LLM tiers)
- GPG (for provenance signing)

### Getting Started

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
uvicorn backend.main:app --port 8000
```

Open http://localhost:8000/ui/

### Running LLM Tiers (T2/T3)

```bash
ollama serve &
ollama pull mistral:7b           # or mistral-small:24b for PRD
```

### Running Eval Gates

```bash
python -m eval.harness --tier all
```

## Coding Standards

### Python
- Python 3.12+ with full type hints
- `black` for formatting
- `ruff` for linting
- Docstrings on all public functions (Google style)
- Async I/O preferred for routes

### Architecture Principles
- **Tier separation:** T0/T1/T2/T3 must remain independently testable
- **Attestation gate:** No code path may bypass named-human attestation
- **Audit chain:** Every finding must produce a signed provenance entry
- **Citation integrity:** Citations must be preserved through all tier transitions

## Security & Compliance Requirements

### Forbidden in Code
- Real CUI / ITAR / PII data (use synthetic fixtures only)
- Hardcoded secrets, API keys, or credentials
- Code paths that bypass attestation
- Logic that allows QUILL to make authorization decisions

### Required for All Changes
- Audit chain integrity preserved
- GPG signing flow unbroken
- Citations traceable to source
- Synthetic test fixtures only

### NIST SP 800-53 Mapping
Major changes should reference applicable controls (AC-3, AU-9, SI-7, etc.) in the PR description.

## Commit Convention

Format: `type(scope): description`

- `feat:` New feature
- `fix:` Bug fix
- `refactor:` Code restructuring
- `eval:` Eval harness or ground truth changes
- `docs:` Documentation
- `test:` Test changes
- `chore:` Maintenance
- `security:` Security/compliance fix

Scopes: `routes`, `analysis`, `audit`, `ingest`, `eval`, `ui`, `config`

## Branch Naming

- `feature/description`
- `fix/description`
- `eval/description`
- `docs/description`

## Code of Conduct

Please read our [Code of Conduct](CODE_OF_CONDUCT.md).
