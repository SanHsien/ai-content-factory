# Security model

## Purpose

The v0.1 security model protects an offline release candidate before an
authorized human considers publication. Optional adapters add explicitly
selected OpenAI GPT Image 2 Image Edit boundary, but does not change the
offline default. The model is intentionally small: it catches common
accidental disclosures and makes the remaining uncertainty visible.

## Security properties and Phase 2 boundary

The repository aims to provide:

- no live API or remote publisher path in the default local workflow; the only
  Phase 2 live path is an explicit OpenAI image-edit opt-in;
- no credential persistence, private asset requirement, or real brand data in
  the sanitized tree;
- deterministic local artifacts with structured status and failure records;
- redacted secret, owner-configured hashed-brand, and private-path findings;
- explicit input-rights responsibility and provider data-control limits before
  a reference image leaves the local boundary;
- explicit provenance and human-review boundaries; and
- a local-only dry-run/manual handoff that fails closed when remote writes are
  requested.

These are design and local-test targets. They are not a guarantee about a
future dependency, untracked data, operator environment, or external service.

## Trust boundaries

| Boundary | Data crossing it | Control | Evidence limit |
| --- | --- | --- | --- |
| Local working tree → scanner | Text files and filenames | Secret and private-path rules; relative locations only | Pattern coverage is incomplete; unreadable and excluded data is a limit |
| Owner-held brand knowledge → scanner | SHA-256 fingerprints only | External hash file, command argument, or environment variable | A missing fingerprint list is not proof of absence |
| Synthetic fixture → provider contract | Generic local JSON | Fixture-only flag, structured results, deterministic serialization | Synthetic output is not current or externally sourced evidence |
| Draft artifact → human reviewer | Local package and manifest | Stranger Test, validation, provenance ledger, and redacted findings | Human review is still required |
| Phase 2 reference → OpenAI Image Edit API | Approved synthetic/local reference and prompt, only after explicit opt-in | `--allow-network`, `--confirm-live-call`, reviewed `LIVE_CALL_PLAN.md`, process-scoped key, and non-`UNKNOWN` input rights status | No account, quota, retention configuration, or commercial clearance is verified here |
| OpenAI response → local artifact | Base64 image response and safe response metadata | Immediate local materialization, PNG structure check, SHA-256, provenance record, and `MANUAL_REVIEW_REQUIRED` | Local QA is not semantic safety, rights clearance, approval, or publication proof |
| Live publisher → outside world | A publish request | No live publisher; local dry-run/manual handoff only; `remote_write = 0` | No remote publication exists |

## Controls

1. Scan before packaging. Stop on a finding instead of masking it with an
   ignore rule.
2. Hash matched values in output. Never echo secret, brand, or private-path
   text.
3. Keep brand fingerprints outside tracked files. Normalize before hashing so
   an owner can configure case and spacing behavior without disclosing the
   source token.
4. Keep provider and publisher contracts offline and fixture-backed until a
   separate authorization and security review exists.
5. Validate generated artifacts for required files, safe relative names,
   canonical JSON, deterministic platform text, and zero remote write.
6. Label provenance, evidence status, rights/licensing uncertainty, and
   human-only gates in documentation.
7. Keep the selected live provider behind all three explicit gates:
   `--allow-network`, `--confirm-live-call`, and a reviewed
   `LIVE_CALL_PLAN.md`; require the process-scoped `OPENAI_API_KEY` without
   persisting or logging its value.
8. Require an explicit `OWNED`, `LICENSED`, or `SYNTHETIC` reference status and
   ownership/consent statement. Reject `UNKNOWN`; do not infer commercial
   rights from API access or output ownership language.
9. Record OpenAI's official data-control facts without claiming that this
   project's organization has enabled them: `/v1/images/edits` is documented
   as not used for training by default, with 30-day abuse-monitoring retention,
   no application-state retention, and ZDR eligibility subject to limits. See
   the [official data-controls guide](https://developers.openai.com/api/docs/guides/your-data).
10. Treat network access, browser automation, credentials, account state,
    payment, private assets, and real identities as separate threat surfaces.

## Review sequence

```text
inventory → local tests → demo/validate → redacted scan
          → provider terms/data controls → rights review → Stranger Test
          → explicit live plan → human decision → manual artifact review
```

The sequence is evidence collection. The explicit live plan is still not a
publisher authorization. It permits at most the selected experimental image
edit within its reviewed cost/input bound; it does not authorize an unplanned
upload, account operation, second provider, retry, or publication.

## Residual risks

- Pattern scanners can miss encoded, split, compressed, or novel secrets.
- A SHA-256 fingerprint configuration is only as complete as the owner's
  private input.
- A local clean result does not inspect remote logs, browser state, or files
  excluded by an explicit pattern.
- A local fixture can contain a plausible claim without proving that the claim
  is current, correct, rights-cleared, or safe for a public audience.
- Future dependencies or adapters may add network behavior and require a new
  review even if the current tree remains clean.
- OpenAI's [Services Agreement](https://openai.com/policies/services-agreement/)
  assigns input/output responsibilities subject to applicable law, but does
  not establish that a particular reference image is licensed or that an
  output is commercially exclusive.
- The [official OpenAI data-controls guide](https://developers.openai.com/api/docs/guides/your-data)
  records endpoint-level retention and ZDR eligibility, but the actual
  organization/project setting remains an operator-owned, unverified state.
- Provider pricing is dynamic and token-based. A local cost cap is a safety
  control, not a billing proof or quote.
- The future vulnerability-reporting route and external operator eligibility
  are not established.

These residual risks are why a local scan is a review gate and not a release
approval.
