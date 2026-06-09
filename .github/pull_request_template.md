## What does this PR do?

_Brief description._

**Resolves:** #

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor
- [ ] Eval / harness change
- [ ] Documentation
- [ ] Config (catalog / rubric)
- [ ] Security / compliance

## Component Affected

- [ ] Backend (routes / services)
- [ ] Analysis tiers (T0/T1/T2/T3)
- [ ] Audit / provenance chain
- [ ] Web UI (desktop/web)
- [ ] Eval harness / ground truth
- [ ] Tests
- [ ] Config (catalog.yaml / rubric.yaml)
- [ ] Docs

## Checklist

### Code Quality
- [ ] `ruff` / `black` formatted
- [ ] Type hints on all public functions
- [ ] Self-review completed
- [ ] No CUI/ITAR/PII in code, tests, or fixtures

### Testing
- [ ] Unit tests added / updated
- [ ] Integration tests pass
- [ ] Eval gates still pass (precision, recall, F1)
- [ ] Tested against all relevant tiers (T0/T1/T2/T3)

### Security / Compliance
- [ ] No secrets in code
- [ ] Audit chain integrity preserved
- [ ] GPG signing flow not broken
- [ ] Named-human attestation gate preserved (QUILL does NOT auto-adjudicate)
- [ ] CUI/ITAR data handling policy followed (docs/05)
- [ ] Citations preserve full provenance

### Documentation
- [ ] PRD / DECISIONS.md updated (if architectural change)
- [ ] docs/ files updated (if FR/NFR change)
- [ ] RTM (docs/08) updated (if requirements changed)
- [ ] CHANGELOG entry added

## Eval Impact

Did this PR change eval gate metrics? Report:

| Metric | Before | After |
|--------|--------|-------|
| Precision | | |
| Recall | | |
| F1 | | |

## Notes

_Anything reviewers should know._
