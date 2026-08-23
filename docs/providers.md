# Provider model

Providers are replaceable implementations of stable public contracts. The
orchestrator depends on protocols and structured results; it does not import a
vendor SDK or discover credentials.

## Public contracts

| Protocol | Input | Output |
| --- | --- | --- |
| `ResearchProvider` | topic and generic brand context | findings with evidence status |
| `TextProvider` | topic and research | article/script/platform text |
| `ImageProvider` | prompt and generic context | media descriptor or verified artifact |
| `VideoProvider` | prompt and generic context | media descriptor or verified artifact |
| `VoiceProvider` | narration text and generic context | media descriptor or voice artifact |

The default `FixtureProviders` registry is deterministic, offline, and requires
no secret. It proves orchestration and contracts only; fixture content is not
live research or generated media.

## Optional adapter rules

An optional provider must:

1. use a stable provider ID and stay behind the matching protocol;
2. declare imports, network behavior, authentication, cost, retry, rate limit,
   input rights, output terms, retention, and model/runtime requirements;
3. fail clearly when unavailable and never activate as a hidden fallback;
4. produce local hashes and provenance before QA;
5. use sanitized recorded fixtures for public tests; and
6. require manual review before publishing external output.

Network-capable adapters must be selected explicitly. The normal `demo`,
`run`, `inspect`, `validate`, and public test paths never load them. See the
separate image, video, and voice provider documents for their current status.

## Private brand use

Brand-specific prompts, assets, voice identities, accounts, and model paths
are supplied by an external private layer. A provider may receive a generic
profile object, but it may not search the repository or machine for private
state.
