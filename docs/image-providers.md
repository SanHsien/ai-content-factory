# Image providers

`ImageProvider` converts a prompt and generic context into a `MediaAsset` or a
verified image artifact. The offline demo uses `FixtureImageProvider`, which
returns a deterministic descriptor and never generates or downloads bytes.

## Included paths

- `FixtureImageProvider`: default, offline, deterministic, no credentials.
- `ImageSource`: validates a user-supplied local PNG/JPEG with explicit rights
  and provenance for the optional motion-render path.
- Experimental API adapter: isolated optional extra, explicit network consent,
  cost plan, and manual review; never loaded by the base demo.

Product-native image tools may be integrated as an external handoff that
materializes a verified local file. They are not assumed to exist on another
developer's machine and are not a core dependency.

## Contribution requirements

Document input rights, output license, model/provider, network behavior,
credential source, cost and retry limits, artifact hashing, error taxonomy,
and sanitized tests. Unknown rights must block live generation.
