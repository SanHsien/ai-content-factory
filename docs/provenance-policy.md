# Provenance policy

## Rule

Every non-trivial design, implementation, copied dependency, fixture, media
descriptor, external input, or documentation decision must have a provenance
status that a stranger can understand. The ledger should reveal enough lineage
to review the decision without revealing private production information.

Provenance is an evidence record, not a copyright opinion, security
certification, provider approval, or release authorization.

## Labels

Use the smallest accurate label:

- `CLEAN_REIMPLEMENTATION`: private production experience informed the problem
  framing or risk controls, but the repository content was recreated from
  generic concepts and no private code, data, prompt, name, identity,
  credential, path, asset, or brand was copied.
- `PROJECT_DECISION`: an explicit repository choice, not third-party legal
  advice or external approval.
- `FIXTURE_ONLY`: synthetic local input or output used to exercise a contract;
  never present it as live research, current truth, or external media.
- `THIRD_PARTY_SOURCE`: copied or imported material whose exact source,
  version, license, notice, and retained surface are recorded.

The full clean-reimplementation disclosure used in this phase is:

> clean reimplementation informed by private production experience

Do not use a vague "inspired by" phrase when a clean-reimplementation label
is the accurate description.

## Required ledger fields

Each entry should identify:

- a stable ID;
- the artifact or decision;
- a provenance label;
- the evidence actually inspected;
- what was not inspected or remains uncertain;
- the current status: `IMPLEMENTED`, `VERIFIED`, `UNVERIFIED`,
  `HUMAN_REVIEW`, or `BLOCKED`; and
- any required license, notice, privacy, security, rights, credential, cost,
  or human-authorization gate.

For provider and publisher changes, also record the capability boundary,
fixture/test evidence, side-effect behavior, and whether the implementation is
local-only or future external work.

## Entry example

Use a generic entry shape such as:

```text
ID: P-NNN
Artifact or decision: local fixture contract
Label: FIXTURE_ONLY
Evidence: deterministic unittest and redacted scan
Limit: no live source, external media, rights decision, or account evidence
Status: VERIFIED for the named local checks
```

The example is a template, not a ledger entry and not evidence by itself.

## Prohibited shortcuts

Do not paste private source, production exports, credentials, personal data,
real brand names, local absolute paths, private assets, account identifiers,
or unreviewed external text into a provenance entry. Do not turn a private
source into an unqualified public attribution. Do not call a fixture a live
result or call a draft license decision a completed public release.

## Review gate

Before any future external provider, publisher, dependency, copied asset, or
external source is introduced, add a ledger row and perform a notice, license,
security, privacy, and rights review. Record the exact evidence and the
remaining uncertainty. Phase 1 remains offline and does not authorize that
future introduction.
