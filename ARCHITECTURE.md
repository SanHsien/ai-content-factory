# Architecture

AI Content Factory is a standard-library Python core surrounded by explicit
provider and publisher boundaries. The default dependency direction is inward:

```text
CLI
  -> pipeline orchestrator
      -> core contracts, hashing, approval lifecycle
      -> provider protocols
      -> media and editorial contracts
      -> local publisher protocols
```

Vendor SDKs, model runtimes, browsers, accounts, and private brand data stay
outside the core.

## v0.1 execution path

The public demo runs these persisted stages:

```text
TOPIC -> RESEARCH -> TEXT -> STORYBOARD -> MEDIA
      -> MEDIA_QA -> APPROVAL -> PUBLISH_PACKAGE
```

Every stage has deterministic inputs, artifacts, status, and structured
failure state. A run can be inspected, validated, paused, and resumed. The
package stage requires a valid approval hash and emits only local files.

## Boundaries

| Boundary | Core owns | Adapter or private layer owns |
| --- | --- | --- |
| Research | result contract and evidence status | retrieval, citations, network policy |
| Image | request/result shape and artifact integrity | model/API, cost, rights, credentials |
| Video | request/result shape, provenance, QA handoff | model runtime, weights, GPU, toolchain |
| Voice | profile/artifact contract and selection policy | engine, voice license, model files |
| Publisher | approval and duplicate guard | destination API and operator authorization |
| Brand | generic profile schema | identity, prompts, assets, account configuration |

## Offline and optional paths

The base registry contains deterministic fixture providers only. It has no
runtime third-party dependencies and blocks network access in tests. Optional
adapters are lazily imported by explicit commands. Missing optional tools must
fail with an actionable message and cannot silently activate another provider.

## Public/private separation

The public repository contains generic contracts, fixtures, tests, and docs.
A private layer may reference the installed package and supply configuration or
assets at runtime. It must not be copied into the public tree. The release
candidate is assembled by `scripts/build_release_candidate.py` from
`public_release_manifest.json`, not by copying the working repository.

## Deliberate v0.1 limits

v0.1 does not include live research, autonomous remote publishing, analytics
collection, account automation, bundled model weights, or production brand
logic. These can be independent adapters without changing core contracts.
