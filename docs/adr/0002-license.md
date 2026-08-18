# ADR 0002: License

- Status: accepted
- Date: 2026-08-11

## Context

The staging repository contains cleanly written Phase 1 code and synthetic fixtures. It does not import history, files, media, credentials, or unlicensed implementation from private production repositories. The intended future ecosystem includes independent provider and publisher adapters and may include corporate adopters.

## Options

### MIT

- Short and widely understood.
- Contributor friendly and broadly compatible.
- Does not include an explicit patent grant.

### Apache License 2.0

- Permissive and contributor friendly.
- Includes an explicit patent license and termination terms.
- Provides a NOTICE mechanism useful for a future adapter ecosystem and corporate adoption.
- Slightly longer and requires careful preservation of notices.

## Decision

Use Apache License 2.0 for the clean Phase 1 staging implementation. This decision applies only to files authored in this repository. It does not grant rights to any private production system, third-party media, or unreviewed implementation.

## Dependency Compatibility

Phase 1 has no runtime third-party dependency. The Python build backend is a development/build tool and must remain under dependency review. Any future direct dependency requires license and provenance review before merge.
