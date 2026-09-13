"""Small, deterministic media QA for synthetic phase-one descriptors."""

from __future__ import annotations

from pathlib import PurePath
from typing import Any, Mapping, Sequence

from ai_content_factory.core.hashing import canonical_json_hash


EXPECTED = {
    "image": {
        "extension": ".png",
        "format": "png-placeholder",
        "mime_type": "image/png",
    },
    "video": {
        "extension": ".mp4",
        "format": "mp4-placeholder",
        "mime_type": "video/mp4",
    },
    "voice": {
        "extension": ".wav",
        "format": "wav-placeholder",
        "mime_type": "audio/wav",
    },
}


def _check(check_id: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"id": check_id, "passed": bool(passed), "detail": detail}


def _descriptor_digest(asset: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in asset.items() if key != "descriptor_sha256"}
    return canonical_json_hash(payload)


def evaluate_media_manifest(
    manifest: Mapping[str, Any],
    *,
    storyboard: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a neutral PASS/FAIL scorecard without touching media or network."""

    raw_assets = manifest.get("assets", [])
    assets = raw_assets if isinstance(raw_assets, list) else []
    checks: list[dict[str, Any]] = []
    required_types = set(EXPECTED)
    observed_types: set[str] = set()
    asset_ids: list[str] = []

    checks.append(_check("artifact_manifest_present", bool(assets), "At least one descriptor is required."))
    for index, raw in enumerate(assets):
        prefix = f"asset_{index + 1}"
        if not isinstance(raw, Mapping):
            checks.append(_check(f"{prefix}_schema", False, "Descriptor must be an object."))
            continue

        media_type = str(raw.get("media_type", ""))
        expected = EXPECTED.get(media_type)
        observed_types.add(media_type)
        asset_id = str(raw.get("asset_id", ""))
        asset_ids.append(asset_id)
        fmt = str(raw.get("format", ""))
        metadata = raw.get("metadata", {})
        metadata = metadata if isinstance(metadata, Mapping) else {}
        reference = str(raw.get("path_or_reference", ""))
        suffix = PurePath(reference).suffix.lower() if reference else ""

        checks.extend(
            [
                _check(f"{prefix}_known_type", expected is not None, "Media type must be image, video, or voice."),
                _check(f"{prefix}_placeholder", raw.get("placeholder") is True, "Phase one accepts synthetic placeholders only."),
                _check(
                    f"{prefix}_local_reference",
                    bool(reference) and "://" not in reference and not PurePath(reference).is_absolute(),
                    "Reference must be a safe local relative placeholder path.",
                ),
                _check(
                    f"{prefix}_format",
                    bool(expected) and fmt == expected["format"],
                    "Format must match the descriptor media type.",
                ),
                _check(
                    f"{prefix}_extension",
                    bool(expected) and suffix == expected["extension"],
                    "Reference extension must match the descriptor media type.",
                ),
                _check(
                    f"{prefix}_mime_type",
                    bool(expected) and metadata.get("mime_type") == expected["mime_type"],
                    "MIME metadata must match the descriptor media type.",
                ),
                _check(
                    f"{prefix}_checksum",
                    raw.get("descriptor_sha256") == _descriptor_digest(raw),
                    "Descriptor SHA-256 must match canonical descriptor metadata.",
                ),
            ]
        )

        if media_type in {"image", "video"}:
            dimensions_valid = (
                isinstance(metadata.get("width"), int)
                and metadata["width"] > 0
                and isinstance(metadata.get("height"), int)
                and metadata["height"] > 0
            )
            checks.append(_check(f"{prefix}_dimensions", dimensions_valid, "Visual descriptors require positive dimensions."))
        if media_type in {"video", "voice"}:
            duration = raw.get("duration_seconds")
            checks.append(
                _check(
                    f"{prefix}_duration",
                    isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration > 0,
                    "Timed descriptors require a positive duration.",
                )
            )
        if media_type == "voice":
            audio_valid = (
                isinstance(metadata.get("sample_rate_hz"), int)
                and metadata["sample_rate_hz"] > 0
                and metadata.get("channels") in {1, 2}
            )
            checks.append(_check(f"{prefix}_audio_metadata", audio_valid, "Voice descriptors require sample rate and channel metadata."))

    checks.append(
        _check(
            "asset_ids_unique",
            bool(asset_ids) and all(asset_ids) and len(asset_ids) == len(set(asset_ids)),
            "Every descriptor requires a unique non-empty asset ID.",
        )
    )
    checks.append(
        _check(
            "required_asset_types",
            required_types.issubset(observed_types),
            "At least one image, video, and voice descriptor is required.",
        )
    )
    scenes = storyboard.get("scenes", []) if isinstance(storyboard, Mapping) else []
    subtitles_valid = (
        isinstance(scenes, Sequence)
        and not isinstance(scenes, (str, bytes))
        and bool(scenes)
        and all(
            isinstance(scene, Mapping)
            and isinstance(scene.get("voiceover"), str)
            and bool(scene["voiceover"].strip())
            and isinstance(scene.get("start_seconds"), (int, float))
            and isinstance(scene.get("end_seconds"), (int, float))
            and scene["end_seconds"] > scene["start_seconds"]
            for scene in scenes
        )
    )
    checks.append(_check("subtitle_manifest_valid", subtitles_valid, "Storyboard timing and voiceover form the phase-one subtitle manifest."))

    blocking = [item["id"] for item in checks if not item["passed"]]
    status = "PASS" if not blocking else "FAIL"
    return {
        "blocking_reasons": blocking,
        "checks": checks,
        "status": status,
        "summary": f"{len(checks) - len(blocking)}/{len(checks)} media descriptor checks passed.",
    }


__all__ = ["evaluate_media_manifest"]
