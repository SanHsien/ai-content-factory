# Security policy

> 繁體中文：[SECURITY.md](SECURITY.md)

## Supported scope

The public v0.1.0 release supports the offline core and dependency-free
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

Use GitHub Security Advisories **Report a vulnerability**:
<https://github.com/SanHsien/ai-content-factory/security/advisories/new>.
If that entry is unavailable, contact the maintainer through their GitHub
profile. Do not open a public issue first.

Include impact, reproduction steps, affected versions, and the minimum
necessary evidence. Do not attach a real API key, cookie, account, private
media, or personally identifying brand configuration.

If the issue also exists upstream, the maintainer may forward it to the
original GitHub repository. The upstream project does not currently publish a
dedicated security mailbox; never place a secret or exploit detail in a public
issue.

## Secret and private-data rules

- Never commit credentials, tokens, cookies, private keys, browser profiles,
  account exports, private media, or production configuration.
- `.env.example` contains names and empty placeholders only.
- Optional adapters read explicit process-scoped configuration and must redact
  errors and logs.
- Public tests use generated synthetic values and fixture transports.
- Private brand layers remain outside the public repository.
- `.gitignore` covers `output/`, `private/`, `.env*`, root `config/`, and root
  `brand.json`. The public demo brand under `examples/demo-brand/` stays
  tracked. Do not force-add ignored paths.

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
