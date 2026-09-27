# Core contracts

This document defines the v0.1 offline core boundary. The implementation is
Python 3.11 standard-library-only code under
`src/ai_content_factory/core/`; it performs no network, filesystem, secret, or
external-service work.

## ContentPacket

`ContentPacket` is the versioned unit that moves through QA and approval.

Required concepts:

| Field | Contract |
| --- | --- |
| `packet_id` | Non-empty string. `id` is a convenience alias. |
| `version` | Positive integer or non-empty string. |
| `schema_version` | Non-empty string identifying the packet contract version. |
| `content` | JSON-compatible value. `payload` is a convenience alias. |
| `metadata` | JSON object; defaults to `{}`. |
| `artifacts` | List of `Artifact` objects with unique IDs. |
| `approval_state` | One of the six `ApprovalState` values. |
| `integrity_snapshot` | Optional until QA passes; required for `QA_PASSED` and `APPROVED`. |

The packet manifest used for hashing contains `packet_id`, `version`,
`schema_version`, `content`, `metadata`, and sorted artifact manifests. It does
not contain approval state or the integrity snapshot itself. Consequently,
changing lifecycle state does not mutate the content hash, while changing
content, metadata, version, or an artifact declaration does.

Typical construction and approval:

```python
from ai_content_factory.core import Artifact, ContentPacket

packet = ContentPacket(
    packet_id="packet-1",
    version=1,
    content={"title": "Example"},
    artifacts=[Artifact.from_text("script", "hello")],
)
packet.mark_qa_pending()
packet.mark_qa_passed()  # captures an integrity snapshot
packet.approve()
```

`approve()` only succeeds from `QA_PASSED`, after schema and integrity
validation pass. Direct field assignment remains possible for data loading or
migration, but callers should use the lifecycle methods when enforcing
transitions.

## Artifact and SHA-256

`Artifact` stores an in-memory payload and its declared `sha256` digest. The
payload may be bytes-like data, UTF-8 text, or a JSON-compatible value. Bytes
are hashed as-is; text is UTF-8 encoded; structured values are serialized using
the canonical JSON rules below. `Artifact.from_bytes()` and
`Artifact.from_text()` calculate the digest at construction time.

The declared digest must be exactly 64 lower-case hexadecimal characters and
must equal `artifact.computed_sha256`. A missing, malformed, or mismatching
digest is a schema error. The core contract does not read a path or fetch
artifact content; replacement of content is detected when the in-memory value
is validated against the snapshot.

## Canonical deterministic JSON

`canonical_json(value)` uses these rules:

- object keys must be strings and are sorted lexicographically;
- arrays preserve their order;
- insignificant whitespace is omitted (`separators=(",", ":")`);
- non-ASCII text is emitted as UTF-8 without ASCII escaping;
- non-finite floats are rejected;
- the resulting string is encoded as UTF-8 before hashing.

`canonical_json_hash(value)` returns the lower-case SHA-256 hex digest of those
bytes. `artifact_sha256(value)` applies the artifact payload rules and returns
the same lower-case digest format.

## IntegritySnapshot and validation

`ContentPacket.capture_integrity_snapshot()` creates an
`IntegritySnapshot` containing:

- `packet_hash`: the canonical hash of the packet manifest;
- `artifact_hashes`: a map from artifact ID to the computed payload SHA-256;
- `schema_version`: copied from the packet.

`packet.validate_integrity()` compares current state against that snapshot and
returns a `ValidationResult`. It detects:

- packet content or manifest mutation (`INTEGRITY_PACKET_MUTATED`);
- missing snapshot entries (`INTEGRITY_ARTIFACT_MISSING`);
- added entries (`INTEGRITY_ARTIFACT_ADDED`);
- same-ID content replacement (`INTEGRITY_ARTIFACT_REPLACED`);
- malformed or missing artifact hashes (`INTEGRITY_ARTIFACT_HASH_MALFORMED`);
- declared-vs-content hash mismatch (`INTEGRITY_ARTIFACT_HASH_MISMATCH`);
- malformed snapshot digests (`INTEGRITY_PACKET_HASH_MALFORMED` and related
  snapshot errors).

If an integrity or schema validation failure is observed while the packet is
`QA_PASSED` or `APPROVED`, the packet is automatically moved to
`APPROVAL_INVALIDATED`. Explicit mutation helpers (`set_content`,
`add_artifact`, `remove_artifact`, and `replace_artifact`) invalidate approval
immediately. Direct nested mutation, such as `packet.content["title"] = ...`,
is detected at the next `validate_integrity()` or `validate()` call.

An invalidated packet is never silently restored to an approved state. It must
be returned to the workflow (`DRAFT` or `QA_PENDING`), pass QA again, and
receive a new snapshot before approval.

## Schema validation and structured errors

`validate_schema()` returns a `ValidationResult` with:

```python
{
    "valid": False,
    "errors": [
        {
            "code": "ARTIFACT_SHA256_MALFORMED",
            "path": "artifacts[0].sha256",
            "message": "...",
        }
    ],
}
```

Each `ValidationError` always has stable `code`, `path`, and `message` fields;
optional machine-readable `details` are included when relevant. The result is
also iterable over its errors and exposes `valid`, `is_valid`, and `ok` aliases.
Call `result.raise_for_errors()` when fail-fast behavior is preferred; it
raises `SchemaValidationError` and retains the structured error tuple.

The public import surface is available from `ai_content_factory.core`, or from
the focused `contracts`, `hashing`, `integrity`, and `schema` modules inside
the core package.
