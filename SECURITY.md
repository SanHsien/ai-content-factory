# Security policy

## Supported scope

The local OSS v0.1 candidate supports the offline core and dependency-free
demo. Live provider and publisher adapters are experimental, optional, or not
included. No document authorizes account access, remote publishing, browser
automation, credential setup, payment, or deployment.

## Local checks

Run from the project root:

```text
python -B -m unittest discover -s tests -p "test_*.py"
python -B scripts/security_scan.py --root . --brand-hash-file scripts/public_brand_hashes.sha256
python -B scripts/public_ci.py
```

The redacted scanner checks credential-shaped values and sensitive filenames,
private absolute paths, and configured brand fingerprints. It reports only a
repository-relative location, rule, and fingerprint. The tracked brand file
contains hashes only.

These checks reduce accidental disclosure risk; they are not a security
guarantee. Binary, encoded, novel, ignored, or external data may evade them.

## Reporting a vulnerability

There is no public repository or dedicated security address yet. Retain the
minimum redacted evidence and use an already authorized private channel to the
project owner. Do not place a secret, personal data, private media, account ID,
or exploit detail in a public issue. A future public release must establish a
private reporting route before publication.

## Secret and private-data rules

- Never commit credentials, tokens, cookies, private keys, browser profiles,
  account exports, private media, or production configuration.
- `.env.example` contains names and empty placeholders only.
- Optional adapters read explicit process-scoped configuration and must redact
  errors and logs.
- Public tests use generated synthetic values and fixture transports.
- Private brand layers remain outside the public repository.

## Release gate

The public candidate is assembled from `public_release_manifest.json`. Stop if
the allowlist check, secret/brand/path scan, provenance review, dependency
review, clean Stranger Test, ZIP extraction, or checksum comparison fails.
Never add an ignore pattern merely to obtain a clean report.

## External adapters

Before enabling an adapter, review authentication, network destinations, data
retention, training policy, rights, cost, retries, rate limits, output
integrity, dependency provenance, and operator authorization. A local fixture
or interface does not prove the external service is safe or available.
