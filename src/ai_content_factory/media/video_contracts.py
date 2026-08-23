"""Provider-neutral video render request and artifact contracts.

The contracts describe local render intent and verified local output. They do
not choose a video provider, call a network service, decode a video
container, or claim that a render is approved or published.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .image_sources import (
    ArtifactProvenance,
    HeroImageArtifact,
    ImageProvenance,
    MaterializationStatus,
)


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
SUPPORTED_VIDEO_MIME_TYPES = frozenset(
    {"video/mp4", "video/webm", "video/quicktime", "video/x-matroska"}
)


class VideoContractError(ValueError):
    """Raised when a video request or artifact violates the local contract."""


class VideoGenerationMode(str, Enum):
    """The provider-neutral render strategies supported by Phase 2R."""

    MOTION_RENDER = "MOTION_RENDER"
    GENERATIVE_I2V = "GENERATIVE_I2V"


GenerationMode = VideoGenerationMode
VideoMode = VideoGenerationMode
Provenance = ImageProvenance
VideoProvenance = ImageProvenance
ArtifactStatus = MaterializationStatus

MOTION_RENDER = VideoGenerationMode.MOTION_RENDER.value
GENERATIVE_I2V = VideoGenerationMode.GENERATIVE_I2V.value
CHATGPT_HANDOFF = ImageProvenance.CHATGPT_HANDOFF.value
CODEX_NATIVE = ImageProvenance.CODEX_NATIVE.value
SYNTHETIC = ImageProvenance.SYNTHETIC.value
PRIVATE_OWNED = ImageProvenance.PRIVATE_OWNED.value


def _coerce_mode(value: VideoGenerationMode | str) -> VideoGenerationMode:
    if isinstance(value, VideoGenerationMode):
        return value
    try:
        return VideoGenerationMode(str(value))
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(item.value for item in VideoGenerationMode)
        raise VideoContractError(
            f"generation_mode must be one of: {allowed}"
        ) from exc


def _coerce_provenance(value: ImageProvenance | str) -> ImageProvenance:
    if isinstance(value, ImageProvenance):
        return value
    try:
        return ImageProvenance(str(value))
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(item.value for item in ImageProvenance)
        raise VideoContractError(f"provenance must be one of: {allowed}") from exc


def _coerce_status(value: MaterializationStatus | str) -> MaterializationStatus:
    if isinstance(value, MaterializationStatus):
        return value
    try:
        return MaterializationStatus(str(value))
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(item.value for item in MaterializationStatus)
        raise VideoContractError(f"status must be one of: {allowed}") from exc


def _coerce_dimensions(
    dimensions: Sequence[int] | Mapping[str, Any] | None,
    width: int | None,
    height: int | None,
) -> tuple[int | None, int | None]:
    resolved_width, resolved_height = width, height
    if dimensions is None:
        return resolved_width, resolved_height
    if isinstance(dimensions, Mapping):
        dimension_width = dimensions.get("width")
        dimension_height = dimensions.get("height")
    elif (
        isinstance(dimensions, Sequence)
        and not isinstance(dimensions, (str, bytes, bytearray))
        and len(dimensions) == 2
    ):
        dimension_width, dimension_height = dimensions
    else:
        raise VideoContractError(
            "dimensions must be a two-item sequence or a width/height mapping"
        )
    if (
        resolved_width is not None
        and dimension_width is not None
        and resolved_width != dimension_width
    ):
        raise VideoContractError("width and dimensions disagree")
    if (
        resolved_height is not None
        and dimension_height is not None
        and resolved_height != dimension_height
    ):
        raise VideoContractError("height and dimensions disagree")
    return (
        dimension_width if resolved_width is None else resolved_width,
        dimension_height if resolved_height is None else resolved_height,
    )


def _validate_sha256(value: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise VideoContractError(
            "sha256 must be a 64-character hexadecimal SHA-256"
        )
    return value.lower()


@dataclass(frozen=True, slots=True, init=False)
class VideoRenderRequest:
    """Provider-neutral intent for a local or future video render."""

    request_id: str
    generation_mode: VideoGenerationMode
    prompt: str
    hero_image: HeroImageArtifact | None
    source_image_artifact_id: str | None
    aspect_ratio: str
    motion_preset: str
    caption_mode: str
    voice_mode: str
    brand_config_reference: str | None
    output_format: str
    width: int
    height: int
    duration_seconds: float
    fps: float
    output_mime: str
    provenance: ImageProvenance
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        request_id: str | None = None,
        generation_mode: VideoGenerationMode | str | None = None,
        prompt: str = "",
        hero_image: HeroImageArtifact | None = None,
        width: int = 1080,
        height: int = 1920,
        duration_seconds: float = 8.0,
        fps: float = 30.0,
        output_mime: str = "video/mp4",
        provenance: ImageProvenance | str = ImageProvenance.SYNTHETIC,
        metadata: Mapping[str, Any] | None = None,
        source_image_artifact_id: str | None = None,
        aspect_ratio: str = "9:16",
        motion_preset: str = "GENTLE_PUSH_IN",
        caption_mode: str = "OPTIONAL_TEXT",
        voice_mode: str = "NONE",
        brand_config_reference: str | Path | None = None,
        output_format: str = "mp4",
        *,
        mode: VideoGenerationMode | str | None = None,
        render_id: str | None = None,
        image: HeroImageArtifact | None = None,
        image_artifact: HeroImageArtifact | None = None,
        duration: float | None = None,
        mime: str | None = None,
        dimensions: Sequence[int] | Mapping[str, Any] | None = None,
    ) -> None:
        resolved_mode = (
            generation_mode
            if generation_mode is not None
            else mode
            if mode is not None
            else VideoGenerationMode.MOTION_RENDER
        )
        resolved_image = (
            hero_image
            if hero_image is not None
            else image
            if image is not None
            else image_artifact
        )
        resolved_width, resolved_height = _coerce_dimensions(
            dimensions, width, height
        )
        if duration is not None:
            if duration_seconds != 8.0 and duration_seconds != duration:
                raise VideoContractError("duration and duration_seconds disagree")
            duration_seconds = duration
        if mime is not None:
            if output_mime != "video/mp4" and output_mime != mime:
                raise VideoContractError("mime and output_mime disagree")
            output_mime = mime
        object.__setattr__(
            self, "request_id", "" if request_id is None else str(request_id)
        )
        if render_id is not None:
            if request_id is not None and request_id != render_id:
                raise VideoContractError("request_id and render_id disagree")
            object.__setattr__(self, "request_id", str(render_id))
        object.__setattr__(self, "generation_mode", _coerce_mode(resolved_mode))
        object.__setattr__(self, "prompt", str(prompt))
        object.__setattr__(self, "hero_image", resolved_image)
        resolved_source_id = source_image_artifact_id
        if resolved_source_id is None and resolved_image is not None:
            resolved_source_id = resolved_image.artifact_id
        object.__setattr__(self, "source_image_artifact_id", resolved_source_id)
        object.__setattr__(self, "aspect_ratio", str(aspect_ratio))
        object.__setattr__(self, "motion_preset", str(motion_preset))
        object.__setattr__(self, "caption_mode", str(caption_mode))
        object.__setattr__(self, "voice_mode", str(voice_mode))
        object.__setattr__(
            self,
            "brand_config_reference",
            None
            if brand_config_reference is None
            else Path(str(brand_config_reference)).name,
        )
        object.__setattr__(self, "output_format", str(output_format).lower())
        object.__setattr__(
            self, "width", 0 if resolved_width is None else resolved_width
        )
        object.__setattr__(
            self, "height", 0 if resolved_height is None else resolved_height
        )
        object.__setattr__(self, "duration_seconds", float(duration_seconds))
        object.__setattr__(self, "fps", float(fps))
        object.__setattr__(self, "output_mime", str(output_mime))
        object.__setattr__(self, "provenance", _coerce_provenance(provenance))
        object.__setattr__(self, "metadata", dict(metadata or {}))

    @property
    def mode(self) -> VideoGenerationMode:
        return self.generation_mode

    @property
    def image(self) -> HeroImageArtifact | None:
        return self.hero_image

    @property
    def image_artifact(self) -> HeroImageArtifact | None:
        return self.hero_image

    @property
    def dimensions(self) -> tuple[int, int]:
        return self.width, self.height

    @property
    def duration(self) -> float:
        return self.duration_seconds

    @property
    def mime(self) -> str:
        return self.output_mime

    def validate(self) -> None:
        if not self.request_id.strip():
            raise VideoContractError("request_id is required")
        if (
            isinstance(self.width, bool)
            or not isinstance(self.width, int)
            or self.width <= 0
            or isinstance(self.height, bool)
            or not isinstance(self.height, int)
            or self.height <= 0
        ):
            raise VideoContractError("video dimensions must be positive integers")
        if self.duration_seconds <= 0:
            raise VideoContractError("duration_seconds must be positive")
        if self.fps <= 0:
            raise VideoContractError("fps must be positive")
        if not self.output_mime.startswith("video/"):
            raise VideoContractError("output_mime must be a video MIME type")
        if self.aspect_ratio != "9:16":
            raise VideoContractError("Phase 2R motion render aspect_ratio must be 9:16")
        if self.output_format != "mp4" or self.output_mime != "video/mp4":
            raise VideoContractError("Phase 2R motion render output must be MP4")
        if not self.motion_preset.strip():
            raise VideoContractError("motion_preset is required")
        if self.caption_mode not in {"NONE", "OPTIONAL_TEXT", "BURNED_TEXT"}:
            raise VideoContractError("caption_mode is invalid")
        if self.voice_mode not in {"NONE", "SILENT", "LOCAL_FILE"}:
            raise VideoContractError("voice_mode is invalid")
        if (
            self.generation_mode is VideoGenerationMode.GENERATIVE_I2V
            and self.hero_image is None
        ):
            raise VideoContractError(
                "GENERATIVE_I2V requires a hero image artifact"
            )
        if self.hero_image is not None:
            self.hero_image.validate()
            if self.source_image_artifact_id != self.hero_image.artifact_id:
                raise VideoContractError(
                    "source_image_artifact_id must match the hero image artifact"
                )
        if not isinstance(self.prompt, str):
            raise VideoContractError("prompt must be text")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "dimensions": {"height": self.height, "width": self.width},
            "duration_seconds": self.duration_seconds,
            "fps": self.fps,
            "generation_mode": self.generation_mode.value,
            "source_image_artifact_id": self.source_image_artifact_id,
            "aspect_ratio": self.aspect_ratio,
            "motion_preset": self.motion_preset,
            "caption_mode": self.caption_mode,
            "voice_mode": self.voice_mode,
            "brand_config_reference": self.brand_config_reference,
            "output_format": self.output_format,
            "metadata": dict(self.metadata),
            "mime": self.output_mime,
            "provenance": self.provenance.value,
            "prompt": self.prompt,
            "request_id": self.request_id,
        }
        result["hero_image"] = (
            self.hero_image.to_dict() if self.hero_image is not None else None
        )
        return result

    as_dict = to_dict

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        hero_image: HeroImageArtifact | None = None,
        hero_image_path: str | Path | None = None,
    ) -> "VideoRenderRequest":
        if not isinstance(value, Mapping):
            raise TypeError("video render request must be a mapping")
        image_value = value.get("hero_image", value.get("image"))
        resolved_image = hero_image
        if resolved_image is None and isinstance(image_value, Mapping):
            resolved_image = HeroImageArtifact.from_dict(
                image_value, path=hero_image_path
            )
        return cls(
            request_id=value.get("request_id", value.get("render_id")),
            generation_mode=value.get(
                "generation_mode",
                value.get("mode", VideoGenerationMode.MOTION_RENDER.value),
            ),
            prompt=str(value.get("prompt", "")),
            hero_image=resolved_image,
            dimensions=value.get("dimensions"),
            duration_seconds=float(
                value.get("duration_seconds", value.get("duration", 8.0))
            ),
            fps=float(value.get("fps", 30.0)),
            output_mime=str(
                value.get("mime", value.get("output_mime", "video/mp4"))
            ),
            provenance=value.get("provenance", ImageProvenance.SYNTHETIC.value),
            metadata=value.get("metadata"),
            source_image_artifact_id=value.get("source_image_artifact_id"),
            aspect_ratio=str(value.get("aspect_ratio", "9:16")),
            motion_preset=str(value.get("motion_preset", "GENTLE_PUSH_IN")),
            caption_mode=str(value.get("caption_mode", "OPTIONAL_TEXT")),
            voice_mode=str(value.get("voice_mode", "NONE")),
            brand_config_reference=value.get("brand_config_reference"),
            output_format=str(value.get("output_format", "mp4")),
        )


@dataclass(frozen=True, slots=True, init=False)
class VideoArtifact:
    """A locally materialized video with declared integrity metadata."""

    artifact_id: str
    path: Path
    sha256: str
    mime: str
    width: int
    height: int
    duration_seconds: float
    generation_mode: VideoGenerationMode
    provenance: ImageProvenance
    fps: float
    status: MaterializationStatus
    source_image_sha256: str
    renderer: str
    renderer_version: str
    preset: str
    created_at: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        artifact_id: str | None = None,
        path: str | Path | None = None,
        sha256: str | None = None,
        mime: str | None = None,
        width: int | None = None,
        height: int | None = None,
        duration_seconds: float = 0.0,
        generation_mode: VideoGenerationMode | str = VideoGenerationMode.MOTION_RENDER,
        provenance: ImageProvenance | str = ImageProvenance.SYNTHETIC,
        fps: float = 30.0,
        status: MaterializationStatus | str = MaterializationStatus.COMPLETE,
        source_image_sha256: str = "",
        renderer: str = "",
        renderer_version: str = "",
        preset: str = "",
        created_at: str = "",
        metadata: Mapping[str, Any] | None = None,
        *,
        mime_type: str | None = None,
        dimensions: Sequence[int] | Mapping[str, Any] | None = None,
        file_path: str | Path | None = None,
        local_path: str | Path | None = None,
        mode: VideoGenerationMode | str | None = None,
        duration: float | None = None,
        frame_rate: float | None = None,
        source_provenance: ImageProvenance | str | None = None,
    ) -> None:
        if path is None:
            path = file_path if file_path is not None else local_path
        if mime is not None and mime_type is not None and mime != mime_type:
            raise VideoContractError("mime and mime_type disagree")
        declared_mime = mime if mime is not None else mime_type
        resolved_width, resolved_height = _coerce_dimensions(
            dimensions, width, height
        )
        if duration is not None:
            if duration_seconds != 0.0 and duration_seconds != duration:
                raise VideoContractError("duration and duration_seconds disagree")
            duration_seconds = duration
        if frame_rate is not None:
            if fps != 30.0 and fps != frame_rate:
                raise VideoContractError("frame_rate and fps disagree")
            fps = frame_rate
        if mode is not None:
            if (
                generation_mode != VideoGenerationMode.MOTION_RENDER
                and generation_mode != mode
            ):
                raise VideoContractError("mode and generation_mode disagree")
            generation_mode = mode
        if source_provenance is not None:
            if (
                provenance != ImageProvenance.SYNTHETIC
                and provenance != source_provenance
            ):
                raise VideoContractError("source_provenance and provenance disagree")
            provenance = source_provenance
        object.__setattr__(
            self, "artifact_id", "" if artifact_id is None else str(artifact_id)
        )
        object.__setattr__(self, "path", Path("") if path is None else Path(path))
        object.__setattr__(
            self, "sha256", "" if sha256 is None else str(sha256)
        )
        object.__setattr__(
            self, "mime", "" if declared_mime is None else str(declared_mime)
        )
        object.__setattr__(
            self, "width", 0 if resolved_width is None else resolved_width
        )
        object.__setattr__(
            self, "height", 0 if resolved_height is None else resolved_height
        )
        object.__setattr__(self, "duration_seconds", float(duration_seconds))
        object.__setattr__(self, "generation_mode", _coerce_mode(generation_mode))
        object.__setattr__(self, "provenance", _coerce_provenance(provenance))
        object.__setattr__(self, "fps", float(fps))
        object.__setattr__(self, "status", _coerce_status(status))
        object.__setattr__(self, "source_image_sha256", str(source_image_sha256))
        object.__setattr__(self, "renderer", str(renderer))
        object.__setattr__(self, "renderer_version", str(renderer_version))
        object.__setattr__(self, "preset", str(preset))
        object.__setattr__(self, "created_at", str(created_at))
        object.__setattr__(self, "metadata", dict(metadata or {}))

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        artifact_id: str | None = None,
        mime: str = "video/mp4",
        width: int,
        height: int,
        duration_seconds: float,
        generation_mode: VideoGenerationMode | str = VideoGenerationMode.MOTION_RENDER,
        provenance: ImageProvenance | str = ImageProvenance.SYNTHETIC,
        fps: float = 30.0,
        source_image_sha256: str = "",
        renderer: str = "",
        renderer_version: str = "",
        preset: str = "",
        created_at: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> "VideoArtifact":
        file_path = Path(path)
        if not file_path.is_file():
            raise VideoContractError("video file is missing")
        try:
            digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise VideoContractError("video file could not be read") from exc
        artifact = cls(
            artifact_id=artifact_id or file_path.stem,
            path=file_path,
            sha256=digest,
            mime=mime,
            width=width,
            height=height,
            duration_seconds=duration_seconds,
            generation_mode=generation_mode,
            provenance=provenance,
            fps=fps,
            source_image_sha256=source_image_sha256,
            renderer=renderer,
            renderer_version=renderer_version,
            preset=preset,
            created_at=created_at,
            metadata=metadata,
        )
        artifact.validate()
        return artifact

    def validate(self) -> None:
        if not self.artifact_id.strip():
            raise VideoContractError("artifact_id is required")
        if not isinstance(self.path, Path) or not self.path.is_file():
            raise VideoContractError("video file is missing")
        if not self.mime.startswith("video/"):
            raise VideoContractError("MIME must be a video MIME type")
        if (
            isinstance(self.width, bool)
            or not isinstance(self.width, int)
            or self.width <= 0
            or isinstance(self.height, bool)
            or not isinstance(self.height, int)
            or self.height <= 0
        ):
            raise VideoContractError("video dimensions must be positive integers")
        if self.duration_seconds <= 0:
            raise VideoContractError("duration_seconds must be positive")
        if self.fps <= 0:
            raise VideoContractError("fps must be positive")
        declared_sha = _validate_sha256(self.sha256)
        try:
            actual_sha = hashlib.sha256(self.path.read_bytes()).hexdigest()
        except OSError as exc:
            raise VideoContractError("video file could not be read") from exc
        if actual_sha != declared_sha:
            raise VideoContractError("SHA-256 does not match video bytes")
        if self.source_image_sha256:
            _validate_sha256(self.source_image_sha256)

    def is_valid(self) -> bool:
        try:
            self.validate()
        except (OSError, TypeError, ValueError):
            return False
        return True

    @property
    def mime_type(self) -> str:
        return self.mime

    @property
    def dimensions(self) -> tuple[int, int]:
        return self.width, self.height

    @property
    def duration(self) -> float:
        return self.duration_seconds

    @property
    def mode(self) -> VideoGenerationMode:
        return self.generation_mode

    @property
    def frame_rate(self) -> float:
        return self.fps

    @property
    def file_path(self) -> Path:
        return self.path

    @property
    def local_path(self) -> Path:
        return self.path

    @property
    def artifact_sha256(self) -> str:
        return self.sha256

    @property
    def output_sha256(self) -> str:
        return self.sha256

    def to_dict(self, *, include_path: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "artifact_id": self.artifact_id,
            "artifact_type": "video",
            "dimensions": {"height": self.height, "width": self.width},
            "duration_seconds": self.duration_seconds,
            "fps": self.fps,
            "generation_mode": self.generation_mode.value,
            "source_image_sha256": self.source_image_sha256,
            "output_sha256": self.sha256,
            "renderer": self.renderer,
            "renderer_version": self.renderer_version,
            "preset": self.preset,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
            "mime": self.mime,
            "provenance": self.provenance.value,
            "sha256": self.sha256,
            "status": self.status.value,
        }
        if include_path:
            result["path"] = self.path.name
        return result

    as_dict = to_dict

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        path: str | Path | None = None,
    ) -> "VideoArtifact":
        if not isinstance(value, Mapping):
            raise TypeError("video artifact manifest must be a mapping")
        sha256_value = value.get("sha256", value.get("output_sha256"))
        if (
            value.get("sha256") is not None
            and value.get("output_sha256") is not None
            and value.get("sha256") != value.get("output_sha256")
        ):
            raise VideoContractError("sha256 and output_sha256 disagree")
        return cls(
            artifact_id=value.get("artifact_id"),
            path=path if path is not None else value.get("path"),
            sha256=sha256_value,
            mime=value.get("mime", value.get("mime_type")),
            dimensions=value.get("dimensions"),
            duration_seconds=value.get(
                "duration_seconds", value.get("duration", 0.0)
            ),
            fps=value.get("fps", value.get("frame_rate", 30.0)),
            generation_mode=value.get(
                "generation_mode",
                value.get("mode", VideoGenerationMode.MOTION_RENDER.value),
            ),
            provenance=value.get("provenance", ImageProvenance.SYNTHETIC.value),
            status=value.get("status", MaterializationStatus.COMPLETE.value),
            source_image_sha256=value.get("source_image_sha256", ""),
            renderer=value.get("renderer", ""),
            renderer_version=value.get("renderer_version", ""),
            preset=value.get("preset", ""),
            created_at=value.get("created_at", ""),
            metadata=value.get("metadata"),
        )


class GenerativeVideoProvider(Protocol):
    """Future provider boundary for real GENERATIVE_I2V implementations.

    Phase 2R intentionally supplies no implementation. A future adapter must
    remain explicit and separately reviewed for cost, credentials, and rights.
    """

    provider_id: str

    def generate_video(
        self,
        request: VideoRenderRequest,
        *,
        output_dir: str | Path,
    ) -> VideoArtifact:
        """Generate and materialize a verified video artifact."""


__all__ = [
    "ArtifactProvenance",
    "ArtifactStatus",
    "CHATGPT_HANDOFF",
    "CODEX_NATIVE",
    "GENERATIVE_I2V",
    "GenerativeVideoProvider",
    "GenerationMode",
    "ImageProvenance",
    "MOTION_RENDER",
    "PRIVATE_OWNED",
    "Provenance",
    "SYNTHETIC",
    "SUPPORTED_VIDEO_MIME_TYPES",
    "VideoArtifact",
    "VideoContractError",
    "VideoGenerationMode",
    "VideoMode",
    "VideoProvenance",
    "VideoRenderRequest",
]
