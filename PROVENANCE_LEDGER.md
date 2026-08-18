# Provenance ledger

This ledger is a compact, human-reviewable record of where the Phase 1
material came from. It deliberately records categories and decisions rather
than private source details.

| ID | Artifact or decision | Provenance label | Evidence and limits | Status |
| --- | --- | --- | --- | --- |
| P-001 | Secret, brand, and private-path scanner design | `CLEAN_REIMPLEMENTATION` — informed by private production experience | Implemented from generic security patterns with no private code, values, paths, identities, or brand names copied; covered by local unit tests | `VERIFIED` for local fixtures |
| P-002 | Redacted output contract | `CLEAN_REIMPLEMENTATION` — informed by private production experience | Output contains a relative file location, rule, line, generic detail, and SHA-256 fingerprint; it is not proof of complete detection | `VERIFIED` by tests |
| P-003 | Provider and publisher boundaries | `CLEAN_REIMPLEMENTATION` — informed by private production experience | Drafts describe future interfaces and human gates only; no remote service or browser state was accessed | `IMPLEMENTED`, external behavior `UNVERIFIED` |
| P-004 | Security, pipeline, and Stranger Test documents | `CLEAN_REIMPLEMENTATION` — informed by private production experience | Written as generic OSS drafts; no private operational names, source text, or deployment instructions are included | `IMPLEMENTED` |
| P-005 | Apache-2.0 distribution decision | `PROJECT_DECISION` | The canonical `LICENSE` file is present and the accepted project decision is recorded in the license ADR; this documentation task did not modify the license artifact. Future packaging still needs attribution and notice review, but the license choice is not deferred | `VERIFIED` for the local license artifact and project decision |
| P-006 | Documentation contract for status, commands, safety, and `output/<run_id>/` layout | `PROJECT_DECISION` | README and contribution docs were aligned to the observed Python 3.11/stdlib-only CLI default at repository-root `output`, `platform-ready/<platform>.txt`, publisher approval/integrity gates, and zero remote write | `VERIFIED` by local CLI, validation, and test evidence |
| P-007 | Provider/publisher contribution gates, sanitized OSS guidance, and skills roadmap | `CLEAN_REIMPLEMENTATION` — informed by private production experience | Generic review rules were written without copying private code, data, prompts, names, credentials, assets, or brands; future external behavior remains unexercised | `IMPLEMENTED`, external behavior `UNVERIFIED` |
| P-008 | OpenAI GPT Image 2 provider adapter | `REIMPLEMENTED_CLEAN` | Written in staging from the official Image Edit API and official Python SDK contract; no private provider code, credentials, responses, or account identity copied | `SAFE_FOR_FUTURE_PUBLIC`; live behavior pending isolated validation |
| P-009 | Neutral synthetic reference PNG and generator | `SYNTHETIC` | Deterministic geometric artwork generated locally using Python standard library only; no person, private pet, brand, or external asset used | `SAFE_FOR_FUTURE_PUBLIC` |
| P-010 | Sanitized recorded provider fixtures | `REIMPLEMENTED_CLEAN` | Synthetic response shapes contain no account ID, API key, signed URL, private prompt, or private media | `SAFE_FOR_FUTURE_PUBLIC` |
| P-011 | Optional OpenAI Python SDK 2.46.0 | `THIRD_PARTY_LICENSED` | Official package, Apache-2.0; optional live-only dependency; default runtime remains dependency-free | `THIRD_PARTY_LICENSED` |
| P-012 | Standard-library PNG inspection | `REIMPLEMENTED_CLEAN` | PNG signature and IHDR dimensions are validated locally; no decoder binary or third-party package is copied | `SAFE_FOR_FUTURE_PUBLIC` |
| P-013 | OpenAI provider final-qualification recheck | `OFFICIAL_DOCUMENTATION_REVIEW` | Current model, image guide, API reference, pricing, authentication, and organization-verification pages were reviewed on 2026-08-11; official guide/reference drift and organization-specific unknowns remain explicit | `REVIEW_REQUIRED`; no live availability claim |
| P-014 | Phase 2 final-qualification no-call record | `LOCAL_VERIFICATION` | Credential presence was checked as a boolean only and was absent; no value, account state, request, usage metadata, provider response, or artifact was obtained | `BLOCKED_BY_MISSING_CREDENTIAL` |
| P-015 | Phase 2R image-source and video-artifact contracts | `REIMPLEMENTED_CLEAN` | Generic local contracts written in staging; no private brand data, image, provider response, or production code copied | `SAFE_FOR_FUTURE_PUBLIC` |
| P-016 | HyperFrames motion-render adapter | `THIRD_PARTY_LICENSED` | Local adapter invokes the installed HyperFrames CLI and validates with FFprobe; HyperFrames source is not vendored and the Phase 1 Python runtime stays dependency-free | `THIRD_PARTY_LICENSED`; optional tooling |
| P-019 | Phase 3 local I2V candidate review | `docs/research/LOCAL_I2V_CANDIDATE_REVIEW_20260812.md`; official upstream repositories, model manifests, and license texts | Clean research synthesis; no upstream code, model weights, skill content, or private asset copied | `REIMPLEMENTED_CLEAN`; future public eligibility requires review of linked model terms |
| P-017 | DemoPet public motion-video fixture | `SYNTHETIC` | Uses the existing deterministic geometric pet image and generic copy; no real person, pet, brand, account, or external media | `SAFE_FOR_FUTURE_PUBLIC` |
| P-018 | Private brand integration behavior | `CLEAN_REIMPLEMENTATION` — informed by private production guidance | Public core accepts only a generic external config path; private guidance and assets are not copied into this repository | `SAFE_FOR_FUTURE_PUBLIC`; private files remain `PRIVATE_ONLY` |
| P-020 | Editorial plan, shot, asset-planning, prompt-compilation, subtitle, audio, timeline, and editorial-quality contracts | `CLEAN_REIMPLEMENTATION` — informed by private production editing experience | Generic architecture was written cleanly in staging after a read-only pattern audit; no private code, prompts, brand data, account identity, analytics, credentials, or production configuration was copied | `SAFE_FOR_FUTURE_PUBLIC`; renderer integration remains optional local tooling |
| P-021 | Voice palette, deterministic selection policy, usage history, and explicit local-command voice adapter | `CLEAN_REIMPLEMENTATION` — informed by private production voice workflows | Generic contracts and implementation were written cleanly in staging. No private voice assets, product names, engine paths, prompts, account data, credentials, or model weights are present. Human voice approval and provider licensing remain private integration gates | `SAFE_FOR_FUTURE_PUBLIC`; local synthesis is opt-in and externally configured |
| P-022 | Durable image submission receipt, bounded materialization, file-stability check, and verified image artifact | `CLEAN_REIMPLEMENTATION` — informed by private production reliability experience | Provider-neutral Python standard-library contracts were written cleanly in staging. No private source code, product identity, prompt, media, credential, output path, provider response, or account data was copied. Unit tests use only generated synthetic PNG bytes | `SAFE_FOR_FUTURE_PUBLIC`; external provider invocation remains outside the public core |
| P-023 | Offline demo HTML preview | `CLEAN_REIMPLEMENTATION` | Self-contained standard-library output written from existing synthetic fixture artifacts; no external asset, script, font, URL, private content, or copied template | `SAFE_FOR_FUTURE_PUBLIC`; visible fixture artifact only |
| P-024 | Public release manifest, builder, and public CI | `CLEAN_REIMPLEMENTATION` | Allowlist packaging, redacted scans, deterministic file hashes, and standard-library tests were written in this repository; no private release automation or history was copied | `SAFE_FOR_FUTURE_PUBLIC`; local RC packaging only |
| P-025 | v0.1 product documentation | `CLEAN_REIMPLEMENTATION` | Documentation describes verified current code and generic boundaries; private production experience informed scope but no private identity, prompt, media, account, path, or configuration was copied | `SAFE_FOR_FUTURE_PUBLIC`; optional provider claims remain bounded |

## Reading rules

- `CLEAN_REIMPLEMENTATION` means the design may have been informed by private
  production experience but was recreated from generic concepts without
  copying private artifacts.
- `PROJECT_DECISION` records an explicit project choice, not third-party legal
  advice or an external approval.
- `FIXTURE_ONLY` identifies synthetic local input and must not be presented as
  live research, current truth, or external media.
- `VERIFIED` applies only to the evidence named in the row.
- `UNVERIFIED`, `HUMAN_REVIEW`, and `BLOCKED` must not be rewritten as
  approval, live capability, public delivery, payment, or demand.

## Entry requirements

Before any future external provider, publisher, dependency, copied asset, or
external source is introduced, add a row that identifies:

1. a stable ID and artifact or decision;
2. a provenance label;
3. the exact evidence inspected;
4. what was not inspected or remains uncertain;
5. the current status; and
6. the required license, notice, security, privacy, rights, credential, cost,
   and human-authorization gates.

Do not paste private source, production exports, credentials, personal data,
real brand names, local absolute paths, or account identifiers into this
ledger. No row authorizes remote publishing, browser automation, account
access, credential handling, payment, or distribution.
