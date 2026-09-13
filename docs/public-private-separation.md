# Public and private separation

## Public core

The release candidate may contain contracts, orchestrator code, deterministic
fixtures, generic examples, tests, documentation, and optional adapter code
whose provenance and license are recorded.

## Private layer

A private layer may contain brand identity, source media, prompts, account
configuration, analytics, publication state, voice selection, credentials,
and production schedules. It lives outside the public repository and is
referenced only through explicit runtime configuration.

## Enforcement

- The base demo never looks for a private directory.
- Tests block private absolute paths and hidden provider fallback.
- The release builder copies an allowlist, never the whole working tree.
- Redacted scans check secrets, private paths, and owner-supplied brand hashes.
- The RC excludes Git history, output, caches, model weights, live tests, and
  internal evidence.

A generic schema does not make private data public. Only synthetic or
explicitly licensed examples belong in fixtures.
