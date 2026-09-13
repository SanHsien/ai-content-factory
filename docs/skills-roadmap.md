# Skills roadmap

This roadmap separates present local evidence from future capability. It does
not authorize work outside the current offline staging boundary.

| Capability/skill | Phase 1 state | Evidence in this tree | Future evidence required |
| --- | --- | --- | --- |
| Deterministic pipeline orchestration | `IMPLEMENTED` | Local stage state, stable run ID, resumable artifacts, and validation tests | Broader fixture matrix and migration policy for a later schema |
| Standard-library security scans | `IMPLEMENTED` | Redacted secret, hashed-brand, and private-path scans with unit tests | Broader fixtures, false-positive review, and owner-maintained fingerprint process |
| Provenance and evidence writing | `IMPLEMENTED` | Ledger, labels, limits, sanitized contribution rules, and Stranger Test | Independent reviewer record and repeatable package evidence |
| Fixture-only provider contracts | `LOCAL_VERIFIED` | Structured research/text/media contracts, deterministic synthetic fixtures, and no remote URI fields | Contract tests for each approved external adapter, privacy and cost decision, credential lifecycle, and rights review |
| Local media/claim QA | `IMPLEMENTED` for contract checks | Placeholder media descriptors, stage scorecard, bounded evidence statuses | Deterministic quality fixtures, current-source review, rights checks, and a human quality rubric |
| Local dry-run publisher | `LOCAL_VERIFIED` | Package validation, zero remote write, structured result, and duplicate guard tests | Exact future target, authorization, rights review, dry-run proof, and human final action |
| Human handoff packaging | `IMPLEMENTED` | Local handoff marker and explicit manual-action-required status | Sanitized operator checklist and separately authorized external evidence |
| Vulnerability reporting route | `NOT ESTABLISHED` | Redacted local evidence and a policy boundary only | Authenticated private channel and response policy without a guessed contact address |
| Remote provider or publisher adapter | `BLOCKED` | Future contracts only; no live service is exercised | Explicit scope change, threat-model review, credentials, privacy/terms/cost review, rights review, tests, and human approval |
| Browser automation or deployment | `BLOCKED` | No Phase 1 implementation or authorization | Separate authorization, threat model, account authority, stop/rollback plan, and observed end-to-end evidence |

## Safe sequencing

The next safe increments are local evidence improvements:

1. add a synthetic fixture or deterministic contract test;
2. update the provenance ledger and security/rights limits;
3. run the tests, validator, scanner, and Stranger Test; and
4. record unresolved decisions for human review.

Do not jump from a documented interface to a live integration. A roadmap row,
configured link, mock response, dry run, or local handoff is not proof of
availability, eligibility, approval, payment, public reach, or operator
access.
