"""Local publisher contracts and the phase-one duplicate guard."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from ai_content_factory.pipeline.models import FailureState, canonical_json
from ai_content_factory.providers.fixtures import PLATFORMS


def remote_write_enabled() -> bool:
    """Return whether the environment attempts to opt into remote writes."""

    return os.environ.get("REMOTE_WRITE", "0") != "0"


@dataclass(frozen=True)
class PublishResult:
    status: str
    mode: str
    remote_write: int
    package_id: str | None = None
    platform_files: Mapping[str, str] = field(default_factory=dict)
    manifest_file: str | None = None
    failure: FailureState | None = None
    manual_action_required: bool = False

    @property
    def succeeded(self) -> bool:
        return self.failure is None and self.status not in {
            "DUPLICATE_PACKAGE",
            "FAILED",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure": self.failure.to_dict() if self.failure else None,
            "manual_action_required": self.manual_action_required,
            "manifest_file": self.manifest_file,
            "mode": self.mode,
            "package_id": self.package_id,
            "platform_files": {
                str(key): self.platform_files[key]
                for key in sorted(self.platform_files)
            },
            "remote_write": self.remote_write,
            "status": self.status,
        }


class Publisher(Protocol):
    mode: str

    def publish(
        self,
        package: Mapping[str, Any],
        *,
        output_dir: str | Path | None = None,
    ) -> PublishResult:
        ...


class DuplicateGuard:
    """Prevent a local handoff marker from being written twice."""

    @staticmethod
    def existing_marker_failure(
        marker: Path,
        package_id: str,
    ) -> FailureState | None:
        if not marker.is_file():
            return None
        try:
            with marker.open("r", encoding="utf-8") as handle:
                existing = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return FailureState(
                code="DUPLICATE_OUTPUT",
                message="A publisher marker already exists and is unreadable.",
                stage="PUBLISH_PACKAGE",
                details={"marker": marker.name},
            )
        existing_id = existing.get("package_id") if isinstance(existing, Mapping) else None
        return FailureState(
            code="DUPLICATE_PACKAGE" if existing_id == package_id else "DUPLICATE_OUTPUT",
            message="A publisher marker already exists for this output.",
            stage="PUBLISH_PACKAGE",
            details={"marker": marker.name, "package_id": package_id},
        )


def package_parts(package: Mapping[str, Any]) -> tuple[str | None, dict[str, str], FailureState | None]:
    """Validate the package surface shared by both local publisher modes."""

    package_id = package.get("package_id")
    raw_files = package.get("platform_files", {})
    raw_platforms = package.get("platforms", {})
    planned_actions = package.get("planned_actions", {})
    if not isinstance(package_id, str) or not package_id:
        return None, {}, FailureState(
            code="PACKAGE_ID_MISSING",
            message="Publish package has no deterministic package id.",
            stage="PUBLISH_PACKAGE",
        )
    if package.get("remote_write") != 0 or remote_write_enabled():
        return None, {}, FailureState(
            code="REMOTE_WRITE_DISABLED",
            message="REMOTE_WRITE must remain 0 for phase one.",
            stage="PUBLISH_PACKAGE",
            details={"remote_write": os.environ.get("REMOTE_WRITE", "0")},
        )
    if package.get("approval_status") != "APPROVED":
        return None, {}, FailureState(
            code="APPROVAL_REQUIRED",
            message="Only an approved packet may enter a publisher path.",
            stage="PUBLISH_PACKAGE",
        )
    if package.get("approval_integrity") != "PASS":
        return None, {}, FailureState(
            code="APPROVAL_INVALIDATED",
            message="Approved packet integrity was not verified.",
            stage="PUBLISH_PACKAGE",
        )
    packet_sha256 = package.get("packet_sha256")
    if not isinstance(packet_sha256, str) or len(packet_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in packet_sha256
    ):
        return None, {}, FailureState(
            code="APPROVAL_INVALIDATED",
            message="Publish package has no valid approved packet digest.",
            stage="PUBLISH_PACKAGE",
        )
    if not isinstance(raw_files, Mapping) or not isinstance(raw_platforms, Mapping):
        return None, {}, FailureState(
            code="PACKAGE_PLATFORM_SCHEMA_INVALID",
            message="Publish package platform data is invalid.",
            stage="PUBLISH_PACKAGE",
        )
    if not isinstance(planned_actions, Mapping) or set(planned_actions) != set(PLATFORMS):
        return None, {}, FailureState(
            code="PACKAGE_PLAN_INVALID",
            message="Publish package must contain seven local-only planned actions.",
            stage="PUBLISH_PACKAGE",
        )
    if any(
        not isinstance(action, Mapping)
        or action.get("remote_write") != 0
        or action.get("destination") != platform
        for platform, action in planned_actions.items()
    ):
        return None, {}, FailureState(
            code="REMOTE_WRITE_DISABLED",
            message="All planned publisher actions must remain local-only.",
            stage="PUBLISH_PACKAGE",
        )
    if set(raw_files) != set(PLATFORMS) or set(raw_platforms) != set(PLATFORMS):
        return None, {}, FailureState(
            code="PLATFORM_SET_INVALID",
            message="Publish package must contain exactly seven platform files.",
            stage="PUBLISH_PACKAGE",
            details={"expected": list(PLATFORMS)},
        )
    files = {str(platform): str(raw_files[platform]) for platform in PLATFORMS}
    return package_id, files, None


def _write_local_manifest(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(canonical_json(payload) + "\n", encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


__all__ = [
    "DuplicateGuard",
    "PublishResult",
    "Publisher",
    "package_parts",
    "remote_write_enabled",
]
