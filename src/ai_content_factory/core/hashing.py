"""Deterministic hashing helpers used by the core contracts.

Only Python's standard library is used.  Canonical JSON is UTF-8 encoded,
uses lexicographically sorted object keys, and omits insignificant whitespace.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from enum import Enum
from typing import Any, Mapping


def _to_canonical_value(value: Any) -> Any:
    """Convert supported values to the JSON data model.

    ``json.dumps`` accepts a few values that are not part of a strict JSON
    contract (for example integer mapping keys).  Rejecting those values here
    prevents two callers from accidentally hashing different representations of
    the same logical object.
    """

    if isinstance(value, Enum):
        return _to_canonical_value(value.value)

    if value is None or isinstance(value, (str, bool, int)):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite floats are not valid canonical JSON")
        return value

    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON object keys must be strings")
            result[key] = _to_canonical_value(item)
        return result

    if isinstance(value, (list, tuple)):
        return [_to_canonical_value(item) for item in value]

    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        if hasattr(value, "to_canonical_dict"):
            return _to_canonical_value(value.to_canonical_dict())
        return _to_canonical_value(dataclasses.asdict(value))

    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonicalize(value: Any) -> Any:
    """Return a recursively normalized JSON-compatible value."""

    return _to_canonical_value(value)


def canonical_json(value: Any) -> str:
    """Serialize ``value`` deterministically as compact UTF-8-ready JSON."""

    normalized = _to_canonical_value(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Return the UTF-8 bytes used as the canonical JSON hash input."""

    return canonical_json(value).encode("utf-8")


def canonical_json_hash(value: Any) -> str:
    """Return the lower-case SHA-256 digest of canonical JSON."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


hash_canonical_json = canonical_json_hash


def _payload_bytes(value: Any) -> bytes:
    """Convert artifact payloads to bytes without filesystem or network I/O."""

    # Avoid importing Artifact here; accepting the shape keeps this helper
    # useful without introducing a module cycle.
    if hasattr(value, "artifact_id") and hasattr(value, "content"):
        value = value.content

    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, str):
        return value.encode("utf-8")
    if value is None:
        raise TypeError("artifact content cannot be None")

    # Structured payloads are hashed as the same canonical JSON bytes used by
    # packet manifests.  This is deterministic and still stdlib-only.
    return canonical_json_bytes(value)


def sha256_hex(value: bytes | bytearray | memoryview | str) -> str:
    """Return a lower-case SHA-256 digest for raw bytes or UTF-8 text."""

    if isinstance(value, str):
        raw = value.encode("utf-8")
    elif isinstance(value, bytes):
        raw = value
    elif isinstance(value, bytearray):
        raw = bytes(value)
    elif isinstance(value, memoryview):
        raw = value.tobytes()
    else:
        raise TypeError("sha256_hex expects bytes-like data or text")
    return hashlib.sha256(raw).hexdigest()


def artifact_sha256(value: Any) -> str:
    """Return the SHA-256 digest for an artifact payload or Artifact object."""

    return hashlib.sha256(_payload_bytes(value)).hexdigest()


__all__ = [
    "artifact_sha256",
    "canonical_json",
    "canonical_json_bytes",
    "canonical_json_hash",
    "canonicalize",
    "hash_canonical_json",
    "sha256_hex",
]
