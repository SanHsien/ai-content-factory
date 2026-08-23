"""Read-only inspection and validation for pipeline artifacts."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from ai_content_factory.providers.fixtures import PLATFORMS
from .approval import validate_approved_packet

from .models import (
    PipelineState,
    RunStatus,
    STAGE_ORDER,
    StageStatus,
    canonical_json,
    digest_file,
)


REQUIRED_STAGE_FILES = (
    "content_packet.json",
    "research.json",
    "article.md",
    "short_script.md",
    "storyboard.json",
    "media_manifest.json",
    "qa_scorecard.json",
    "approval.json",
    "publish_manifest.json",
    "demo_preview.html",
)
JSON_STAGE_FILES = tuple(
    filename for filename in REQUIRED_STAGE_FILES if filename.endswith(".json")
)
STATE_FILE = "pipeline_state.json"
RUN_LOG_FILE = "run_log.jsonl"
LEGACY_ARTIFACT_FILES = (
    "topic.json",
    "text.json",
    "media.json",
    "media_qa.json",
    "publish_package.json",
)


def _resolve_output_root(root: Path) -> Path:
    """Accept either output/<run_id> or its output parent for read-only APIs."""

    if (root / STATE_FILE).is_file():
        return root
    if root.is_dir():
        candidates = sorted(
            child
            for child in root.iterdir()
            if child.is_dir() and (child / STATE_FILE).is_file()
        )
        if len(candidates) == 1:
            return candidates[0]
    return root


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    complete: bool
    output_dir: str
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    checked_files: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked_files": list(self.checked_files),
            "complete": self.complete,
            "details": {
                str(key): self.details[key] for key in sorted(self.details)
            },
            "errors": list(self.errors),
            "output_dir": self.output_dir,
            "valid": self.valid,
            "warnings": list(self.warnings),
        }


def _read_json(path: Path) -> tuple[Mapping[str, Any] | None, str | None]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)
    if not isinstance(value, Mapping):
        return None, "JSON root must be an object"
    return value, None


def _unsafe_relative_name(name: str) -> bool:
    candidate = Path(name)
    return (
        candidate.is_absolute()
        or ".." in candidate.parts
        or len(candidate.parts) != 2
        or candidate.parts[0] != "platform-ready"
        or candidate.suffix != ".txt"
    )


def validate_output(
    output_dir: str | Path,
    *,
    expected_topic: str | None = None,
) -> ValidationReport:
    """Validate a generated package without changing any files."""

    root = _resolve_output_root(Path(output_dir))
    errors: list[str] = []
    warnings: list[str] = []
    checked: list[str] = []
    details: dict[str, Any] = {}
    state: PipelineState | None = None

    if not root.is_dir():
        return ValidationReport(
            valid=False,
            complete=False,
            output_dir=str(root),
            errors=("OUTPUT_DIRECTORY_MISSING",),
        )

    for filename in (STATE_FILE, RUN_LOG_FILE, *REQUIRED_STAGE_FILES):
        path = root / filename
        if not path.is_file():
            errors.append(f"MISSING_FILE:{filename}")
            continue
        checked.append(filename)

    state_path = root / STATE_FILE
    if state_path.is_file():
        state_data, error = _read_json(state_path)
        if error:
            errors.append(f"INVALID_JSON:{STATE_FILE}:{error}")
        else:
            try:
                state = PipelineState.from_dict(state_data or {})
            except (TypeError, ValueError, KeyError) as exc:
                errors.append(f"INVALID_STATE:{exc}")

    parsed: dict[str, Mapping[str, Any]] = {}
    for filename in JSON_STAGE_FILES:
        path = root / filename
        if not path.is_file():
            continue
        value, error = _read_json(path)
        if error:
            errors.append(f"INVALID_JSON:{filename}:{error}")
        elif value is not None:
            parsed[filename] = value

    for filename in LEGACY_ARTIFACT_FILES:
        if (root / filename).is_file():
            errors.append(f"LEGACY_ARTIFACT_FILENAME:{filename}")

    topic_data = parsed.get("content_packet.json")
    if topic_data is not None:
        topic = str(topic_data.get("topic", ""))
        details["topic"] = topic
        if not topic:
            errors.append("TOPIC_EMPTY")
        if expected_topic is not None and topic != expected_topic:
            errors.append("TOPIC_MISMATCH")
        required_packet_fields = {
            "packet_id", "schema_version", "topic", "locale", "research",
            "article", "short_script", "storyboard", "media_artifacts",
            "platform_copy", "qa", "approval_state", "provenance", "created_at",
        }
        missing_packet_fields = sorted(required_packet_fields - set(topic_data))
        if missing_packet_fields:
            errors.append("CONTENT_PACKET_FIELDS_MISSING:" + ",".join(missing_packet_fields))
        packet_valid, packet_errors, _ = validate_approved_packet(root, topic_data)
        if not packet_valid:
            errors.extend(f"CONTENT_PACKET_INTEGRITY:{item}" for item in packet_errors)

    package = parsed.get("publish_manifest.json")
    package_platforms: Mapping[str, Any] = {}
    if package is not None:
        if package.get("remote_write") != 0:
            errors.append("REMOTE_WRITE_MUST_BE_ZERO")
        raw_platforms = package.get("platforms", {})
        if isinstance(raw_platforms, Mapping):
            package_platforms = raw_platforms
        else:
            errors.append("PLATFORMS_MUST_BE_OBJECT")
        if set(package_platforms) != set(PLATFORMS):
            errors.append("PLATFORM_SET_MISMATCH")
        if package.get("approval_status") != "APPROVED":
            errors.append("PUBLISH_APPROVAL_REQUIRED")
        if package.get("approval_integrity") != "PASS":
            errors.append("PUBLISH_APPROVAL_INTEGRITY_REQUIRED")
        if topic_data is not None and package.get("packet_sha256") != topic_data.get("packet_sha256"):
            errors.append("PUBLISH_PACKET_HASH_MISMATCH")
        if package.get("dedupe_key") != package.get("package_id"):
            errors.append("PUBLISH_DEDUPE_KEY_MISMATCH")
        planned_actions = package.get("planned_actions", {})
        if not isinstance(planned_actions, Mapping) or set(planned_actions) != set(PLATFORMS):
            errors.append("PUBLISH_PLANNED_ACTIONS_INVALID")
        elif any(
            not isinstance(action, Mapping)
            or action.get("remote_write") != 0
            or action.get("destination") != platform
            for platform, action in planned_actions.items()
        ):
            errors.append("PUBLISH_PLANNED_ACTIONS_INVALID")
        if package.get("preview_file") != "demo_preview.html":
            errors.append("PUBLISH_PREVIEW_REFERENCE_INVALID")

    preview_path = root / "demo_preview.html"
    if preview_path.is_file():
        try:
            preview = preview_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"UNREADABLE_PREVIEW:{exc}")
        else:
            lowered = preview.lower()
            if "<!doctype html>" not in lowered or "remote writes: 0" not in lowered:
                errors.append("DEMO_PREVIEW_INVALID")
            if "http://" in lowered or "https://" in lowered:
                errors.append("DEMO_PREVIEW_NETWORK_REFERENCE")

    for platform in PLATFORMS:
        filename = f"platform-ready/{platform}.txt"
        path = root / filename
        if not path.is_file():
            errors.append(f"MISSING_PLATFORM_FILE:{filename}")
            continue
        checked.append(filename)
        if platform in package_platforms:
            try:
                content = path.read_text(encoding="utf-8")
            except OSError as exc:
                errors.append(f"UNREADABLE_PLATFORM_FILE:{filename}:{exc}")
            else:
                if content != str(package_platforms[platform]) + "\n":
                    errors.append(f"PLATFORM_CONTENT_MISMATCH:{filename}")

    if package is not None:
        raw_files = package.get("platform_files", {})
        if not isinstance(raw_files, Mapping):
            errors.append("PLATFORM_FILES_MUST_BE_OBJECT")
        else:
            for platform, filename in raw_files.items():
                if str(platform) not in PLATFORMS or _unsafe_relative_name(str(filename)):
                    errors.append(f"UNSAFE_PLATFORM_PATH:{platform}")

    if state is not None:
        details["run_id"] = state.run_id
        details["status"] = state.status.value
        details["stage_status"] = {
            stage.value: state.record(stage).status.value for stage in STAGE_ORDER
        }
        complete = state.status == RunStatus.SUCCEEDED
        if state.failure is not None:
            errors.append(f"RUN_FAILURE:{state.failure.code}")
        for stage in STAGE_ORDER:
            record = state.record(stage)
            if complete and record.status != StageStatus.SUCCEEDED:
                errors.append(f"STAGE_NOT_SUCCEEDED:{stage.value}")
    else:
        complete = False

    log_path = root / RUN_LOG_FILE
    if log_path.is_file():
        try:
            log_events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]
        except (OSError, json.JSONDecodeError):
            errors.append("RUN_LOG_INVALID")
        else:
            if not log_events or any(not isinstance(event, Mapping) for event in log_events):
                errors.append("RUN_LOG_INVALID")
            elif any("run_id" not in event or "status" not in event for event in log_events):
                errors.append("RUN_LOG_FIELDS_MISSING")

    remote_write = os.environ.get("REMOTE_WRITE", "0")
    if remote_write != "0":
        warnings.append("REMOTE_WRITE_ENVIRONMENT_IS_NOT_ZERO")

    # All JSON artifacts are checked in canonical form only for readability;
    # no timestamp or host path is allowed to make them non-deterministic.
    for filename, value in parsed.items():
        if "private_path" in value or "network_url" in value:
            errors.append(f"FORBIDDEN_METADATA:{filename}")
        if filename != STATE_FILE and not canonical_json(value).strip():
            errors.append(f"EMPTY_ARTIFACT:{filename}")

    return ValidationReport(
        valid=not errors,
        complete=complete,
        output_dir=str(root),
        errors=tuple(errors),
        warnings=tuple(warnings),
        checked_files=tuple(checked),
        details=details,
    )


def inspect_output(output_dir: str | Path) -> dict[str, Any]:
    """Return a compact read-only status summary suitable for CLI output."""

    root = _resolve_output_root(Path(output_dir))
    state_path = root / STATE_FILE
    if not state_path.is_file():
        return {
            "output_dir": str(root),
            "status": "MISSING",
            "next_stage": None,
            "failure": None,
            "stages": {},
        }
    data, error = _read_json(state_path)
    if error or data is None:
        return {
            "output_dir": str(root),
            "status": "INVALID_STATE",
            "error": error or "state is not an object",
        }
    try:
        state = PipelineState.from_dict(data)
    except (TypeError, ValueError, KeyError) as exc:
        return {
            "output_dir": str(root),
            "status": "INVALID_STATE",
            "error": str(exc),
        }
    next_stage = state.next_stage()
    return {
        "current_stage": state.current_stage.value if state.current_stage else None,
        "failure": state.failure.to_dict() if state.failure else None,
        "next_stage": next_stage.value if next_stage else None,
        "output_dir": str(root),
        "run_id": state.run_id,
        "stages": {
            stage.value: state.record(stage).status.value for stage in STAGE_ORDER
        },
        "status": state.status.value,
        "topic": state.topic,
    }


# Public aliases make the read-only API discoverable from either spelling.
inspect_run = inspect_output
validate_run = validate_output


__all__ = [
    "REQUIRED_STAGE_FILES",
    "RUN_LOG_FILE",
    "STATE_FILE",
    "ValidationReport",
    "inspect_output",
    "inspect_run",
    "validate_output",
    "validate_run",
]
