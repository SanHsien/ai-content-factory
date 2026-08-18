"""Build and verify approved, immutable offline content packets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from ai_content_factory.core import ApprovalState, Artifact, ContentPacket


FIXTURE_CREATED_AT = "2000-01-01T00:00:00Z"
PACKET_SCHEMA_VERSION = "1.0"

MIME_TYPES = {
    ".json": "application/json",
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


def _read_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _artifact(root: Path, filename: str) -> Artifact:
    path = root / filename
    data = path.read_bytes()
    media_type = MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return Artifact.from_bytes(
        filename,
        data,
        media_type=media_type,
        name=filename,
        metadata={
            "artifact_type": "pipeline-output",
            "created_at": FIXTURE_CREATED_AT,
            "generated_by": "offline-fixture-pipeline",
            "path_or_reference": filename,
            "provenance": "synthetic-fixture",
        },
    )


def build_approved_packet(
    root: Path,
    *,
    packet_id: str,
    topic: str,
    platform_copy: Mapping[str, str],
    artifact_filenames: Sequence[str],
) -> tuple[ContentPacket, dict[str, Any]]:
    """Create a fixture-approved packet scoped only to local package generation."""

    research = _read_json(root / "research.json")
    storyboard = _read_json(root / "storyboard.json")
    media = _read_json(root / "media_manifest.json")
    qa = _read_json(root / "qa_scorecard.json")
    content = {
        "article": (root / "article.md").read_text(encoding="utf-8"),
        "created_at": FIXTURE_CREATED_AT,
        "locale": "en",
        "media_artifacts": media.get("assets", []),
        "platform_copy": {key: str(platform_copy[key]) for key in sorted(platform_copy)},
        "provenance": {
            "eligibility": "REIMPLEMENTED_CLEAN",
            "mode": "synthetic-fixture",
            "network_required": False,
        },
        "qa": qa,
        "research": research,
        "short_script": (root / "short_script.md").read_text(encoding="utf-8"),
        "storyboard": storyboard,
        "topic": topic,
    }
    packet = ContentPacket(
        packet_id=packet_id,
        version=1,
        schema_version=PACKET_SCHEMA_VERSION,
        content=content,
        artifacts=[_artifact(root, filename) for filename in artifact_filenames],
        metadata={
            "approval_scope": "offline-dry-run-and-manual-package-only",
            "brand": "DemoPet",
            "fixture_only": True,
            "remote_write": 0,
        },
    )
    packet.mark_qa_pending().mark_qa_passed().approve()
    if not packet.approval_is_valid:
        raise ValueError("approved content packet failed integrity validation")

    document = packet.to_dict()
    document.update(content)
    document["packet_sha256"] = packet.packet_hash()
    document["artifacts"] = [
        {
            **artifact.manifest_dict(),
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.metadata["artifact_type"],
            "created_at": artifact.metadata["created_at"],
            "generated_by": artifact.metadata["generated_by"],
            "mime_type": artifact.media_type,
            "path_or_reference": artifact.metadata["path_or_reference"],
            "provenance": artifact.metadata["provenance"],
        }
        for artifact in packet.artifacts
    ]
    return packet, document


def validate_approved_packet(
    root: Path,
    document: Mapping[str, Any] | None = None,
) -> tuple[bool, tuple[str, ...], ContentPacket | None]:
    """Rehydrate local artifact bytes and reject stale or mutated approvals."""

    errors: list[str] = []
    try:
        doc = document or _read_json(root / "content_packet.json")
        raw_artifacts = doc.get("artifacts", [])
        if not isinstance(raw_artifacts, list) or not raw_artifacts:
            return False, ("ARTIFACT_MANIFEST_MISSING",), None
        artifacts: list[Artifact] = []
        for item in raw_artifacts:
            if not isinstance(item, Mapping):
                errors.append("ARTIFACT_MANIFEST_INVALID")
                continue
            reference = str(item.get("path_or_reference", ""))
            candidate = Path(reference)
            if not reference or candidate.is_absolute() or ".." in candidate.parts or len(candidate.parts) != 1:
                errors.append("ARTIFACT_REFERENCE_UNSAFE")
                continue
            path = root / candidate
            if not path.is_file():
                errors.append(f"ARTIFACT_MISSING:{candidate.name}")
                continue
            artifacts.append(
                Artifact(
                    artifact_id=item.get("artifact_id", item.get("id")),
                    content=path.read_bytes(),
                    sha256=item.get("sha256"),
                    media_type=str(item.get("mime_type", item.get("media_type", "application/octet-stream"))),
                    metadata=item.get("metadata", {}),
                    name=item.get("name"),
                )
            )
        packet = ContentPacket(
            packet_id=doc.get("packet_id"),
            version=doc.get("version", 1),
            schema_version=str(doc.get("schema_version", "")),
            content=doc.get("content", {}),
            artifacts=artifacts,
            approval_state=doc.get("approval_state", ApprovalState.DRAFT.value),
            metadata=doc.get("metadata", {}),
            integrity_snapshot=doc.get("integrity_snapshot"),
        )
        content = doc.get("content", {})
        if not isinstance(content, Mapping):
            errors.append("PACKET_CONTENT_INVALID")
        else:
            for key in (
                "topic",
                "locale",
                "research",
                "article",
                "short_script",
                "storyboard",
                "media_artifacts",
                "platform_copy",
                "qa",
                "provenance",
                "created_at",
            ):
                if doc.get(key) != content.get(key):
                    errors.append(f"PACKET_CONTENT_ALIAS_MISMATCH:{key}")
        if packet.approval_state is not ApprovalState.APPROVED:
            errors.append("PACKET_NOT_APPROVED")
        if doc.get("packet_sha256") != packet.packet_hash():
            errors.append("PACKET_HASH_MISMATCH")
        integrity = packet.validate_integrity()
        errors.extend(error.code for error in integrity.errors)
        return not errors and packet.approval_is_valid, tuple(dict.fromkeys(errors)), packet
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False, ("PACKET_INTEGRITY_VALIDATION_FAILED",), None


__all__ = [
    "FIXTURE_CREATED_AT",
    "PACKET_SCHEMA_VERSION",
    "build_approved_packet",
    "validate_approved_packet",
]
