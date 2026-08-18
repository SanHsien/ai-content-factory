# AI Content Factory

AI Content Factory turns a topic into a reviewable content packet, storyboard,
media plan, quality report, and platform-ready copy. Its default demo is fully
offline: no API key, account, GPU, private asset, or paid service is required.

> Current release: v0.1.0. The offline core is publicly available and usable;
> live providers and remote publishing remain optional or intentionally absent.

## What you get

One command creates `output/<run_id>/` with:

- fixture research, an article, a short script, and a storyboard;
- provider-neutral image, video, and voice descriptors;
- media QA, integrity-bound approval, and a duplicate-safe package manifest;
- local copy for seven common social platforms; and
- `demo_preview.html`, a self-contained visual summary you can open directly.

The demo proves orchestration and packaging, not factual research or generated
media quality. Replace fixtures with reviewed providers before publishing.

## Quickstart (Windows)

Requirements: Windows 10/11 and Python 3.11 or newer. From this directory:

```powershell
py -3 -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or newer required'; print(sys.version)"
py -3 -m venv .venv
.venv\Scripts\python -B scripts\bootstrap_offline.py
$result = .venv\Scripts\ai-content-factory demo --output output | ConvertFrom-Json
Invoke-Item $result.visible_artifact
```

No `pip install` or network access is needed for the base demo. To verify the
checkout with the same dependency-free checks used by the public release:

```powershell
.venv\Scripts\python -B scripts\public_ci.py
```

See [the detailed quickstart](docs/quickstart.md) for CMD/Linux commands,
expected output, inspection, validation, and clean removal.

## Do I need a paid API or GPU?

| Capability | Paid API | GPU | Status |
| --- | --- | --- | --- |
| Offline demo and HTML preview | No | No | Included and tested |
| Local platform package | No | No | Included; remote writes are always zero |
| User-provided image to motion render | No | No dedicated GPU required | Optional; needs HyperFrames and FFmpeg |
| Real image generation | Provider-specific | Provider-specific | Optional adapter boundary |
| Local generative video | No hosted API required | Usually yes | Optional advanced provider boundary; weights are not included |
| Remote social publishing | Provider-specific | No | Not included in v0.1 |

The optional historical image API extra is not imported by the demo and is
never an automatic fallback. Product-native tools are also optional handoff
adapters, never a requirement of the public core.

## Architecture at a glance

```text
Topic
  -> ResearchProvider
  -> TextProvider
  -> storyboard and editorial contracts
  -> ImageProvider / VideoProvider / VoiceProvider
  -> media QA
  -> integrity-bound approval
  -> local DryRunPublisher / ManualPublisher
  -> visual preview and platform-ready package
```

Core orchestration knows contracts, not vendor SDKs. Private brands provide
configuration and assets from outside the repository. Optional adapters may
add network, model, or tool requirements, but the default registry remains
fixture-only and offline. Read [ARCHITECTURE.md](ARCHITECTURE.md) and
[provider documentation](docs/providers.md) before adding an adapter.

## Useful commands

```powershell
# Show every command
.venv\Scripts\ai-content-factory --help

# Run another topic using deterministic fixtures
.venv\Scripts\ai-content-factory run `
  --topic "How can a creator plan one useful short video?" `
  --output output-custom

# Inspect or validate without changing artifacts
.venv\Scripts\ai-content-factory inspect --output output-custom
.venv\Scripts\ai-content-factory validate --output output-custom

# Run public tests only
.venv\Scripts\python -B -m unittest discover -s tests -p "test_*.py"

# Run redacted repository checks with the public denylist fingerprints
.venv\Scripts\python -B scripts\security_scan.py `
  --root . `
  --brand-hash-file scripts\public_brand_hashes.sha256
```

The `run` command can accept a generic JSON brand profile with `--brand`; that
file stays outside the public repository. It never enables a live provider or
publisher by itself.

## Safety model

- `REMOTE_WRITE=0` is enforced by the offline publishing stage.
- Approval is invalidated when an approved artifact changes.
- Re-running an identical package reuses its logical identity rather than
  creating a second publish intent.
- Network-capable adapters require explicit commands and consent flags.
- Secrets, browser profiles, model weights, caches, private paths, and private
  media are excluded by the release manifest and redacted scanner.
- Fixture claims are clearly marked and require human review.

This project does not store credentials, automate logins, or publish to social
accounts in v0.1.

## Project layout

```text
src/ai_content_factory/   core, pipeline, media, providers, publishers, CLI
fixtures/synthetic/       deterministic public-safe demo inputs
examples/demo-brand/      generic external brand-profile example
tests/                    dependency-free public test suite
scripts/                  offline bootstrap, scans, CI, RC builder
docs/                     architecture, providers, security, troubleshooting
```

## Extend it

1. Implement one of the protocols in `providers/contracts.py` or
   `publishers/base.py`.
2. Keep vendor imports inside the adapter.
3. Declare network, secret, cost, rights, and license behavior.
4. Add sanitized fixtures and failure-path tests.
5. Register the adapter explicitly; do not make it a hidden fallback.

Start with [providers](docs/providers.md), [editorial engine](docs/editorial-engine.md),
and [public/private separation](docs/public-private-separation.md).

## Documentation

- [Quickstart](docs/quickstart.md)
- [Architecture](ARCHITECTURE.md)
- [Pipeline](docs/pipeline.md)
- [Provider model](docs/providers.md)
- [Image providers](docs/image-providers.md)
- [Video providers](docs/video-providers.md)
- [Voice providers](docs/voice-providers.md)
- [Editorial engine](docs/editorial-engine.md)
- [Privacy and security](docs/privacy.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## License

Core source is licensed under Apache-2.0. External tools, provider SDKs, model
weights, fonts, and user assets retain their own licenses. They are not
relicensed or bundled by this repository; see [NOTICE](NOTICE),
[the dependency inventory](docs/dependency-inventory.md), and
[the provenance ledger](PROVENANCE_LEDGER.md).
