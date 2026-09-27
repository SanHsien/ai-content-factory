# Direct Dependency Inventory

| Name | Version | Source | License | Purpose | Status |
|---|---|---|---|---|---|
| Python | 3.11 or newer | Python Software Foundation | PSF License | runtime and standard library | SAFE |
| setuptools | environment-provided compatible release | Python Packaging Authority | MIT | local editable build backend only; no runtime import | SAFE |
| openai | 2.46.0, optional `openai-image` extra | OpenAI official PyPI/GitHub distribution | Apache-2.0 | live GPT Image 2 transport only; lazily imported and excluded from offline demo/tests | SAFE for experimental opt-in use; version and endpoint must be re-reviewed before promotion |
| HyperFrames CLI | 0.7.106, optional local tool | official npm package and heygen-com/hyperframes repository | Apache-2.0 | deterministic HTML composition lint, inspect, snapshot, and local MP4 render | SAFE as optional Phase 2R tooling; not vendored or imported by the Phase 1 runtime |
| FFmpeg / FFprobe | system installation; verified 8.1.2 local build | FFmpeg project through a Windows package manager build | GPLv3 build configuration | local encode, decode, stream inspection, and frame extraction | SAFE as an external executable for local tooling; not distributed by this repository |
| Chrome Headless Shell | HyperFrames-managed local browser build | Chrome for Testing distribution retrieved by HyperFrames | third-party browser binary; not distributed here | deterministic local frame capture | REVIEW_REQUIRED for redistribution; acceptable as external optional tooling only |

Default runtime third-party dependencies: none. The OpenAI SDK is an optional
historical live-provider extra and is not installed, imported, or required by
the offline or Phase 2R image-handoff paths. HyperFrames, Chrome Headless
Shell, and FFmpeg are optional external render tools invoked only by the
explicit video command.

No dependency may be added without recording its exact version range, source, license, purpose, network behavior, and review status. A dependency is `BLOCKING` when its license or provenance is unknown or incompatible.
