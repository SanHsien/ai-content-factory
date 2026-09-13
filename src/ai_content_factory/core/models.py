"""Versioned content, artifact, approval, and integrity contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Iterable, Mapping

from .errors import (
    ApprovalError,
    SchemaValidationError,
    ValidationError,
    ValidationResult,
)
from .hashing import artifact_sha256, canonical_json, canonical_json_hash


_UNSET = object()
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_APPROVAL_STATES = frozenset(
    {
        "DRAFT",
        "QA_PENDING",
        "QA_PASSED",
        "APPROVED",
        "REJECTED",
        "APPROVAL_INVALIDATED",
    }
)


def _error(
    code: str,
    path: str,
    message: str,
    **details: Any,
) -> ValidationError:
    return ValidationError(code, path, message, details)


def _append_unique(
    errors: list[ValidationError], new_errors: Iterable[ValidationError]
) -> None:
    seen = {(error.code, error.path, error.message) for error in errors}
    for error in new_errors:
        key = (error.code, error.path, error.message)
        if key not in seen:
            errors.append(error)
            seen.add(key)


def _is_valid_version(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value >= 1
    return isinstance(value, str) and bool(value.strip())


class ApprovalState(str, Enum):
    """Lifecycle state for QA and approval of a content packet."""

    DRAFT = "DRAFT"
    QA_PENDING = "QA_PENDING"
    QA_PASSED = "QA_PASSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPROVAL_INVALIDATED = "APPROVAL_INVALIDATED"

    @classmethod
    def from_value(cls, value: "ApprovalState | str") -> "ApprovalState":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            try:
                return cls(normalized)
            except ValueError as exc:
                raise ValueError(f"Unknown approval state: {value!r}") from exc
        raise TypeError("approval state must be an ApprovalState or string")


@dataclass(slots=True, init=False)
class Artifact:
    """An in-memory artifact with a declared and computed SHA-256 digest.

    ``content`` accepts bytes-like values, text, or a JSON-compatible value.
    Bytes are hashed as-is, text is UTF-8 encoded, and structured values use
    canonical JSON.  No filesystem access is performed by this contract.
    """

    artifact_id: str | None
    content: Any
    sha256: str | None
    media_type: str
    metadata: dict[str, Any]
    name: str | None

    def __init__(
        self,
        artifact_id: str | None = None,
        content: Any = _UNSET,
        sha256: str | None | object = _UNSET,
        media_type: str = "application/octet-stream",
        metadata: Mapping[str, Any] | None = None,
        name: str | None = None,
        *,
        id: str | None = None,
        data: Any = _UNSET,
        payload: Any = _UNSET,
        declared_sha256: str | None | object = _UNSET,
    ) -> None:
        if artifact_id is not None and id is not None and artifact_id != id:
            raise TypeError("artifact_id and id refer to different values")
        resolved_id = artifact_id if artifact_id is not None else id
        if resolved_id is None and name is not None:
            resolved_id = name

        supplied_content = [
            value
            for value in (content, data, payload)
            if value is not _UNSET
        ]
        if len(supplied_content) > 1:
            raise TypeError("use only one of content, data, or payload")
        resolved_content = supplied_content[0] if supplied_content else None

        if sha256 is not _UNSET and declared_sha256 is not _UNSET:
            if sha256 != declared_sha256:
                raise TypeError("sha256 and declared_sha256 differ")
        resolved_sha256 = (
            sha256
            if sha256 is not _UNSET
            else declared_sha256
            if declared_sha256 is not _UNSET
            else _UNSET
        )
        if resolved_sha256 is _UNSET:
            if resolved_content is None:
                resolved_sha256 = None
            else:
                try:
                    resolved_sha256 = artifact_sha256(resolved_content)
                except (TypeError, ValueError):
                    # Schema validation reports unsupported content in a
                    # structured way; construction remains possible so a
                    # caller can inspect or repair the malformed object.
                    resolved_sha256 = None

        self.artifact_id = resolved_id
        self.content = resolved_content
        self.sha256 = resolved_sha256  # type: ignore[assignment]
        self.media_type = media_type
        self.metadata = (
            dict(metadata)
            if isinstance(metadata, Mapping)
            else {}
            if metadata is None
            else metadata
        )  # type: ignore[assignment]
        self.name = name

    @classmethod
    def from_bytes(
        cls,
        artifact_id: str,
        data: bytes | bytearray | memoryview,
        *,
        media_type: str = "application/octet-stream",
        metadata: Mapping[str, Any] | None = None,
        name: str | None = None,
    ) -> "Artifact":
        return cls(
            artifact_id=artifact_id,
            content=bytes(data),
            sha256=artifact_sha256(data),
            media_type=media_type,
            metadata=metadata,
            name=name,
        )

    @classmethod
    def from_text(
        cls,
        artifact_id: str,
        text: str,
        *,
        media_type: str = "text/plain; charset=utf-8",
        metadata: Mapping[str, Any] | None = None,
        name: str | None = None,
    ) -> "Artifact":
        return cls(
            artifact_id=artifact_id,
            content=text,
            sha256=artifact_sha256(text),
            media_type=media_type,
            metadata=metadata,
            name=name,
        )

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        content: Any = _UNSET,
    ) -> "Artifact":
        """Build an artifact from a manifest or an in-memory artifact dict."""

        if not isinstance(value, Mapping):
            raise TypeError("artifact value must be a mapping")
        raw_content = content
        if raw_content is _UNSET:
            raw_content = value.get("content", value.get("data", None))
        raw_hash = value.get("sha256", value.get("declared_sha256", _UNSET))
        return cls(
            artifact_id=value.get("artifact_id", value.get("id")),
            content=raw_content,
            sha256=raw_hash,
            media_type=value.get("media_type", "application/octet-stream"),
            metadata=value.get("metadata", {}),
            name=value.get("name"),
        )

    @property
    def id(self) -> str | None:
        return self.artifact_id

    @id.setter
    def id(self, value: str | None) -> None:
        self.artifact_id = value

    @property
    def data(self) -> Any:
        return self.content

    @data.setter
    def data(self, value: Any) -> None:
        self.content = value

    @property
    def payload(self) -> Any:
        return self.content

    @payload.setter
    def payload(self, value: Any) -> None:
        self.content = value

    @property
    def declared_sha256(self) -> str | None:
        return self.sha256

    @declared_sha256.setter
    def declared_sha256(self, value: str | None) -> None:
        self.sha256 = value

    @property
    def computed_sha256(self) -> str:
        return artifact_sha256(self.content)

    def compute_sha256(self) -> str:
        return self.computed_sha256

    @property
    def hash(self) -> str | None:
        """Alias for the declared digest; ``sha256`` remains canonical."""

        return self.sha256

    def manifest_dict(self) -> dict[str, Any]:
        """Return the JSON manifest covered by a packet hash.

        Raw artifact bytes are deliberately not included; the separate
        ``IntegritySnapshot.artifact_hashes`` map covers their content.
        """

        return {
            "id": self.artifact_id,
            "media_type": self.media_type,
            "name": self.name,
            "metadata": dict(self.metadata) if isinstance(self.metadata, Mapping) else self.metadata,
            "sha256": self.sha256,
        }

    to_canonical_dict = manifest_dict

    def to_dict(self, *, include_content: bool = False) -> dict[str, Any]:
        result = self.manifest_dict()
        if include_content:
            result["content"] = self.content
        return result

    def validate_schema(self, path: str = "artifact") -> ValidationResult:
        errors: list[ValidationError] = []

        if not isinstance(self.artifact_id, str) or not self.artifact_id.strip():
            errors.append(
                _error(
                    "ARTIFACT_ID_INVALID",
                    f"{path}.id",
                    "artifact id must be a non-empty string",
                )
            )

        if self.content is None:
            errors.append(
                _error(
                    "ARTIFACT_CONTENT_MISSING",
                    f"{path}.content",
                    "artifact content is required",
                )
            )
        else:
            try:
                artifact_sha256(self.content)
            except (TypeError, ValueError) as exc:
                errors.append(
                    _error(
                        "ARTIFACT_CONTENT_INVALID",
                        f"{path}.content",
                        f"artifact content cannot be hashed: {exc}",
                    )
                )

        if not isinstance(self.media_type, str) or not self.media_type.strip():
            errors.append(
                _error(
                    "ARTIFACT_MEDIA_TYPE_INVALID",
                    f"{path}.media_type",
                    "media_type must be a non-empty string",
                )
            )

        if self.name is not None and (
            not isinstance(self.name, str) or not self.name.strip()
        ):
            errors.append(
                _error(
                    "ARTIFACT_NAME_INVALID",
                    f"{path}.name",
                    "name must be null or a non-empty string",
                )
            )

        if not isinstance(self.metadata, Mapping):
            errors.append(
                _error(
                    "ARTIFACT_METADATA_INVALID",
                    f"{path}.metadata",
                    "metadata must be a JSON object",
                )
            )
        else:
            try:
                canonical_json(self.metadata)
            except (TypeError, ValueError) as exc:
                errors.append(
                    _error(
                        "ARTIFACT_METADATA_INVALID",
                        f"{path}.metadata",
                        f"metadata is not canonical JSON: {exc}",
                    )
                )

        if self.sha256 is None:
            errors.append(
                _error(
                    "ARTIFACT_SHA256_MISSING",
                    f"{path}.sha256",
                    "artifact sha256 is required",
                )
            )
        elif not isinstance(self.sha256, str) or not _SHA256_RE.fullmatch(self.sha256):
            errors.append(
                _error(
                    "ARTIFACT_SHA256_MALFORMED",
                    f"{path}.sha256",
                    "artifact sha256 must be 64 lower-case hexadecimal characters",
                )
            )
        elif self.content is not None:
            try:
                computed = self.computed_sha256
            except (TypeError, ValueError):
                computed = None
            if computed is not None and computed != self.sha256:
                errors.append(
                    _error(
                        "ARTIFACT_SHA256_MISMATCH",
                        f"{path}.sha256",
                        "declared sha256 does not match artifact content",
                        expected=computed,
                        actual=self.sha256,
                    )
                )

        return ValidationResult(tuple(errors))


@dataclass(frozen=True, slots=True)
class IntegritySnapshot:
    """Immutable packet and artifact digests captured at a known state."""

    packet_hash: str
    artifact_hashes: Mapping[str, str]
    schema_version: str = "1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_hashes", dict(self.artifact_hashes))

    @property
    def packet_sha256(self) -> str:
        return self.packet_hash

    @property
    def artifact_sha256(self) -> Mapping[str, str]:
        return self.artifact_hashes

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_hashes": dict(self.artifact_hashes),
            "packet_hash": self.packet_hash,
            "schema_version": self.schema_version,
        }

    to_canonical_dict = to_dict

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "IntegritySnapshot":
        packet_hash = value.get("packet_hash", value.get("packet_sha256"))
        artifact_hashes = value.get("artifact_hashes", {})
        return cls(
            packet_hash=packet_hash,
            artifact_hashes=artifact_hashes,
            schema_version=value.get("schema_version", "1"),
        )

    def validate_schema(self, path: str = "integrity_snapshot") -> ValidationResult:
        errors: list[ValidationError] = []
        if not isinstance(self.schema_version, str) or not self.schema_version.strip():
            errors.append(
                _error(
                    "INTEGRITY_SNAPSHOT_SCHEMA_VERSION_INVALID",
                    f"{path}.schema_version",
                    "snapshot schema_version must be a non-empty string",
                )
            )
        if not isinstance(self.packet_hash, str) or not _SHA256_RE.fullmatch(
            self.packet_hash
        ):
            errors.append(
                _error(
                    "INTEGRITY_PACKET_HASH_MALFORMED",
                    f"{path}.packet_hash",
                    "snapshot packet_hash must be 64 lower-case hexadecimal characters",
                )
            )
        if not isinstance(self.artifact_hashes, Mapping):
            errors.append(
                _error(
                    "INTEGRITY_ARTIFACT_HASHES_INVALID",
                    f"{path}.artifact_hashes",
                    "snapshot artifact_hashes must be an object",
                )
            )
        else:
            for artifact_id, digest in self.artifact_hashes.items():
                item_path = f"{path}.artifact_hashes[{artifact_id!r}]"
                if not isinstance(artifact_id, str) or not artifact_id.strip():
                    errors.append(
                        _error(
                            "INTEGRITY_ARTIFACT_ID_INVALID",
                            item_path,
                            "snapshot artifact ids must be non-empty strings",
                        )
                    )
                if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
                    errors.append(
                        _error(
                            "INTEGRITY_ARTIFACT_HASH_MALFORMED",
                            item_path,
                            "snapshot artifact hashes must be 64 lower-case hexadecimal characters",
                        )
                    )
        return ValidationResult(tuple(errors))


IntegrityValidationResult = ValidationResult


@dataclass(slots=True, init=False)
class ContentPacket:
    """Versioned JSON content plus artifacts and approval lifecycle state."""

    packet_id: str | None
    version: int | str | None
    content: Any
    artifacts: list[Artifact]
    approval_state: ApprovalState
    schema_version: str
    metadata: dict[str, Any]
    integrity_snapshot: IntegritySnapshot | None

    def __init__(
        self,
        packet_id: str | None = None,
        version: int | str | None | object = _UNSET,
        content: Any = _UNSET,
        artifacts: Iterable[Artifact] | Artifact | None = None,
        approval_state: ApprovalState | str = ApprovalState.DRAFT,
        schema_version: str = "1",
        metadata: Mapping[str, Any] | None = None,
        integrity_snapshot: IntegritySnapshot | Mapping[str, Any] | None | object = _UNSET,
        *,
        id: str | None = None,
        payload: Any = _UNSET,
        state: ApprovalState | str | object = _UNSET,
        approval: ApprovalState | str | object = _UNSET,
        integrity: IntegritySnapshot | Mapping[str, Any] | None | object = _UNSET,
        content_version: int | str | object = _UNSET,
        packet_version: int | str | object = _UNSET,
    ) -> None:
        if packet_id is not None and id is not None and packet_id != id:
            raise TypeError("packet_id and id refer to different values")
        self.packet_id = packet_id if packet_id is not None else id

        supplied_versions = [
            value
            for value in (version, content_version, packet_version)
            if value is not _UNSET
        ]
        if len({repr(value) for value in supplied_versions}) > 1:
            raise TypeError("version, content_version, and packet_version differ")
        self.version = supplied_versions[0] if supplied_versions else 1  # type: ignore[assignment]

        if content is not _UNSET and payload is not _UNSET:
            raise TypeError("use only one of content or payload")
        self.content = content if content is not _UNSET else payload if payload is not _UNSET else {}

        if isinstance(artifacts, Artifact):
            self.artifacts = [artifacts]
        else:
            self.artifacts = list(artifacts) if artifacts is not None else []

        if state is not _UNSET and approval is not _UNSET and state != approval:
            raise TypeError("state and approval refer to different values")
        resolved_state = state if state is not _UNSET else approval if approval is not _UNSET else approval_state
        self.approval_state = ApprovalState.from_value(resolved_state)  # type: ignore[arg-type]
        self.schema_version = schema_version
        self.metadata = (
            dict(metadata)
            if isinstance(metadata, Mapping)
            else {}
            if metadata is None
            else metadata
        )  # type: ignore[assignment]

        if integrity_snapshot is not _UNSET and integrity is not _UNSET:
            if integrity_snapshot != integrity:
                raise TypeError("integrity_snapshot and integrity refer to different values")
        resolved_snapshot = (
            integrity_snapshot
            if integrity_snapshot is not _UNSET
            else integrity
            if integrity is not _UNSET
            else None
        )
        if isinstance(resolved_snapshot, Mapping):
            try:
                resolved_snapshot = IntegritySnapshot.from_dict(resolved_snapshot)
            except (TypeError, ValueError):
                # Preserve malformed input for structured validation rather
                # than hiding it behind a constructor exception.
                pass
        self.integrity_snapshot = resolved_snapshot  # type: ignore[assignment]

    @property
    def id(self) -> str | None:
        return self.packet_id

    @id.setter
    def id(self, value: str | None) -> None:
        self.packet_id = value

    @property
    def payload(self) -> Any:
        return self.content

    @payload.setter
    def payload(self, value: Any) -> None:
        self.set_content(value)

    @property
    def state(self) -> ApprovalState:
        return self.approval_state

    @state.setter
    def state(self, value: ApprovalState | str) -> None:
        self.set_approval_state(value)

    @property
    def approval(self) -> ApprovalState:
        return self.approval_state

    @approval.setter
    def approval(self, value: ApprovalState | str) -> None:
        self.set_approval_state(value)

    @property
    def integrity(self) -> IntegritySnapshot | None:
        return self.integrity_snapshot

    @integrity.setter
    def integrity(self, value: IntegritySnapshot | Mapping[str, Any] | None) -> None:
        if isinstance(value, Mapping):
            value = IntegritySnapshot.from_dict(value)
        self.integrity_snapshot = value

    def to_canonical_dict(self) -> dict[str, Any]:
        """Return the lifecycle-independent packet manifest to be hashed."""

        manifests = [artifact.manifest_dict() for artifact in self.artifacts]
        manifests.sort(key=lambda item: (str(item.get("id")), canonical_json(item)))
        return {
            "artifacts": manifests,
            "content": self.content,
            "metadata": self.metadata,
            "packet_id": self.packet_id,
            "schema_version": self.schema_version,
            "version": self.version,
        }

    canonical_manifest = to_canonical_dict

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def packet_hash(self) -> str:
        return canonical_json_hash(self.to_canonical_dict())

    def to_dict(self, *, include_artifact_content: bool = False) -> dict[str, Any]:
        """Return a JSON-oriented packet representation.

        Artifact payloads are excluded by default because bytes are not JSON
        values and a manifest should not duplicate potentially large content.
        Pass ``include_artifact_content=True`` when the caller explicitly wants
        an in-memory round-trip for JSON/text payloads.
        """

        return {
            "approval_state": self.approval_state.value,
            "artifacts": [
                artifact.to_dict(include_content=include_artifact_content)
                if isinstance(artifact, Artifact)
                else artifact
                for artifact in self.artifacts
            ],
            "content": self.content,
            "integrity_snapshot": (
                self.integrity_snapshot.to_dict()
                if isinstance(self.integrity_snapshot, IntegritySnapshot)
                else self.integrity_snapshot
            ),
            "metadata": self.metadata,
            "packet_id": self.packet_id,
            "schema_version": self.schema_version,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ContentPacket":
        """Build a packet from the public ``to_dict`` representation."""

        if not isinstance(value, Mapping):
            raise TypeError("content packet value must be a mapping")
        raw_artifacts = value.get("artifacts", [])
        if not isinstance(raw_artifacts, (list, tuple)):
            raw_artifacts = []
        artifacts = [
            Artifact.from_dict(item) if isinstance(item, Mapping) else item
            for item in raw_artifacts
        ]
        raw_snapshot = value.get(
            "integrity_snapshot",
            value.get("integrity"),
        )
        return cls(
            packet_id=value.get("packet_id", value.get("id")),
            version=value.get(
                "version",
                value.get("content_version", value.get("packet_version", 1)),
            ),
            content=value.get("content", value.get("payload", {})),
            artifacts=artifacts,
            approval_state=value.get(
                "approval_state",
                value.get("state", ApprovalState.DRAFT.value),
            ),
            schema_version=value.get("schema_version", "1"),
            metadata=value.get("metadata", {}),
            integrity_snapshot=raw_snapshot,
        )

    @property
    def content_hash(self) -> str:
        return self.packet_hash()

    @property
    def packet_sha256(self) -> str:
        return self.packet_hash()

    def validate_schema(
        self,
        *,
        require_integrity_snapshot: bool = True,
    ) -> ValidationResult:
        errors: list[ValidationError] = []

        if not isinstance(self.packet_id, str) or not self.packet_id.strip():
            errors.append(
                _error(
                    "PACKET_ID_INVALID",
                    "packet_id",
                    "packet_id must be a non-empty string",
                )
            )

        if not _is_valid_version(self.version):
            errors.append(
                _error(
                    "PACKET_VERSION_INVALID",
                    "version",
                    "version must be a positive integer or non-empty string",
                )
            )

        if not isinstance(self.schema_version, str) or not self.schema_version.strip():
            errors.append(
                _error(
                    "PACKET_SCHEMA_VERSION_INVALID",
                    "schema_version",
                    "schema_version must be a non-empty string",
                )
            )

        try:
            canonical_json(self.content)
        except (TypeError, ValueError) as exc:
            errors.append(
                _error(
                    "PACKET_CONTENT_INVALID",
                    "content",
                    f"content must be canonical JSON: {exc}",
                )
            )

        if not isinstance(self.metadata, Mapping):
            errors.append(
                _error(
                    "PACKET_METADATA_INVALID",
                    "metadata",
                    "metadata must be a JSON object",
                )
            )
        else:
            try:
                canonical_json(self.metadata)
            except (TypeError, ValueError) as exc:
                errors.append(
                    _error(
                        "PACKET_METADATA_INVALID",
                        "metadata",
                        f"metadata must be canonical JSON: {exc}",
                    )
                )

        if not isinstance(self.approval_state, ApprovalState):
            errors.append(
                _error(
                    "PACKET_APPROVAL_STATE_INVALID",
                    "approval_state",
                    "approval_state must be an ApprovalState",
                )
            )

        if not isinstance(self.artifacts, (list, tuple)):
            errors.append(
                _error(
                    "PACKET_ARTIFACTS_INVALID",
                    "artifacts",
                    "artifacts must be a list of Artifact objects",
                )
            )
        else:
            seen_ids: set[str] = set()
            for index, artifact in enumerate(self.artifacts):
                path = f"artifacts[{index}]"
                if not isinstance(artifact, Artifact):
                    errors.append(
                        _error(
                            "PACKET_ARTIFACT_INVALID",
                            path,
                            "artifact must be an Artifact instance",
                        )
                    )
                    continue
                _append_unique(errors, artifact.validate_schema(path))
                if isinstance(artifact.artifact_id, str):
                    if artifact.artifact_id in seen_ids:
                        errors.append(
                            _error(
                                "PACKET_ARTIFACT_ID_DUPLICATE",
                                f"{path}.id",
                                "artifact ids must be unique within a packet",
                                artifact_id=artifact.artifact_id,
                            )
                        )
                    seen_ids.add(artifact.artifact_id)

        if self.integrity_snapshot is not None:
            if not isinstance(self.integrity_snapshot, IntegritySnapshot):
                errors.append(
                    _error(
                        "INTEGRITY_SNAPSHOT_INVALID",
                        "integrity_snapshot",
                        "integrity_snapshot must be an IntegritySnapshot",
                    )
                )
            else:
                _append_unique(errors, self.integrity_snapshot.validate_schema())
        elif require_integrity_snapshot and self.approval_state in {
            ApprovalState.QA_PASSED,
            ApprovalState.APPROVED,
        }:
            errors.append(
                _error(
                    "INTEGRITY_SNAPSHOT_MISSING",
                    "integrity_snapshot",
                    "QA-passed or approved packets require an integrity snapshot",
                )
            )

        result = ValidationResult(tuple(errors))
        if not result.valid:
            self._invalidate_if_approved()
        return result

    def capture_integrity_snapshot(self) -> IntegritySnapshot:
        """Capture and attach the current packet/artifact digests."""

        schema_result = self.validate_schema(require_integrity_snapshot=False)
        if not schema_result.valid:
            raise SchemaValidationError(
                schema_result.errors,
                message="Cannot capture integrity for an invalid packet",
            )

        snapshot = IntegritySnapshot(
            packet_hash=self.packet_hash(),
            artifact_hashes={
                artifact.artifact_id: artifact.computed_sha256
                for artifact in self.artifacts
            },
            schema_version=self.schema_version,
        )
        self.integrity_snapshot = snapshot
        return snapshot

    create_integrity_snapshot = capture_integrity_snapshot
    snapshot_integrity = capture_integrity_snapshot

    def _coerce_snapshot(
        self,
        snapshot: IntegritySnapshot | Mapping[str, Any] | None,
    ) -> IntegritySnapshot | None:
        candidate = self.integrity_snapshot if snapshot is None else snapshot
        if isinstance(candidate, Mapping):
            try:
                candidate = IntegritySnapshot.from_dict(candidate)
            except (TypeError, ValueError):
                return None
        return candidate if isinstance(candidate, IntegritySnapshot) else None

    def validate_integrity(
        self,
        snapshot: IntegritySnapshot | Mapping[str, Any] | None = None,
    ) -> ValidationResult:
        """Validate packet and artifact digests against a captured snapshot.

        A failed validation automatically moves a QA-passed or approved packet
        to ``APPROVAL_INVALIDATED``.  This also catches direct list/dict/object
        mutation that cannot be intercepted by Python properties.
        """

        errors: list[ValidationError] = []
        schema_result = self.validate_schema(require_integrity_snapshot=False)
        _append_unique(errors, schema_result.errors)

        resolved_snapshot = self._coerce_snapshot(snapshot)
        if resolved_snapshot is None:
            errors.append(
                _error(
                    "INTEGRITY_SNAPSHOT_MISSING",
                    "integrity_snapshot",
                    "a valid integrity snapshot is required for integrity validation",
                )
            )
            result = ValidationResult(tuple(errors))
            self._invalidate_if_approved()
            return result

        _append_unique(errors, resolved_snapshot.validate_schema().errors)
        snapshot_schema = resolved_snapshot.validate_schema()

        if snapshot_schema.valid:
            try:
                current_packet_hash = self.packet_hash()
            except (TypeError, ValueError) as exc:
                current_packet_hash = None
                errors.append(
                    _error(
                        "INTEGRITY_PACKET_HASH_UNAVAILABLE",
                        "packet",
                        f"current packet cannot be hashed: {exc}",
                    )
                )
            if current_packet_hash is not None and current_packet_hash != resolved_snapshot.packet_hash:
                errors.append(
                    _error(
                        "INTEGRITY_PACKET_MUTATED",
                        "packet",
                        "packet content or manifest differs from the captured snapshot",
                        expected=resolved_snapshot.packet_hash,
                        actual=current_packet_hash,
                    )
                )

            if isinstance(self.artifacts, (list, tuple)):
                current_by_id: dict[str, Artifact] = {}
                for index, artifact in enumerate(self.artifacts):
                    if not isinstance(artifact, Artifact):
                        continue
                    if not isinstance(artifact.artifact_id, str):
                        continue
                    if artifact.artifact_id in current_by_id:
                        errors.append(
                            _error(
                                "INTEGRITY_ARTIFACT_REPLACED",
                                f"artifacts[{index}]",
                                "duplicate artifact id makes the packet ambiguous",
                                artifact_id=artifact.artifact_id,
                            )
                        )
                    current_by_id[artifact.artifact_id] = artifact

                expected_ids = set(resolved_snapshot.artifact_hashes)
                current_ids = set(current_by_id)
                for artifact_id in sorted(expected_ids - current_ids):
                    errors.append(
                        _error(
                            "INTEGRITY_ARTIFACT_MISSING",
                            f"artifacts[{artifact_id!r}]",
                            "artifact present in the snapshot is missing",
                            artifact_id=artifact_id,
                        )
                    )
                for artifact_id in sorted(current_ids - expected_ids):
                    errors.append(
                        _error(
                            "INTEGRITY_ARTIFACT_ADDED",
                            f"artifacts[{artifact_id!r}]",
                            "artifact was added after the snapshot",
                            artifact_id=artifact_id,
                        )
                    )

                for artifact_id, artifact in current_by_id.items():
                    path = f"artifacts[{artifact_id!r}]"
                    if not isinstance(artifact.sha256, str) or not _SHA256_RE.fullmatch(
                        artifact.sha256
                    ):
                        errors.append(
                            _error(
                                "INTEGRITY_ARTIFACT_HASH_MALFORMED",
                                f"{path}.sha256",
                                "artifact sha256 is missing or malformed",
                            )
                        )
                    try:
                        current_artifact_hash = artifact.computed_sha256
                    except (TypeError, ValueError) as exc:
                        current_artifact_hash = None
                        errors.append(
                            _error(
                                "INTEGRITY_ARTIFACT_HASH_UNAVAILABLE",
                                f"{path}.content",
                                f"artifact cannot be hashed: {exc}",
                            )
                        )

                    if (
                        current_artifact_hash is not None
                        and isinstance(artifact.sha256, str)
                        and _SHA256_RE.fullmatch(artifact.sha256)
                        and current_artifact_hash != artifact.sha256
                    ):
                        errors.append(
                            _error(
                                "INTEGRITY_ARTIFACT_HASH_MISMATCH",
                                f"{path}.sha256",
                                "declared sha256 does not match current artifact content",
                                expected=current_artifact_hash,
                                actual=artifact.sha256,
                            )
                        )

                    if artifact_id in resolved_snapshot.artifact_hashes:
                        expected_hash = resolved_snapshot.artifact_hashes[artifact_id]
                        if (
                            current_artifact_hash is not None
                            and current_artifact_hash != expected_hash
                        ):
                            errors.append(
                                _error(
                                    "INTEGRITY_ARTIFACT_REPLACED",
                                    f"{path}.content",
                                    "artifact content differs from the captured snapshot",
                                    expected=expected_hash,
                                    actual=current_artifact_hash,
                                )
                            )

        result = ValidationResult(tuple(errors))
        if not result.valid:
            self._invalidate_if_approved()
        return result

    validate_packet_integrity = validate_integrity

    def validate(self) -> ValidationResult:
        """Run schema validation and integrity validation when applicable."""

        errors: list[ValidationError] = []
        schema_result = self.validate_schema()
        _append_unique(errors, schema_result.errors)

        should_check_integrity = (
            self.integrity_snapshot is not None
            or self.approval_state
            in {
                ApprovalState.QA_PASSED,
                ApprovalState.APPROVED,
                ApprovalState.APPROVAL_INVALIDATED,
            }
        )
        if should_check_integrity:
            integrity_result = self.validate_integrity()
            _append_unique(errors, integrity_result.errors)

        result = ValidationResult(tuple(errors))
        if not result.valid:
            self._invalidate_if_approved()
        return result

    validate_all = validate

    def _invalidate_if_approved(self) -> None:
        if self.approval_state in {
            ApprovalState.QA_PASSED,
            ApprovalState.APPROVED,
        }:
            self.approval_state = ApprovalState.APPROVAL_INVALIDATED

    def invalidate_approval(self) -> "ContentPacket":
        self.approval_state = ApprovalState.APPROVAL_INVALIDATED
        return self

    def set_content(self, content: Any) -> "ContentPacket":
        self.content = content
        self._invalidate_if_approved()
        return self

    def add_artifact(self, artifact: Artifact) -> "ContentPacket":
        self.artifacts.append(artifact)
        self._invalidate_if_approved()
        return self

    def remove_artifact(self, artifact_id: str) -> Artifact:
        for index, artifact in enumerate(self.artifacts):
            if isinstance(artifact, Artifact) and artifact.artifact_id == artifact_id:
                removed = self.artifacts.pop(index)
                self._invalidate_if_approved()
                return removed
        raise KeyError(artifact_id)

    def replace_artifact(self, artifact: Artifact) -> "ContentPacket":
        if not isinstance(artifact, Artifact):
            raise TypeError("replace_artifact expects an Artifact")
        for index, current in enumerate(self.artifacts):
            if isinstance(current, Artifact) and current.artifact_id == artifact.artifact_id:
                self.artifacts[index] = artifact
                self._invalidate_if_approved()
                return self
        raise KeyError(artifact.artifact_id)

    def set_approval_state(self, state: ApprovalState | str) -> "ContentPacket":
        self.approval_state = ApprovalState.from_value(state)
        return self

    def transition_to(self, state: ApprovalState | str) -> "ContentPacket":
        target = ApprovalState.from_value(state)
        current = self.approval_state
        allowed: dict[ApprovalState, set[ApprovalState]] = {
            ApprovalState.DRAFT: {ApprovalState.QA_PENDING, ApprovalState.REJECTED},
            ApprovalState.QA_PENDING: {
                ApprovalState.DRAFT,
                ApprovalState.QA_PASSED,
                ApprovalState.REJECTED,
            },
            ApprovalState.QA_PASSED: {
                ApprovalState.APPROVED,
                ApprovalState.DRAFT,
                ApprovalState.REJECTED,
                ApprovalState.APPROVAL_INVALIDATED,
            },
            ApprovalState.APPROVED: {ApprovalState.APPROVAL_INVALIDATED},
            ApprovalState.REJECTED: {ApprovalState.DRAFT, ApprovalState.QA_PENDING},
            ApprovalState.APPROVAL_INVALIDATED: {
                ApprovalState.DRAFT,
                ApprovalState.QA_PENDING,
            },
        }
        if target not in allowed.get(current, set()):
            raise ApprovalError(
                f"invalid approval transition {current.value} -> {target.value}"
            )

        if target is ApprovalState.QA_PASSED:
            schema_result = self.validate_schema(require_integrity_snapshot=False)
            if not schema_result.valid:
                raise ApprovalError(
                    "cannot mark an invalid packet QA_PASSED",
                    errors=schema_result.errors,
                )
            if self.integrity_snapshot is None:
                self.capture_integrity_snapshot()

        if target is ApprovalState.APPROVED:
            return self.approve()

        self.approval_state = target
        return self

    def mark_qa_pending(self) -> "ContentPacket":
        return self.transition_to(ApprovalState.QA_PENDING)

    def mark_qa_passed(self) -> "ContentPacket":
        return self.transition_to(ApprovalState.QA_PASSED)

    def reject(self) -> "ContentPacket":
        return self.transition_to(ApprovalState.REJECTED)

    def approve(self) -> "ContentPacket":
        if self.approval_state is not ApprovalState.QA_PASSED:
            raise ApprovalError("only QA_PASSED packets can be approved")
        schema_result = self.validate_schema(require_integrity_snapshot=False)
        if not schema_result.valid:
            raise ApprovalError(
                "cannot approve an invalid packet",
                errors=schema_result.errors,
            )
        if self.integrity_snapshot is None:
            self.capture_integrity_snapshot()
        integrity_result = self.validate_integrity()
        if not integrity_result.valid:
            raise ApprovalError(
                "cannot approve a packet with failed integrity validation",
                errors=integrity_result.errors,
            )
        self.approval_state = ApprovalState.APPROVED
        return self

    @property
    def approval_is_valid(self) -> bool:
        if self.approval_state is not ApprovalState.APPROVED:
            return False
        return self.validate_integrity().valid


def validate_artifact_schema(artifact: Artifact) -> ValidationResult:
    if not isinstance(artifact, Artifact):
        return ValidationResult(
            (
                _error(
                    "ARTIFACT_INVALID",
                    "artifact",
                    "value must be an Artifact instance",
                ),
            )
        )
    return artifact.validate_schema()


def validate_content_packet_schema(packet: ContentPacket) -> ValidationResult:
    if not isinstance(packet, ContentPacket):
        return ValidationResult(
            (
                _error(
                    "PACKET_INVALID",
                    "packet",
                    "value must be a ContentPacket instance",
                ),
            )
        )
    return packet.validate_schema()


validate_packet_schema = validate_content_packet_schema


__all__ = [
    "ApprovalState",
    "Artifact",
    "ContentPacket",
    "IntegritySnapshot",
    "IntegrityValidationResult",
    "validate_artifact_schema",
    "validate_content_packet_schema",
    "validate_packet_schema",
]
