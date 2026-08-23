# Changelog

## Unreleased — SanHsien Windows-first fork (2026-08-22)

- Forked from the public `ai-content-factory` project at `d476f740af9c9a0b7f1c2d05c6e658a09ee9abb0`.
- Added a Traditional Chinese public entry (`README.md`) and kept the upstream English README as `README.en.md`.
- Added Windows-first maintenance files: `FORK.md`, `AGENTS.md`, `CLAUDE.md`, `NOTICE.md`, `docs/DEVELOPMENT.md`, `docs/UPSTREAM.md`, `docs/DECISIONS.md`.
- Added `tools/bootstrap_dev.ps1` and `tools/dev_check.ps1` around the upstream dependency-free `scripts/public_ci.py`.
- Added scheduled upstream review, CodeQL, Dependabot, and Windows canonical gate workflows.
- Fork-local review fixes (not contributed upstream): OpenAI-shaped secret scan, required `render-video --no-network`, English fork README section, gitignore for root `config/` and `brand.json`, aligned security reporting, issue template points at `docs/UPSTREAM.md`.
- Windows canonical gate now runs Python 3.14. This fork is not the upstream v0.1.0 RC source.
- Maintainer workflow is direct push to `origin/main`; no feature branches.

## 0.1.0-rc.1 - 2026-08-15

- Added a deterministic self-contained HTML preview to the offline demo.
- Added an allowlist-only public release builder and reproducible public scans.
- Reframed the README and docs around a stranger-usable OSS product.
- Documented image, video, voice, editorial, privacy, and public/private boundaries.
- Added public CI and clean-release regression tests without runtime dependencies.

## Unreleased - Phase 2R

- Added provider-neutral local image-source, hero-image, video-request, and
  video-artifact boundaries.
- Added an explicit HyperFrames motion-render path for real vertical MP4s while
  preserving the Phase 1 offline core.
- Reframed the earlier paid image API work as optional historical evidence,
  not a default prerequisite or phase gate.
- Added a generic external private-brand configuration boundary and a neutral
  public DemoPet video workflow.

All entries below describe local, pre-public work. They are not release,
publication, approval, security certification, or production-suitability
claims.

## Unreleased — Phase 2 experimental real-image boundary

### Added

- One optional OpenAI GPT Image 2 image-edit adapter behind explicit network
  and billable-call consent flags.
- Provider-neutral reference rights, cost policy, request identity, local
  dedupe registry, structured errors, provenance, PNG QA, and mandatory human
  review packaging.
- A deterministic neutral reference image and sanitized response-shape
  fixtures for offline contract tests.

### Boundaries

- The Phase 1 offline demo remains the default and does not import the
  optional SDK, require credentials, or make network calls.
- Real output is never approved or published automatically.
- A recorded fixture or fake transport is test evidence only and is not proof
  of a successful live provider call.

### Current verification limit

- The live real-media vertical slice remains unverified until one explicitly
  authorized, cost-bounded request produces a local artifact with complete
  provider provenance and human-review packaging.

## Unreleased — Phase 1 documentation integration

### Added

- A first-screen README contract covering WHAT, WHY, DEMO, SAFETY,
  ARCHITECTURE, STATUS, and the exact current-stage label.
- A canonical Python 3.11 standard-library-only local command loop using the
  `output/<run_id>/` staging layout.
- Provider and publisher contribution gates that separate fixture/local
  evidence from future external adapter work.
- A reproducible Stranger Test procedure with explicit `PASS`, `HOLD`, and
  `FAIL` evidence rules.
- Expanded provenance, redaction, security, conduct, notice, and skills
  roadmap guidance for sanitized OSS review.
- Confirmation that the canonical `LICENSE` file is present and Apache-2.0 is
  the final Phase 1 project license choice.

### Boundaries

- Offline staging and local pre-public review only.
- No live API, remote provider, remote publisher, browser automation, account
  onboarding, credential setup, payment, deployment, or distribution behavior.
- No real secret values, private paths, private assets, personal data, real
  identities, or real brand names are intentionally recorded by this task.
- Provenance is labeled as a clean reimplementation when private production
  experience informed the design but no private artifact was copied.

### Verified locally by this task

- Documentation commands and status language were reviewed against the local
  CLI, pipeline, fixture, publisher, and test contracts.
- The final documentation tree is checked for redacted secret patterns and
  private-path patterns using the repository scanner.

### Not yet verified

- Any future provider adapter, publisher adapter, remote reporting route,
  external deployment, account capability, or public delivery behavior.
