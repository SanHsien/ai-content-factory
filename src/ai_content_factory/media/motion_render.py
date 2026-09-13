"""Optional, local HyperFrames motion-render video provider.

The core project intentionally has no runtime dependencies outside Python's
standard library.  This adapter keeps that boundary intact: preparing a job
only reads and copies local files, while :meth:`MotionRenderVideoProvider.render`
is the explicit opt-in operation that starts a pinned, npm-offline HyperFrames
command.

The provider is deliberately conservative about evidence.  A successful
HyperFrames command sequence proves that the local renderer completed; an
available ``ffprobe`` adds container-level evidence for the requested frame
size, frame rate, and duration.  Neither path contacts an API or reads an API
key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import html
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable, Mapping, Sequence

from .video_contracts import (
    VideoArtifact,
    VideoGenerationMode,
    VideoRenderRequest,
)


PROVIDER_ID = "motion-render"
HYPERFRAMES_PROVIDER_ID = PROVIDER_ID
DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920
DEFAULT_FPS = 30
DEFAULT_DURATION_SECONDS = 8.0
MIN_DURATION_SECONDS = 7.5
MAX_DURATION_SECONDS = 8.5
DEFAULT_OUTPUT_NAME = "render.mp4"
DEFAULT_NPX_COMMAND = ("npx", "--offline", "--yes", "hyperframes@0.7.106")
HYPERFRAMES_VERSION = "0.7.106"


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TEMPLATE_PATH = _REPOSITORY_ROOT / "examples" / "demo-brand" / "video" / "index.html"


class MotionPreset(str, Enum):
    """Stable, local motion choices exposed by the provider."""

    GENTLE_PUSH_IN = "GENTLE_PUSH_IN"
    SLOW_PAN = "SLOW_PAN"
    EDITORIAL_SHORT = "EDITORIAL_SHORT"
    WARM_MEMORY = "WARM_MEMORY"


PRESETS = tuple(item.value for item in MotionPreset)
SUPPORTED_PRESETS = frozenset(PRESETS)


class MotionRenderErrorCode(str, Enum):
    """Machine-readable failures owned by this optional adapter."""

    INVALID_INPUT = "MOTION_RENDER_INVALID_INPUT"
    TEMPLATE_MISSING = "MOTION_RENDER_TEMPLATE_MISSING"
    TEMPLATE_INVALID = "MOTION_RENDER_TEMPLATE_INVALID"
    JOB_CONFLICT = "MOTION_RENDER_JOB_CONFLICT"
    RENDER_EXPLICIT_REQUIRED = "MOTION_RENDER_EXPLICIT_REQUIRED"
    RENDERER_MISSING = "MOTION_RENDERER_MISSING"
    VALIDATION_FAILED = "MOTION_RENDER_VALIDATION_FAILED"
    RENDER_FAILED = "MOTION_RENDER_FAILED"
    OUTPUT_MISSING = "MOTION_RENDER_OUTPUT_MISSING"
    FFPROBE_FAILED = "MOTION_RENDER_FFPROBE_FAILED"
    PROVENANCE_FAILED = "MOTION_RENDER_PROVENANCE_FAILED"


@dataclass(frozen=True, slots=True)
class MotionRenderFailure:
    """Sanitized failure details suitable for JSON logs or handoff."""

    stage: str
    provider: str
    error_code: MotionRenderErrorCode
    sanitized_message: str
    recoverable: bool = False
    retryable: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def code(self) -> str:
        return self.error_code.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.error_code.value,
            "details": dict(self.details),
            "error_code": self.error_code.value,
            "provider": self.provider,
            "recoverable": self.recoverable,
            "retryable": self.retryable,
            "sanitized_message": self.sanitized_message,
            "stage": self.stage,
        }


class MotionRenderError(RuntimeError):
    """Raised when local job creation or explicit rendering cannot complete."""

    def __init__(self, failure: MotionRenderFailure) -> None:
        self.failure = failure
        super().__init__(failure.sanitized_message)

    @property
    def code(self) -> str:
        return self.failure.code

    @property
    def error_code(self) -> MotionRenderErrorCode:
        return self.failure.error_code

    @property
    def stage(self) -> str:
        return self.failure.stage

    def to_dict(self) -> dict[str, Any]:
        return self.failure.to_dict()


@dataclass(frozen=True, slots=True)
class MotionRenderRequest:
    """Validated input for a deterministic vertical motion render."""

    source_image: Path | str
    output_dir: Path | str
    preset: MotionPreset | str = MotionPreset.GENTLE_PUSH_IN
    job_id: str | None = None
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    fps: int = DEFAULT_FPS
    duration_seconds: float = DEFAULT_DURATION_SECONDS
    output_name: str = DEFAULT_OUTPUT_NAME
    hook: str = ""
    subtitle: str = ""
    cta: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_image", Path(self.source_image))
        object.__setattr__(self, "output_dir", Path(self.output_dir))

    @property
    def source_path(self) -> Path:
        """Compatibility alias used by some provider contract drafts."""

        return Path(self.source_image)

    @property
    def duration(self) -> float:
        return self.duration_seconds

    def normalized_preset(self) -> str:
        return _normalize_preset(self.preset)

    def validate(self) -> None:
        source = Path(self.source_image)
        output_dir = Path(self.output_dir)
        if not source.is_file():
            raise ValueError("source image must be a local file")
        if not source.suffix:
            raise ValueError("source image must have an image extension")
        if not output_dir:
            raise ValueError("output directory is required")
        _normalize_preset(self.preset)
        if self.width != DEFAULT_WIDTH or self.height != DEFAULT_HEIGHT:
            raise ValueError("motion render output is fixed at 1080x1920")
        if self.fps != DEFAULT_FPS:
            raise ValueError("motion render output is fixed at 30 fps")
        if (
            isinstance(self.duration_seconds, bool)
            or not isinstance(self.duration_seconds, (int, float))
            or not math.isfinite(float(self.duration_seconds))
            or not MIN_DURATION_SECONDS <= float(self.duration_seconds) <= MAX_DURATION_SECONDS
        ):
            raise ValueError("motion render duration must be approximately 8 seconds")
        _validate_output_name(self.output_name)
        if self.job_id is not None and not _is_safe_job_id(self.job_id):
            raise ValueError("job id must be a short local identifier")


@dataclass(frozen=True, slots=True)
class MotionRenderJob:
    """A local, self-contained HyperFrames composition ready to render."""

    job_id: str
    job_dir: Path
    composition_path: Path
    source_image_path: Path
    output_path: Path
    preset: str
    width: int
    height: int
    fps: int
    duration_seconds: float
    source_sha256: str
    composition_sha256: str
    hook: str
    subtitle: str
    cta: str

    @property
    def composition(self) -> Path:
        return self.composition_path

    @property
    def source_path(self) -> Path:
        return self.source_image_path

    @property
    def output(self) -> Path:
        return self.output_path

    def to_dict(self) -> dict[str, Any]:
        return {
            "composition": self.composition_path.name,
            "duration_seconds": self.duration_seconds,
            "fps": self.fps,
            "height": self.height,
            "job_id": self.job_id,
            "output": self.output_path.name,
            "preset": self.preset,
            "source_image": self.source_image_path.name,
            "source_sha256": self.source_sha256,
            "text": {
                "cta": self.cta,
                "hook": self.hook,
                "subtitle": self.subtitle,
            },
            "width": self.width,
        }


@dataclass(frozen=True, slots=True)
class MotionRenderArtifact:
    """Materialized video plus local QA/provenance references."""

    artifact_id: str
    path: Path
    provenance_path: Path
    qa_path: Path
    job_dir: Path
    provider: str
    preset: str
    sha256: str
    mime: str = "video/mp4"
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    fps: int = DEFAULT_FPS
    duration_seconds: float = DEFAULT_DURATION_SECONDS
    qa_status: str = "PASS"
    review_state: str = "MANUAL_REVIEW_REQUIRED"

    @property
    def video_path(self) -> Path:
        return self.path

    @property
    def output_path(self) -> Path:
        return self.path

    @property
    def artifact_sha256(self) -> str:
        return self.sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "duration_seconds": self.duration_seconds,
            "fps": self.fps,
            "height": self.height,
            "mime": self.mime,
            "path": self.path.name,
            "preset": self.preset,
            "provider": self.provider,
            "provenance_path": self.provenance_path.name,
            "qa_path": self.qa_path.name,
            "qa_status": self.qa_status,
            "review_state": self.review_state,
            "sha256": self.sha256,
            "width": self.width,
        }


# Names used by early Phase 2R contract drafts.  Keeping aliases local makes
# this module usable before a separate Luna A contract module lands, without
# requiring any change to that module or to the Phase 1 core.
MotionRenderResult = MotionRenderArtifact
MotionVideoArtifact = MotionRenderArtifact
VideoRenderResult = MotionRenderArtifact


def _normalize_preset(value: MotionPreset | str) -> str:
    candidate = value.value if isinstance(value, MotionPreset) else str(value)
    normalized = candidate.strip().upper().replace("-", "_")
    if normalized not in SUPPORTED_PRESETS:
        raise ValueError("unsupported motion preset")
    return normalized


def _validate_output_name(value: str) -> None:
    if not isinstance(value, str) or not value or Path(value).name != value:
        raise ValueError("output name must be a relative file name")
    if Path(value).suffix.lower() != ".mp4":
        raise ValueError("output name must use the .mp4 extension")


def _is_safe_job_id(value: str) -> bool:
    return bool(value) and len(value) <= 80 and Path(value).name == value and value not in {".", ".."}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _format_number(value: float | int) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.3f}".rstrip("0").rstrip(".")


def _source_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
        return suffix
    raise ValueError("source image must be PNG, JPEG, WebP, or SVG")


def _source_mime(path: Path) -> str:
    return {
        ".jpeg": "image/jpeg",
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".webp": "image/webp",
    }[path.suffix.lower()]


def _json_output(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(_json_output(value), encoding="utf-8")
    temporary.replace(path)


def _safe_completed_process_output(result: Any) -> str:
    """Return output only for internal classification; never expose it."""

    output = getattr(result, "stdout", "")
    error = getattr(result, "stderr", "")
    values = [output, error]
    return "\n".join(
        item.decode("utf-8", errors="replace") if isinstance(item, bytes) else str(item or "")
        for item in values
    ).lower()


def _offline_process_env() -> dict[str, str]:
    """Pass only renderer essentials, never arbitrary credential variables."""

    allowed = {
        "APPDATA",
        "COMSPEC",
        "HOME",
        "LANG",
        "LOCALAPPDATA",
        "NODE_PATH",
        "PATH",
        "PATHEXT",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    }
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in allowed
    }
    environment.update(
        {
            "NO_UPDATE_NOTIFIER": "1",
            "npm_config_offline": "true",
        }
    )
    return environment


class MotionRenderVideoProvider:
    """Optional local HyperFrames provider with an explicit render boundary."""

    fixture_only = False
    provider_id = PROVIDER_ID

    def __init__(
        self,
        *,
        template_path: Path | str | None = None,
        npx_command: Sequence[str] | str = DEFAULT_NPX_COMMAND,
        runner: Callable[..., Any] | None = None,
        ffprobe_command: str = "ffprobe",
        timeout_seconds: float | None = 300.0,
    ) -> None:
        self.template_path = Path(template_path) if template_path is not None else DEFAULT_TEMPLATE_PATH
        if isinstance(npx_command, str):
            self.npx_command = (npx_command,)
        else:
            self.npx_command = tuple(str(item) for item in npx_command)
        self.ffprobe_command = str(ffprobe_command)
        self.timeout_seconds = timeout_seconds
        self._uses_default_runner = runner is None
        self._runner = runner or subprocess.run

    def create_job(
        self,
        source_image: Path | str | MotionRenderRequest,
        *,
        output_dir: Path | str | None = None,
        preset: MotionPreset | str = MotionPreset.GENTLE_PUSH_IN,
        job_id: str | None = None,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fps: int = DEFAULT_FPS,
        duration_seconds: float = DEFAULT_DURATION_SECONDS,
        output_name: str = DEFAULT_OUTPUT_NAME,
        hook: str = "",
        subtitle: str = "",
        cta: str = "",
    ) -> MotionRenderJob:
        """Build a local composition without invoking any external process."""

        request = self._coerce_request(
            source_image,
            output_dir=output_dir,
            preset=preset,
            job_id=job_id,
            width=width,
            height=height,
            fps=fps,
            duration_seconds=duration_seconds,
            output_name=output_name,
            hook=hook,
            subtitle=subtitle,
            cta=cta,
        )
        try:
            request.validate()
            source = Path(request.source_image).resolve()
            suffix = _source_suffix(source)
        except (OSError, ValueError) as exc:
            raise self._error(
                MotionRenderErrorCode.INVALID_INPUT,
                "prepare",
                "Motion render input is invalid or unavailable.",
                recoverable=False,
            ) from exc

        template = self.template_path
        if not template.is_file():
            raise self._error(
                MotionRenderErrorCode.TEMPLATE_MISSING,
                "prepare",
                "The local HyperFrames composition template is missing.",
                recoverable=False,
            )
        try:
            template_text = template.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise self._error(
                MotionRenderErrorCode.TEMPLATE_INVALID,
                "prepare",
                "The local HyperFrames composition template cannot be read.",
                recoverable=False,
            ) from exc

        source_sha256 = _sha256_file(source)
        template_sha256 = hashlib.sha256(template_text.encode("utf-8")).hexdigest()
        normalized_preset = request.normalized_preset()
        resolved_output_dir = Path(request.output_dir).resolve()
        resolved_output_dir.mkdir(parents=True, exist_ok=True)
        resolved_job_id = request.job_id or self._job_id(
            source_sha256=source_sha256,
            preset=normalized_preset,
            width=request.width,
            height=request.height,
            fps=request.fps,
            duration_seconds=float(request.duration_seconds),
            output_name=request.output_name,
            hook=request.hook,
            subtitle=request.subtitle,
            cta=request.cta,
            template_sha256=template_sha256,
        )
        job_dir = resolved_output_dir / f"job-{resolved_job_id}"
        job_dir.mkdir(parents=True, exist_ok=True)

        source_destination = job_dir / f"source-image{suffix}"
        if source_destination.exists():
            if not source_destination.is_file() or _sha256_file(source_destination) != source_sha256:
                raise self._error(
                    MotionRenderErrorCode.JOB_CONFLICT,
                    "prepare",
                    "The deterministic render job contains a conflicting source image.",
                    recoverable=False,
                )
        else:
            shutil.copyfile(source, source_destination)

        composition_text = self._render_template(
            template_text,
            source_name=source_destination.name,
            preset=normalized_preset,
            width=request.width,
            height=request.height,
            fps=request.fps,
            duration_seconds=float(request.duration_seconds),
            hook=request.hook,
            subtitle=request.subtitle,
            cta=request.cta,
        )
        composition_path = job_dir / "index.html"
        if composition_path.exists():
            try:
                existing = composition_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise self._error(
                    MotionRenderErrorCode.JOB_CONFLICT,
                    "prepare",
                    "The deterministic render job contains an unreadable composition.",
                    recoverable=False,
                ) from exc
            if existing != composition_text:
                raise self._error(
                    MotionRenderErrorCode.JOB_CONFLICT,
                    "prepare",
                    "The deterministic render job contains a conflicting composition.",
                    recoverable=False,
                )
        else:
            composition_path.write_text(composition_text, encoding="utf-8")

        composition_sha256 = _sha256_file(composition_path)
        return MotionRenderJob(
            composition_sha256=composition_sha256,
            composition_path=composition_path,
            duration_seconds=float(request.duration_seconds),
            fps=request.fps,
            height=request.height,
            job_dir=job_dir,
            job_id=resolved_job_id,
            output_path=job_dir / request.output_name,
            preset=normalized_preset,
            source_image_path=source_destination,
            source_sha256=source_sha256,
            hook=request.hook,
            subtitle=request.subtitle,
            cta=request.cta,
            width=request.width,
        )

    prepare_job = create_job

    def render(
        self,
        request: MotionRenderRequest | Path | str | None = None,
        *,
        source_image: Path | str | None = None,
        source_path: Path | str | None = None,
        output_dir: Path | str | None = None,
        output_path: Path | str | None = None,
        preset: MotionPreset | str = MotionPreset.GENTLE_PUSH_IN,
        job_id: str | None = None,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fps: int = DEFAULT_FPS,
        duration_seconds: float = DEFAULT_DURATION_SECONDS,
        hook: str = "",
        subtitle: str = "",
        cta: str = "",
    ) -> MotionRenderArtifact:
        """Run lint, validate, inspect, render, and optional local ffprobe QA.

        This is the only method in this adapter that invokes an external
        process.  ``create_job``/``prepare_job`` remain safe for offline tests
        and callers that only need to inspect the generated composition.
        """

        request = self._coerce_render_request(
            request,
            source_image=source_image,
            source_path=source_path,
            output_dir=output_dir,
            output_path=output_path,
            preset=preset,
            job_id=job_id,
            width=width,
            height=height,
            fps=fps,
            duration_seconds=duration_seconds,
            hook=hook,
            subtitle=subtitle,
            cta=cta,
        )
        job = self.create_job(request)
        command_status: dict[str, str] = {}
        for phase, command in self._hyperframes_commands(job):
            result = self._run_external(command, cwd=job.job_dir, stage=phase)
            returncode = _returncode(result)
            if returncode != 0:
                output = _safe_completed_process_output(result)
                missing = returncode == 127 or any(
                    marker in output
                    for marker in (
                        "not found",
                        "not recognized as an internal",
                        "could not determine executable",
                        "cannot find module",
                    )
                )
                code = MotionRenderErrorCode.RENDERER_MISSING if missing else (
                    MotionRenderErrorCode.RENDER_FAILED
                    if phase == "render"
                    else MotionRenderErrorCode.VALIDATION_FAILED
                )
                message = (
                    "The local HyperFrames renderer is unavailable."
                    if missing
                    else (
                        "The HyperFrames render command failed."
                        if phase == "render"
                        else "A HyperFrames composition check failed."
                    )
                )
                raise self._error(
                    code,
                    phase,
                    message,
                    recoverable=not missing,
                    retryable=not missing and phase == "render",
                    details={"command": phase, "returncode": returncode},
                )
            command_status[phase] = "PASS"

        if not job.output_path.is_file() or job.output_path.stat().st_size <= 0:
            raise self._error(
                MotionRenderErrorCode.OUTPUT_MISSING,
                "output",
                "HyperFrames completed without producing a non-empty MP4.",
                recoverable=False,
            )

        ffprobe = self._probe_output(job)
        output_sha256 = _sha256_file(job.output_path)
        qa = self._qa_metadata(job, output_sha256=output_sha256, ffprobe=ffprobe, command_status=command_status)
        provenance = self._provenance_metadata(
            job,
            output_sha256=output_sha256,
            qa=qa,
            command_status=command_status,
        )
        provenance_path = job.job_dir / "video_provenance.json"
        qa_path = job.job_dir / "video_qa.json"
        try:
            _write_json_atomic(qa_path, qa)
            _write_json_atomic(provenance_path, provenance)
        except (OSError, TypeError, ValueError) as exc:
            raise self._error(
                MotionRenderErrorCode.PROVENANCE_FAILED,
                "provenance",
                "Video QA or provenance metadata could not be written.",
                recoverable=False,
            ) from exc

        return MotionRenderArtifact(
            artifact_id=f"video-{job.job_id}",
            duration_seconds=job.duration_seconds,
            fps=job.fps,
            height=job.height,
            job_dir=job.job_dir,
            path=job.output_path,
            preset=job.preset,
            provider=self.provider_id,
            provenance_path=provenance_path,
            qa_path=qa_path,
            qa_status=str(qa["status"]),
            review_state="MANUAL_REVIEW_REQUIRED",
            sha256=output_sha256,
            width=job.width,
        )

    render_video = render
    render_motion = render

    def render_contract(
        self,
        request: VideoRenderRequest,
        *,
        output_dir: Path | str,
    ) -> VideoArtifact:
        """Materialize a provider-neutral MOTION_RENDER request locally."""

        request.validate()
        if request.generation_mode is not VideoGenerationMode.MOTION_RENDER:
            raise self._error(
                MotionRenderErrorCode.INVALID_INPUT,
                "prepare",
                "MotionRenderVideoProvider only accepts MOTION_RENDER requests.",
                recoverable=False,
            )
        if request.hero_image is None:
            raise self._error(
                MotionRenderErrorCode.INVALID_INPUT,
                "prepare",
                "A local hero image artifact is required for motion rendering.",
                recoverable=False,
            )
        metadata = dict(request.metadata)
        internal = MotionRenderRequest(
            source_image=request.hero_image.path,
            output_dir=output_dir,
            preset=request.motion_preset,
            job_id=None,
            width=request.width,
            height=request.height,
            fps=int(request.fps),
            duration_seconds=request.duration_seconds,
            output_name=str(metadata.get("output_name", DEFAULT_OUTPUT_NAME)),
            hook=str(metadata.get("hook", "")),
            subtitle=str(metadata.get("subtitle", "")),
            cta=str(metadata.get("cta", "")),
        )
        rendered = self.render(internal)
        if rendered.qa_status != "PASS":
            raise self._error(
                MotionRenderErrorCode.FFPROBE_FAILED,
                "qa",
                "The rendered video did not pass required local media QA.",
                recoverable=False,
            )
        return VideoArtifact.from_file(
            rendered.path,
            artifact_id=rendered.artifact_id,
            width=rendered.width,
            height=rendered.height,
            duration_seconds=rendered.duration_seconds,
            generation_mode=VideoGenerationMode.MOTION_RENDER,
            provenance=request.provenance,
            fps=rendered.fps,
            source_image_sha256=request.hero_image.sha256,
            renderer="hyperframes",
            renderer_version=HYPERFRAMES_VERSION,
            preset=rendered.preset,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "brand_config_reference": request.brand_config_reference,
                "caption_mode": request.caption_mode,
                "motion_preset": rendered.preset,
                "provider": self.provider_id,
                "provenance_file": rendered.provenance_path.name,
                "qa_file": rendered.qa_path.name,
                "renderer": "hyperframes",
                "renderer_version": HYPERFRAMES_VERSION,
                "review_state": rendered.review_state,
                "request_id": request.request_id,
                "source_image_artifact_id": request.source_image_artifact_id,
                "source_image_sha256": request.hero_image.sha256,
                "voice_mode": request.voice_mode,
            },
        )

    def generate(
        self,
        prompt: str = "",
        *,
        topic: str | None = None,
        brand: Any | None = None,
        source_image: Path | str | None = None,
        output_dir: Path | str | None = None,
        preset: MotionPreset | str = MotionPreset.GENTLE_PUSH_IN,
        render: bool = False,
        **kwargs: Any,
    ) -> MotionRenderArtifact:
        """Compatibility entry point that is fail-closed unless explicit.

        The Phase 1 ``VideoProvider`` protocol uses ``generate`` for
        descriptors, while this optional provider creates a real local video.
        Requiring ``render=True`` prevents an orchestration call that merely
        asks for a descriptor from unexpectedly starting npx.
        """

        del prompt, topic, brand
        if not render:
            raise self._error(
                MotionRenderErrorCode.RENDER_EXPLICIT_REQUIRED,
                "authorize",
                "Motion rendering requires an explicit render operation.",
                recoverable=True,
            )
        return self.render(
            source_image=source_image,
            output_dir=output_dir,
            preset=preset,
            **kwargs,
        )

    def _coerce_request(
        self,
        source_image: Path | str | MotionRenderRequest,
        *,
        output_dir: Path | str | None,
        preset: MotionPreset | str,
        job_id: str | None,
        width: int,
        height: int,
        fps: int,
        duration_seconds: float,
        output_name: str,
        hook: str,
        subtitle: str,
        cta: str,
    ) -> MotionRenderRequest:
        if isinstance(source_image, MotionRenderRequest):
            return source_image
        if output_dir is None:
            raise self._error(
                MotionRenderErrorCode.INVALID_INPUT,
                "prepare",
                "A local output directory is required for a motion render job.",
                recoverable=False,
            )
        return MotionRenderRequest(
            duration_seconds=duration_seconds,
            fps=fps,
            height=height,
            job_id=job_id,
            output_dir=output_dir,
            output_name=output_name,
            hook=hook,
            subtitle=subtitle,
            cta=cta,
            preset=preset,
            source_image=source_image,
            width=width,
        )

    def _coerce_render_request(
        self,
        request: MotionRenderRequest | Path | str | None,
        *,
        source_image: Path | str | None,
        source_path: Path | str | None,
        output_dir: Path | str | None,
        output_path: Path | str | None,
        preset: MotionPreset | str,
        job_id: str | None,
        width: int,
        height: int,
        fps: int,
        duration_seconds: float,
        hook: str,
        subtitle: str,
        cta: str,
    ) -> MotionRenderRequest:
        if isinstance(request, MotionRenderRequest):
            if output_path is not None:
                raise self._error(
                    MotionRenderErrorCode.INVALID_INPUT,
                    "prepare",
                    "A render request cannot also provide an output path override.",
                    recoverable=False,
                )
            return request
        resolved_source = source_image or source_path or request
        if resolved_source is None:
            raise self._error(
                MotionRenderErrorCode.INVALID_INPUT,
                "prepare",
                "A local source image is required for a motion render.",
                recoverable=False,
            )
        resolved_output_dir = output_dir
        resolved_output_name = DEFAULT_OUTPUT_NAME
        if output_path is not None:
            output_candidate = Path(output_path)
            if output_candidate.is_absolute():
                if resolved_output_dir is None:
                    resolved_output_dir = output_candidate.parent
                elif output_candidate.parent.resolve() != Path(resolved_output_dir).resolve():
                    raise self._error(
                        MotionRenderErrorCode.INVALID_INPUT,
                        "prepare",
                        "The output path must stay inside the requested output directory.",
                        recoverable=False,
                    )
                resolved_output_name = output_candidate.name
            else:
                resolved_output_name = str(output_candidate)
        return self._coerce_request(
            resolved_source,
            output_dir=resolved_output_dir,
            preset=preset,
            job_id=job_id,
            width=width,
            height=height,
            fps=fps,
            duration_seconds=duration_seconds,
            output_name=resolved_output_name,
            hook=hook,
            subtitle=subtitle,
            cta=cta,
        )

    @staticmethod
    def _job_id(
        *,
        source_sha256: str,
        preset: str,
        width: int,
        height: int,
        fps: int,
        duration_seconds: float,
        output_name: str,
        hook: str,
        subtitle: str,
        cta: str,
        template_sha256: str,
    ) -> str:
        digest = _canonical_hash(
            {
                "duration_seconds": duration_seconds,
                "fps": fps,
                "height": height,
                "output_name": output_name,
                "preset": preset,
                "source_sha256": source_sha256,
                "text": {"cta": cta, "hook": hook, "subtitle": subtitle},
                "template_sha256": template_sha256,
                "width": width,
            }
        )
        return digest[:20]

    @staticmethod
    def _render_template(
        template_text: str,
        *,
        source_name: str,
        preset: str,
        width: int,
        height: int,
        fps: int,
        duration_seconds: float,
        hook: str,
        subtitle: str,
        cta: str,
    ) -> str:
        if not template_text.strip():
            raise MotionRenderError(
                MotionRenderFailure(
                    error_code=MotionRenderErrorCode.TEMPLATE_INVALID,
                    provider=PROVIDER_ID,
                    recoverable=False,
                    sanitized_message="The local HyperFrames composition template is empty.",
                    stage="prepare",
                )
            )
        values = {
            "__SOURCE_IMAGE__": source_name,
            "__MOTION_PRESET__": preset,
            "__WIDTH__": str(width),
            "__HEIGHT__": str(height),
            "__FPS__": str(fps),
            "__DURATION__": _format_number(duration_seconds),
            "__HOOK__": html.escape(hook, quote=False),
            "__SUBTITLE__": html.escape(subtitle, quote=False),
            "__CTA__": html.escape(cta, quote=False),
        }
        result = template_text
        for token, replacement in values.items():
            result = result.replace(token, replacement)
        # Permit a simple custom template that follows the demo asset naming
        # convention but does not use the explicit token.
        if "__SOURCE_IMAGE__" in template_text:
            return result
        if "source-image.svg" in result:
            return result.replace("source-image.svg", source_name)
        raise MotionRenderError(
            MotionRenderFailure(
                error_code=MotionRenderErrorCode.TEMPLATE_INVALID,
                provider=PROVIDER_ID,
                recoverable=False,
                sanitized_message="The HyperFrames composition has no source-image placeholder.",
                stage="prepare",
            )
        )

    def _hyperframes_commands(self, job: MotionRenderJob) -> tuple[tuple[str, tuple[str, ...]], ...]:
        base = tuple(self.npx_command)
        return (
            ("lint", base + ("lint", "--json")),
            ("validate", base + ("validate", "--json")),
            ("inspect", base + ("inspect", "--json")),
            (
                "render",
                base
                + (
                    "render",
                    "--strict",
                    "--output",
                    job.output_path.name,
                ),
            ),
        )

    def _run_external(self, command: Sequence[str], *, cwd: Path, stage: str) -> Any:
        resolved_command = list(command)
        # On Windows, ``npx`` may resolve to a PowerShell shim that Python's
        # CreateProcess cannot launch directly.  Keep the public command
        # contract as npx, but resolve only the real default subprocess path
        # to the adjacent .cmd launcher.  Injected mock runners retain the
        # stable, platform-neutral command for deterministic unit tests.
        if self._uses_default_runner and resolved_command:
            executable_name = Path(resolved_command[0]).name.lower()
            if executable_name in {"npx", "npx.exe", "npx.cmd", "npx.ps1"}:
                resolved_command[0] = shutil.which("npx.cmd") or shutil.which("npx") or resolved_command[0]
        kwargs: dict[str, Any] = {
            "capture_output": True,
            "check": False,
            "cwd": cwd,
            "env": _offline_process_env(),
            "text": True,
        }
        if self.timeout_seconds is not None:
            kwargs["timeout"] = self.timeout_seconds
        try:
            return self._runner(resolved_command, **kwargs)
        except FileNotFoundError as exc:
            raise self._error(
                MotionRenderErrorCode.RENDERER_MISSING,
                stage,
                "The local HyperFrames renderer is unavailable.",
                recoverable=False,
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise self._error(
                MotionRenderErrorCode.RENDER_FAILED if stage == "render" else MotionRenderErrorCode.VALIDATION_FAILED,
                stage,
                "The local HyperFrames command timed out.",
                recoverable=True,
                retryable=True,
            ) from exc
        except OSError as exc:
            raise self._error(
                MotionRenderErrorCode.RENDERER_MISSING,
                stage,
                "The local HyperFrames renderer could not be started.",
                recoverable=False,
            ) from exc

    def _probe_output(self, job: MotionRenderJob) -> dict[str, Any]:
        ffprobe = shutil.which(self.ffprobe_command)
        if not ffprobe:
            return {
                "available": False,
                "status": "UNAVAILABLE",
                "validated": False,
            }
        command = (
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            job.output_path.name,
        )
        result = self._run_external(command, cwd=job.job_dir, stage="ffprobe")
        if _returncode(result) != 0:
            raise self._error(
                MotionRenderErrorCode.FFPROBE_FAILED,
                "ffprobe",
                "ffprobe could not inspect the rendered MP4.",
                recoverable=False,
            )
        raw = getattr(result, "stdout", "")
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        try:
            payload = json.loads(str(raw or ""))
        except (TypeError, ValueError) as exc:
            raise self._error(
                MotionRenderErrorCode.FFPROBE_FAILED,
                "ffprobe",
                "ffprobe returned unreadable media metadata.",
                recoverable=False,
            ) from exc
        if not isinstance(payload, Mapping):
            raise self._error(
                MotionRenderErrorCode.FFPROBE_FAILED,
                "ffprobe",
                "ffprobe returned an invalid media metadata shape.",
                recoverable=False,
            )
        streams = payload.get("streams")
        if not isinstance(streams, list):
            streams = []
        video_stream = next(
            (item for item in streams if isinstance(item, Mapping) and item.get("codec_type") == "video"),
            None,
        )
        if not isinstance(video_stream, Mapping):
            raise self._error(
                MotionRenderErrorCode.FFPROBE_FAILED,
                "ffprobe",
                "ffprobe found no video stream in the rendered MP4.",
                recoverable=False,
            )
        width = _positive_int(video_stream.get("width"))
        height = _positive_int(video_stream.get("height"))
        fps_value = _parse_rate(video_stream.get("avg_frame_rate"))
        if fps_value is None:
            fps_value = _parse_rate(video_stream.get("r_frame_rate"))
        duration_value = _float_value(video_stream.get("duration"))
        format_payload = payload.get("format")
        if duration_value is None and isinstance(format_payload, Mapping):
            duration_value = _float_value(format_payload.get("duration"))
        expected_duration = job.duration_seconds
        valid = (
            width == job.width
            and height == job.height
            and fps_value is not None
            and abs(fps_value - job.fps) <= 0.01
            and duration_value is not None
            and abs(duration_value - expected_duration) <= 0.75
        )
        if not valid:
            raise self._error(
                MotionRenderErrorCode.FFPROBE_FAILED,
                "ffprobe",
                "ffprobe metadata does not match the requested render contract.",
                recoverable=False,
            )
        return {
            "available": True,
            "duration_seconds": duration_value,
            "fps": fps_value,
            "height": height,
            "status": "PASS",
            "validated": True,
            "width": width,
        }

    def _qa_metadata(
        self,
        job: MotionRenderJob,
        *,
        output_sha256: str,
        ffprobe: Mapping[str, Any],
        command_status: Mapping[str, str],
    ) -> dict[str, Any]:
        ffprobe_available = bool(ffprobe.get("available"))
        checks = [
            {
                "detail": "HyperFrames lint, validate, inspect, and render completed.",
                "id": "hyperframes_commands",
                "passed": all(command_status.get(item) == "PASS" for item in ("lint", "validate", "inspect", "render")),
            },
            {
                "detail": "Rendered MP4 exists and is non-empty.",
                "id": "artifact_exists_and_non_zero",
                "passed": job.output_path.is_file() and job.output_path.stat().st_size > 0,
            },
            {
                "detail": "Output extension is MP4.",
                "id": "artifact_format",
                "passed": job.output_path.suffix.lower() == ".mp4",
            },
            {
                "detail": "ffprobe is available and matched the requested dimensions, frame rate, and duration."
                if ffprobe_available
                else "ffprobe is unavailable; container-level media validation remains unverified.",
                "id": "ffprobe_validation",
                "passed": bool(ffprobe.get("validated")),
            },
        ]
        blocking = [item["id"] for item in checks if not item["passed"]]
        return {
            "artifact": {
                "duration_seconds": job.duration_seconds,
                "height": job.height,
                "mime": "video/mp4",
                "path": job.output_path.name,
                "sha256": output_sha256,
                "width": job.width,
            },
            "blocking_reasons": blocking,
            "checks": checks,
            "evidence_status": "LOCAL_VERIFIED" if ffprobe.get("validated") else "FFPROBE_REQUIRED",
            "ffprobe": dict(ffprobe),
            "fps": job.fps,
            "job_id": job.job_id,
            "preset": job.preset,
            "provider": self.provider_id,
            "schema_version": "phase2r.motion-video-qa.v1",
            "status": "PASS" if not blocking else "FAIL",
            "summary": f"{len(checks) - len(blocking)}/{len(checks)} motion video checks passed.",
        }

    def _provenance_metadata(
        self,
        job: MotionRenderJob,
        *,
        output_sha256: str,
        qa: Mapping[str, Any],
        command_status: Mapping[str, str],
    ) -> dict[str, Any]:
        return {
            "artifact_type": "video",
            "composition": {
                "path": job.composition_path.name,
                "sha256": job.composition_sha256,
            },
            "evidence_status": qa.get("evidence_status"),
            "input": {
                "mime": _source_mime(job.source_image_path),
                "path": job.source_image_path.name,
                "sha256": job.source_sha256,
                "source_type": "local_source_image",
            },
            "job": job.to_dict(),
            "output": {
                "duration_seconds": job.duration_seconds,
                "fps": job.fps,
                "height": job.height,
                "mime": "video/mp4",
                "path": job.output_path.name,
                "sha256": output_sha256,
                "width": job.width,
            },
            "preset": job.preset,
            "provider": self.provider_id,
            "qa": {
                "path": "video_qa.json",
                "status": qa.get("status"),
            },
            "renderer": {
                "commands": {
                    "inspect": command_status.get("inspect"),
                    "lint": command_status.get("lint"),
                    "render": command_status.get("render"),
                    "validate": command_status.get("validate"),
                },
                "network": "application_offline_by_pinned_npx_and_npm_offline",
                "os_network_isolation": "NOT_CLAIMED",
                "tool": "npx --offline --yes hyperframes@0.7.106",
                "version": HYPERFRAMES_VERSION,
            },
            "schema_version": "phase2r.motion-video-provenance.v1",
        }

    @staticmethod
    def _error(
        code: MotionRenderErrorCode,
        stage: str,
        message: str,
        *,
        recoverable: bool,
        retryable: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> MotionRenderError:
        return MotionRenderError(
            MotionRenderFailure(
                details=dict(details or {}),
                error_code=code,
                provider=PROVIDER_ID,
                recoverable=recoverable,
                retryable=retryable,
                sanitized_message=message,
                stage=stage,
            )
        )


def _returncode(result: Any) -> int:
    try:
        return int(getattr(result, "returncode", 1))
    except (TypeError, ValueError):
        return 1


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _float_value(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_rate(value: Any) -> float | None:
    if not isinstance(value, str):
        return _float_value(value)
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        numerator_value = _float_value(numerator)
        denominator_value = _float_value(denominator)
        if numerator_value is None or denominator_value in {None, 0}:
            return None
        return numerator_value / denominator_value
    return _float_value(value)


__all__ = [
    "DEFAULT_DURATION_SECONDS",
    "DEFAULT_FPS",
    "DEFAULT_HEIGHT",
    "DEFAULT_NPX_COMMAND",
    "DEFAULT_OUTPUT_NAME",
    "DEFAULT_TEMPLATE_PATH",
    "DEFAULT_WIDTH",
    "HYPERFRAMES_PROVIDER_ID",
    "MotionPreset",
    "MotionRenderArtifact",
    "MotionRenderError",
    "MotionRenderErrorCode",
    "MotionRenderFailure",
    "MotionRenderJob",
    "MotionRenderRequest",
    "MotionRenderResult",
    "MotionRenderVideoProvider",
    "MotionVideoArtifact",
    "PRESETS",
    "PROVIDER_ID",
    "SUPPORTED_PRESETS",
    "VideoRenderResult",
]
