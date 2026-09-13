# ADR 0005: ChatGPT image handoff to local motion render

## Status

Accepted for Phase 2R on 2026-08-11.

## Context

The first Phase 2 experiment treated a paid image API as the candidate real
media boundary. That experiment remains useful historical evidence, but it is
not the intended default product workflow. The useful near-term workflow is a
human-approved hero image created in ChatGPT or Codex, imported as a local
artifact, and rendered into a vertical MP4 without a provider credential or a
billable generation call.

The core must also be honest about two different capabilities:

- `MOTION_RENDER` creates a real video by moving, cropping, layering, and
  compositing a still image and text on a deterministic timeline.
- `GENERATIVE_I2V` would synthesize new subject motion and is not implemented
  in Phase 2R.

## Decision

Add provider-neutral image-source and video-artifact contracts. The default
working source is `ChatGPTHandoffImageSource`; deterministic tests use
`SyntheticImageSource`. `CodexNativeImageSource` is present as a truthful
capability boundary and is classified `PARTIAL` until a product image can be
reliably materialized into a caller-selected local path in a repeatable run.

Implement `MotionRenderVideoProvider` as an optional local adapter around the
pinned HyperFrames 0.7.106 CLI. It is invoked only by the explicit `render-video`
command. Python's standard-library-only Phase 1 path remains unchanged. The
adapter renders locally, then validates the MP4 with FFprobe and records
checksums and provenance. No network, API key, account, browser profile, or
remote publisher is part of the render request.

Keep the previous OpenAI image provider isolated and optional. It is no longer
a Phase gate, a setup prerequisite, or the first workflow shown to users.

## Public and private boundary

The public repository contains generic contracts, the DemoPet synthetic image,
the renderer, tests, and documentation. A brand layer is supplied through an
external `--brand-config` path. Private assets and brand configuration stay
outside this repository and are never copied into public fixtures or evidence.

## Consequences

- The default hero-image-to-video flow requires no API key or API billing.
- A normal HyperFrames tool installation may require network access during
  setup, but the actual render path makes no provider or application network
  call.
- HyperFrames, Chrome Headless Shell, FFmpeg, and FFprobe are optional media
  tooling, not Python runtime dependencies of the Phase 1 core.
- Human review remains required before an imported image or rendered video can
  cross a publishing boundary.
- Phase 2R does not claim true generative image-to-video support.
