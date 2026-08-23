# ADR 0001: Core Language

- Status: accepted
- Date: 2026-08-11

## Context

Phase 1 needs one offline, provider-neutral vertical slice with a small CLI, deterministic JSON contracts, filesystem artifacts, hashing, tests, and no live provider. The private production evidence includes both Python media utilities and Node-based web/publisher code, but duplicating the core in both languages would increase packaging and maintenance cost.

## Options

### Python

- Strong standard library support for CLI, dataclasses, JSON, hashing, filesystem operations, and `unittest`.
- Direct path to future FFmpeg orchestration and media inspection.
- Accessible to content automation contributors.
- Can complete Phase 1 with zero runtime dependencies.
- Packaging requires a Python environment, but one editable local install is sufficient.

### TypeScript / Node

- Strong schema and web/provider ecosystem.
- Familiar for official API and website adapters.
- Requires a package manager dependency tree for even a small validated runtime unless the project accepts more custom code.
- Media orchestration usually still shells out to FFmpeg or another runtime.

### Mixed

- Could match the private production landscape.
- Creates two test, packaging, contributor, and contract surfaces before the core is stable.
- Violates the Phase 1 requirement to choose the smallest reasonable architecture.

## Decision

Use Python 3.11 and its standard library for the Phase 1 core, CLI, fixtures, tests, and security checks. Do not create a duplicate TypeScript core. Future adapters may use other languages only behind a versioned interoperability contract.

## Consequences

- Runtime dependencies are zero in Phase 1.
- JSON schemas are validated by explicit Python contract code rather than a third-party validation package.
- Tests use `unittest` and run offline.
- A future official provider package may justify an additional language, but that is a separate architecture decision.
