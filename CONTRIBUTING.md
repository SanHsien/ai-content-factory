# Contributing

AI Content Factory welcomes small, reviewable changes that preserve the
offline core and provider boundaries.

## Local setup

```text
python -m venv .venv
.venv/Scripts/python -B scripts/bootstrap_offline.py
.venv/Scripts/python -B scripts/public_ci.py
```

Use the platform-specific virtual-environment path on non-Windows systems.
The base runtime has no third-party dependency.

## Change rules

- Do not commit secrets, personal data, private brands, private paths, account
  identifiers, browser state, model weights, caches, or generated output.
- Keep vendor imports and network behavior inside explicit optional adapters.
- Add failure-path tests; do not weaken offline, approval, duplicate, or
  remote-write assertions.
- Update docs and `PROVENANCE_LEDGER.md` when behavior, dependencies, copied
  material, licenses, or public/private boundaries change.
- Keep dependencies small. Record source, version, license, purpose, network
  behavior, and secret requirements for every direct dependency.

## Provider and publisher contributions

State the capability, API or runtime assumptions, source/license, network and
secret behavior, cost/retry limits, rights/privacy constraints, error mapping,
and manual-review boundary. Include synthetic fixtures. Live tests must be
separate and opt-in; public CI cannot need credentials, accounts, or a GPU.

## Pull request expectations

Explain the user-visible change, files and contracts affected, tests run,
provenance, and what remains unverified. A green local test is not evidence of
live provider availability or permission to publish externally.
