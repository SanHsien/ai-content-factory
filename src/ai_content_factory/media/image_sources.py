"""Provider-neutral hero-image contracts and local image sources.

The module intentionally has no SDK, network, or provider-specific imports.
It is a small local boundary for three kinds of input:

* a human/ChatGPT handoff that drops a PNG or JPEG into an inbox;
* a deterministic synthetic image used by offline tests; and
* a future Codex-native materializer, which remains partial until a local
  image is explicitly supplied.

Image validation is deliberately performed from bytes with the Python
standard library. The validator checks the file, declared MIME type,
dimensions, and SHA-256 rather than trusting metadata alone.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import zlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8"
SUPPORTED_IMAGE_MIME_TYPES = frozenset({"image/png", "image/jpeg"})
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_IMAGE_SUFFIX_TO_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
_MIME_TO_SUFFIX = {"image/png": ".png", "image/jpeg": ".jpg"}
_JPEG_SOF_MARKERS = frozenset(
    {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
)
_JPEG_STANDALONE_MARKERS = frozenset(
    {0x01, 0xD8, 0xD9, *range(0xD0, 0xD8)}
)


class ImageProvenance(str, Enum):
    """The source/provenance labels allowed by the local contract."""

    CHATGPT_HANDOFF = "CHATGPT_HANDOFF"
    CODEX_NATIVE = "CODEX_NATIVE"
    SYNTHETIC = "SYNTHETIC"
    PRIVATE_OWNED = "PRIVATE_OWNED"


Provenance = ImageProvenance
ImageSourceProvenance = ImageProvenance
ArtifactProvenance = ImageProvenance


class MaterializationStatus(str, Enum):
    """Evidence status for an image source result."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


ImageSourceStatus = MaterializationStatus
ArtifactStatus = MaterializationStatus


class ImageContractError(ValueError):
    """Raised when a local image does not satisfy the image contract."""


class ImageValidationError(ImageContractError):
    """Raised when a file is missing, malformed, or fails an integrity check."""


class ImageSourceError(RuntimeError):
    """Raised when a source cannot complete a requested local operation."""


def _enum_value(value: Enum | str, enum_type: type[Enum], field_name: str) -> Enum:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(str(value))
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise ValueError(f"{field_name} must be one of: {allowed}") from exc


def _coerce_provenance(value: ImageProvenance | str) -> ImageProvenance:
    return _enum_value(value, ImageProvenance, "provenance")  # type: ignore[return-value]


def _coerce_status(value: MaterializationStatus | str) -> MaterializationStatus:
    return _enum_value(value, MaterializationStatus, "status")  # type: ignore[return-value]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_sha256(value: str, *, field_name: str = "sha256") -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ImageValidationError(
            f"{field_name} must be a 64-character hexadecimal SHA-256"
        )
    return value.lower()


def _coerce_dimensions(
    dimensions: Sequence[int] | Mapping[str, Any] | None,
    width: int | None,
    height: int | None,
) -> tuple[int | None, int | None]:
    resolved_width, resolved_height = width, height
    if dimensions is not None:
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
            raise ValueError(
                "dimensions must be a two-item sequence or a width/height mapping"
            )
        if (
            resolved_width is not None
            and dimension_width is not None
            and resolved_width != dimension_width
        ):
            raise ValueError("width and dimensions disagree")
        if (
            resolved_height is not None
            and dimension_height is not None
            and resolved_height != dimension_height
        ):
            raise ValueError("height and dimensions disagree")
        resolved_width = dimension_width if resolved_width is None else resolved_width
        resolved_height = dimension_height if resolved_height is None else resolved_height
    return resolved_width, resolved_height


def _safe_name(value: str, *, field_name: str) -> str:
    candidate = str(value).strip()
    if (
        not candidate
        or candidate in {".", ".."}
        or "/" in candidate
        or "\\" in candidate
        or Path(candidate).is_absolute()
        or Path(candidate).name != candidate
    ):
        raise ValueError(f"{field_name} must be a single safe local name")
    return candidate


def _safe_path_name(path: Path | None) -> str | None:
    return path.name if isinstance(path, Path) else None


def _parse_png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < len(PNG_SIGNATURE) + 12 or not data.startswith(PNG_SIGNATURE):
        raise ImageValidationError("PNG signature is missing")

    offset = len(PNG_SIGNATURE)
    dimensions: tuple[int, int] | None = None
    saw_iend = False
    first_chunk = True
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_start = offset + 8
        chunk_end = chunk_start + length
        crc_end = chunk_end + 4
        if chunk_end > len(data) or crc_end > len(data):
            raise ImageValidationError("PNG chunk extends beyond the file")
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[chunk_start:chunk_end]
        declared_crc = struct.unpack(">I", data[chunk_end:crc_end])[0]
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if declared_crc != actual_crc:
            raise ImageValidationError("PNG chunk CRC is invalid")

        if first_chunk and chunk_type != b"IHDR":
            raise ImageValidationError("PNG must begin with an IHDR chunk")
        first_chunk = False
        if chunk_type == b"IHDR":
            if dimensions is not None or length != 13:
                raise ImageValidationError("PNG IHDR chunk is invalid")
            width, height = struct.unpack(">II", chunk_data[:8])
            if width <= 0 or height <= 0:
                raise ImageValidationError("PNG dimensions must be positive")
            dimensions = (width, height)
        elif chunk_type == b"IEND":
            if length != 0:
                raise ImageValidationError("PNG IEND chunk is invalid")
            saw_iend = True
            offset = crc_end
            break
        offset = crc_end

    if dimensions is None:
        raise ImageValidationError("PNG IHDR dimensions are missing")
    if not saw_iend:
        raise ImageValidationError("PNG IEND chunk is missing")
    if offset != len(data):
        raise ImageValidationError("PNG contains bytes after IEND")
    return dimensions


def _parse_jpeg_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 4 or not data.startswith(JPEG_SIGNATURE):
        raise ImageValidationError("JPEG signature is missing")
    if not data.endswith(b"\xff\xd9"):
        raise ImageValidationError("JPEG end marker is missing")

    index = 2
    dimensions: tuple[int, int] | None = None
    while index < len(data):
        if data[index] != 0xFF:
            raise ImageValidationError("JPEG marker is malformed")
        while index < len(data) and data[index] == 0xFF:
            index += 1
        if index >= len(data):
            break
        marker = data[index]
        index += 1
        if marker == 0x00:
            raise ImageValidationError("JPEG contains an invalid marker")
        if marker == 0xDA:
            break
        if marker == 0xD9:
            break
        if marker in _JPEG_STANDALONE_MARKERS:
            continue
        if index + 2 > len(data):
            raise ImageValidationError("JPEG segment length is missing")
        segment_length = struct.unpack(">H", data[index : index + 2])[0]
        if segment_length < 2 or index + segment_length > len(data):
            raise ImageValidationError("JPEG segment length is invalid")
        segment = data[index + 2 : index + segment_length]
        if marker in _JPEG_SOF_MARKERS:
            if len(segment) < 5:
                raise ImageValidationError("JPEG frame header is invalid")
            height, width = struct.unpack(">HH", segment[1:5])
            if width <= 0 or height <= 0:
                raise ImageValidationError("JPEG dimensions must be positive")
            dimensions = (width, height)
        index += segment_length

    if dimensions is None:
        raise ImageValidationError("JPEG frame dimensions are missing")
    return dimensions


@dataclass(frozen=True, slots=True)
class ImageFileMetadata:
    """Verified metadata extracted from a local PNG or JPEG file."""

    mime: str
    width: int
    height: int
    sha256: str

    @property
    def mime_type(self) -> str:
        return self.mime

    @property
    def dimensions(self) -> tuple[int, int]:
        return self.width, self.height

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimensions": {"height": self.height, "width": self.width},
            "mime": self.mime,
            "sha256": self.sha256,
        }


def _inspect_image_bytes(data: bytes) -> ImageFileMetadata:
    if data.startswith(PNG_SIGNATURE):
        width, height = _parse_png_dimensions(data)
        mime = "image/png"
    elif data.startswith(JPEG_SIGNATURE):
        width, height = _parse_jpeg_dimensions(data)
        mime = "image/jpeg"
    else:
        raise ImageValidationError("only PNG and JPEG image files are supported")
    return ImageFileMetadata(mime=mime, width=width, height=height, sha256=_sha256(data))


def validate_image_file(
    path: str | Path,
    *,
    expected_sha256: str | None = None,
    expected_mime: str | None = None,
    expected_mime_type: str | None = None,
    expected_width: int | None = None,
    expected_height: int | None = None,
    expected_dimensions: Sequence[int] | Mapping[str, Any] | None = None,
) -> ImageFileMetadata:
    """Read and validate a local PNG/JPEG without optional dependencies."""

    file_path = Path(path)
    if not file_path.is_file():
        raise ImageValidationError("image file is missing")
    try:
        data = file_path.read_bytes()
    except OSError as exc:
        raise ImageValidationError("image file could not be read") from exc
    metadata = _inspect_image_bytes(data)

    declared_mime = expected_mime if expected_mime is not None else expected_mime_type
    if declared_mime is not None and declared_mime != metadata.mime:
        raise ImageValidationError("declared MIME does not match image bytes")
    if declared_mime is not None and declared_mime not in SUPPORTED_IMAGE_MIME_TYPES:
        raise ImageValidationError("MIME must be image/png or image/jpeg")
    suffix_mime = _IMAGE_SUFFIX_TO_MIME.get(file_path.suffix.lower())
    if suffix_mime is not None and suffix_mime != metadata.mime:
        raise ImageValidationError("file extension does not match image bytes")

    if expected_sha256 is not None:
        normalized_expected = _validate_sha256(
            expected_sha256, field_name="expected_sha256"
        )
        if metadata.sha256 != normalized_expected:
            raise ImageValidationError("SHA-256 does not match image bytes")
    resolved_width, resolved_height = _coerce_dimensions(
        expected_dimensions, expected_width, expected_height
    )
    if resolved_width is not None and metadata.width != resolved_width:
        raise ImageValidationError("image width does not match the contract")
    if resolved_height is not None and metadata.height != resolved_height:
        raise ImageValidationError("image height does not match the contract")
    return metadata


inspect_image_file = validate_image_file
read_image_metadata = validate_image_file


@dataclass(frozen=True, slots=True, init=False)
class HeroImageArtifact:
    """A locally materialized, integrity-checked hero image."""

    artifact_id: str
    path: Path
    sha256: str
    mime: str
    width: int
    height: int
    provenance: ImageProvenance
    status: MaterializationStatus
    source: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        artifact_id: str | None = None,
        path: str | Path | None = None,
        sha256: str | None = None,
        mime: str | None = None,
        width: int | None = None,
        height: int | None = None,
        provenance: ImageProvenance | str = ImageProvenance.SYNTHETIC,
        *,
        mime_type: str | None = None,
        dimensions: Sequence[int] | Mapping[str, Any] | None = None,
        file_path: str | Path | None = None,
        local_path: str | Path | None = None,
        status: MaterializationStatus | str = MaterializationStatus.COMPLETE,
        source: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if path is None:
            path = file_path if file_path is not None else local_path
        resolved_width, resolved_height = _coerce_dimensions(
            dimensions, width, height
        )
        declared_mime = mime if mime is not None else mime_type
        if mime is not None and mime_type is not None and mime != mime_type:
            raise ValueError("mime and mime_type disagree")
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
        object.__setattr__(self, "provenance", _coerce_provenance(provenance))
        object.__setattr__(self, "status", _coerce_status(status))
        object.__setattr__(
            self,
            "source",
            self.provenance.value if source is None else str(source),
        )
        object.__setattr__(self, "metadata", dict(metadata or {}))

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        artifact_id: str | None = None,
        provenance: ImageProvenance | str = ImageProvenance.SYNTHETIC,
        expected_sha256: str | None = None,
        expected_mime: str | None = None,
        expected_width: int | None = None,
        expected_height: int | None = None,
        source: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "HeroImageArtifact":
        file_path = Path(path)
        inspected = validate_image_file(
            file_path,
            expected_sha256=expected_sha256,
            expected_mime=expected_mime,
            expected_width=expected_width,
            expected_height=expected_height,
        )
        artifact = cls(
            artifact_id=artifact_id or file_path.stem,
            path=file_path,
            sha256=inspected.sha256,
            mime=inspected.mime,
            width=inspected.width,
            height=inspected.height,
            provenance=provenance,
            status=MaterializationStatus.COMPLETE,
            source=source,
            metadata=metadata,
        )
        artifact.validate()
        return artifact

    def validate(self) -> None:
        if not self.artifact_id.strip():
            raise ImageValidationError("artifact_id is required")
        if not isinstance(self.path, Path) or not self.path.is_file():
            raise ImageValidationError("image file is missing")
        if self.mime not in SUPPORTED_IMAGE_MIME_TYPES:
            raise ImageValidationError("MIME must be image/png or image/jpeg")
        if (
            isinstance(self.width, bool)
            or not isinstance(self.width, int)
            or self.width <= 0
            or isinstance(self.height, bool)
            or not isinstance(self.height, int)
            or self.height <= 0
        ):
            raise ImageValidationError("image dimensions must be positive integers")
        normalized_sha = _validate_sha256(self.sha256)
        inspected = validate_image_file(
            self.path,
            expected_sha256=normalized_sha,
            expected_mime=self.mime,
            expected_width=self.width,
            expected_height=self.height,
        )
        if inspected.sha256 != normalized_sha:
            raise ImageValidationError("SHA-256 does not match image bytes")

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
    def file_path(self) -> Path:
        return self.path

    @property
    def local_path(self) -> Path:
        return self.path

    @property
    def artifact_sha256(self) -> str:
        return self.sha256

    @property
    def source_type(self) -> ImageProvenance:
        return self.provenance

    def to_dict(self, *, include_path: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "artifact_id": self.artifact_id,
            "artifact_type": "hero_image",
            "dimensions": {"height": self.height, "width": self.width},
            "mime": self.mime,
            "provenance": self.provenance.value,
            "sha256": self.sha256,
            "status": self.status.value,
        }
        if include_path:
            result["path"] = self.path.name
        if self.source:
            result["source"] = self.source
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result

    as_dict = to_dict

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        path: str | Path | None = None,
    ) -> "HeroImageArtifact":
        if not isinstance(value, Mapping):
            raise TypeError("artifact manifest must be a mapping")
        dimensions = value.get("dimensions")
        artifact_path = path if path is not None else value.get("path")
        return cls(
            artifact_id=value.get("artifact_id"),
            path=artifact_path,
            sha256=value.get("sha256"),
            mime=value.get("mime", value.get("mime_type")),
            dimensions=dimensions,
            provenance=value.get("provenance", ImageProvenance.SYNTHETIC.value),
            status=value.get("status", MaterializationStatus.COMPLETE.value),
            source=value.get("source"),
            metadata=value.get("metadata"),
        )


@dataclass(frozen=True, slots=True)
class ImageSourceResult:
    """Result envelope that makes partial/handoff states explicit."""

    status: MaterializationStatus
    artifact: HeroImageArtifact | None = None
    message: str = ""
    request_path: Path | None = None
    manifest_path: Path | None = None
    provenance: ImageProvenance | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", _coerce_status(self.status))
        if self.provenance is not None:
            object.__setattr__(
                self, "provenance", _coerce_provenance(self.provenance)
            )

    @property
    def complete(self) -> bool:
        return (
            self.status is MaterializationStatus.COMPLETE
            and self.artifact is not None
        )

    @property
    def partial(self) -> bool:
        return self.status is MaterializationStatus.PARTIAL

    @property
    def not_implemented(self) -> bool:
        return self.status is MaterializationStatus.NOT_IMPLEMENTED or (
            self.status is MaterializationStatus.PARTIAL
            and "not implemented" in self.message.lower()
        )

    def __getattr__(self, name: str) -> Any:
        artifact = object.__getattribute__(self, "artifact")
        if artifact is not None and hasattr(artifact, name):
            return getattr(artifact, name)
        raise AttributeError(name)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "message": self.message,
            "provenance": self.provenance.value if self.provenance else None,
            "status": self.status.value,
            "artifact": self.artifact.to_dict() if self.artifact else None,
        }
        if self.request_path is not None:
            result["request_file"] = _safe_path_name(self.request_path)
        if self.manifest_path is not None:
            result["manifest_file"] = _safe_path_name(self.manifest_path)
        return result


class ImageSource(Protocol):
    provenance: ImageProvenance

    def materialize(
        self,
        output_dir: str | Path | None = None,
        *,
        artifact_id: str = "hero-image",
    ) -> ImageSourceResult: ...


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_handoff_request(
    output_dir: Path,
    *,
    prompt: str,
    status: MaterializationStatus,
    message: str,
) -> Path:
    request_path = output_dir / "image_request.md"
    request_path.write_text(
        "\n".join(
            [
                "# Hero image handoff request",
                "",
                f"Status: {status.value}",
                "Provenance: CHATGPT_HANDOFF",
                "",
                "This is a local handoff record. No API request or network call is made.",
                "",
                "## Prompt",
                "",
                prompt.strip()
                or "Provide a neutral hero image for the local content pipeline.",
                "",
                "## Local completion",
                "",
                "Place one PNG or JPEG in the configured inbox, then run the local importer.",
                "The importer will verify the file bytes, MIME type, dimensions, and SHA-256.",
                "",
                f"Note: {message}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return request_path


def _manifest_value(
    result: ImageSourceResult,
    *,
    source_name: str,
    request_path: Path | None = None,
    input_name: str | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": "1.0",
        "source": source_name,
        "provenance": result.provenance.value if result.provenance else None,
        "status": result.status.value,
        "message": result.message,
        "artifact": result.artifact.to_dict() if result.artifact else None,
        "artifacts": [result.artifact.to_dict()] if result.artifact else [],
    }
    if request_path is not None:
        value["request_file"] = request_path.name
    if input_name is not None:
        value["input_file"] = Path(input_name).name
    return value


def _write_manifest(
    output_dir: Path,
    result: ImageSourceResult,
    *,
    source_name: str,
    request_path: Path | None = None,
    input_name: str | None = None,
) -> Path:
    manifest_path = output_dir / "image_manifest.json"
    _write_json(
        manifest_path,
        _manifest_value(
            result,
            source_name=source_name,
            request_path=request_path,
            input_name=input_name,
        ),
    )
    return manifest_path


def _find_inbox_image(inbox_dir: Path) -> Path | None:
    if inbox_dir.is_file():
        return inbox_dir
    if not inbox_dir.is_dir():
        return None
    candidates = sorted(
        (
            item
            for item in inbox_dir.iterdir()
            if item.is_file() and item.suffix.lower() in _IMAGE_SUFFIX_TO_MIME
        ),
        key=lambda item: item.name.casefold(),
    )
    return candidates[0] if candidates else None


def _destination_for(
    output_dir: Path,
    artifact_id: str,
    mime: str,
) -> Path:
    safe_id = _safe_name(artifact_id, field_name="artifact_id")
    return output_dir / f"{safe_id}{_MIME_TO_SUFFIX[mime]}"


def _copy_local_image(source: Path, destination: Path) -> None:
    try:
        source_resolved = source.resolve()
        destination_resolved = destination.resolve()
        if source_resolved != destination_resolved:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
    except OSError as exc:
        raise ImageSourceError("local image could not be copied") from exc


class ChatGPTHandoffImageSource:
    """Import a human-provided PNG/JPEG from a local inbox.

    The class writes a request and manifest as local evidence. It never
    contacts ChatGPT or any other service.
    """

    provenance = ImageProvenance.CHATGPT_HANDOFF

    def __init__(
        self,
        inbox_dir: str | Path | None = None,
        *,
        output_dir: str | Path | None = None,
        prompt: str = "Provide a neutral hero image for the local content pipeline.",
    ) -> None:
        self.inbox_dir = Path(inbox_dir) if inbox_dir is not None else None
        self.output_dir = Path(output_dir) if output_dir is not None else None
        self.prompt = prompt

    def materialize(
        self,
        output_dir: str | Path | None = None,
        *,
        inbox_dir: str | Path | None = None,
        image_path: str | Path | None = None,
        artifact_id: str = "hero-image",
        prompt: str | None = None,
    ) -> ImageSourceResult:
        resolved_output = (
            Path(output_dir) if output_dir is not None else self.output_dir
        )
        resolved_inbox = (
            Path(inbox_dir) if inbox_dir is not None else self.inbox_dir
        )
        effective_prompt = self.prompt if prompt is None else prompt
        if resolved_output is None:
            return ImageSourceResult(
                status=MaterializationStatus.PARTIAL,
                message="A local output directory is required for the handoff package.",
                provenance=self.provenance,
            )
        resolved_output.mkdir(parents=True, exist_ok=True)
        request_path = _write_handoff_request(
            resolved_output,
            prompt=effective_prompt,
            status=MaterializationStatus.PARTIAL,
            message="Waiting for a validated local image.",
        )
        candidate = (
            Path(image_path)
            if image_path is not None
            else (
                _find_inbox_image(resolved_inbox)
                if resolved_inbox is not None
                else None
            )
        )
        if candidate is None:
            result = ImageSourceResult(
                status=MaterializationStatus.PARTIAL,
                message="No PNG or JPEG was found in the local handoff inbox.",
                request_path=request_path,
                provenance=self.provenance,
            )
            manifest_path = _write_manifest(
                resolved_output,
                result,
                source_name=self.__class__.__name__,
                request_path=request_path,
            )
            return ImageSourceResult(
                status=result.status,
                artifact=result.artifact,
                message=result.message,
                request_path=request_path,
                manifest_path=manifest_path,
                provenance=result.provenance,
            )

        try:
            inspected = validate_image_file(candidate)
            destination = _destination_for(resolved_output, artifact_id, inspected.mime)
            _copy_local_image(candidate, destination)
            artifact = HeroImageArtifact.from_file(
                destination,
                artifact_id=artifact_id,
                provenance=self.provenance,
                source="chatgpt-handoff",
            )
        except (ImageContractError, OSError) as exc:
            result = ImageSourceResult(
                status=MaterializationStatus.PARTIAL,
                message="The handoff image failed local PNG/JPEG validation.",
                request_path=request_path,
                provenance=self.provenance,
            )
            manifest_path = _write_manifest(
                resolved_output,
                result,
                source_name=self.__class__.__name__,
                request_path=request_path,
                input_name=candidate.name,
            )
            return ImageSourceResult(
                status=result.status,
                artifact=None,
                message=f"{result.message} ({exc.__class__.__name__})",
                request_path=request_path,
                manifest_path=manifest_path,
                provenance=self.provenance,
            )

        result = ImageSourceResult(
            status=MaterializationStatus.COMPLETE,
            artifact=artifact,
            message="A local handoff image was imported and validated.",
            request_path=request_path,
            provenance=self.provenance,
        )
        request_path = _write_handoff_request(
            resolved_output,
            prompt=effective_prompt,
            status=result.status,
            message=result.message,
        )
        manifest_path = _write_manifest(
            resolved_output,
            result,
            source_name=self.__class__.__name__,
            request_path=request_path,
            input_name=candidate.name,
        )
        return ImageSourceResult(
            status=result.status,
            artifact=result.artifact,
            message=result.message,
            request_path=request_path,
            manifest_path=manifest_path,
            provenance=self.provenance,
        )

    def import_from_inbox(
        self,
        inbox_dir: str | Path | None = None,
        output_dir: str | Path | None = None,
        **kwargs: Any,
    ) -> ImageSourceResult:
        return self.materialize(
            output_dir=output_dir,
            inbox_dir=inbox_dir,
            **kwargs,
        )

    import_image = import_from_inbox
    resolve = materialize
    acquire = materialize
    load = materialize


class SyntheticImageSource:
    """Materialize a deterministic, neutral PNG using only the stdlib."""

    provenance = ImageProvenance.SYNTHETIC

    def __init__(
        self,
        output_dir: str | Path | None = None,
        *,
        width: int = 64,
        height: int = 64,
        seed: str = "synthetic-hero",
    ) -> None:
        self.output_dir = Path(output_dir) if output_dir is not None else None
        self.width = width
        self.height = height
        self.seed = str(seed)

    @staticmethod
    def _png_chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return (
            struct.pack(">I", len(data))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    def _png_bytes(self, *, artifact_id: str, width: int, height: int) -> bytes:
        digest = hashlib.sha256(
            f"{self.seed}\x1f{artifact_id}\x1f{width}x{height}".encode("utf-8")
        ).digest()
        rgba = bytes((digest[0], digest[1], digest[2], 255))
        row = b"\x00" + rgba * width
        raw = row * height
        ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
        return (
            PNG_SIGNATURE
            + self._png_chunk(b"IHDR", ihdr)
            + self._png_chunk(b"IDAT", zlib.compress(raw, 9))
            + self._png_chunk(b"IEND", b"")
        )

    def materialize(
        self,
        output_dir: str | Path | None = None,
        *,
        output_path: str | Path | None = None,
        artifact_id: str = "synthetic-hero",
        width: int | None = None,
        height: int | None = None,
        dimensions: Sequence[int] | Mapping[str, Any] | None = None,
        seed: str | None = None,
    ) -> ImageSourceResult:
        resolved_width, resolved_height = _coerce_dimensions(
            dimensions,
            self.width if width is None else width,
            self.height if height is None else height,
        )
        if (
            isinstance(resolved_width, bool)
            or not isinstance(resolved_width, int)
            or resolved_width <= 0
            or isinstance(resolved_height, bool)
            or not isinstance(resolved_height, int)
            or resolved_height <= 0
        ):
            raise ValueError("synthetic image dimensions must be positive integers")

        if output_path is not None:
            destination = Path(output_path)
        else:
            resolved_output = (
                Path(output_dir) if output_dir is not None else self.output_dir
            )
            if resolved_output is None:
                return ImageSourceResult(
                    status=MaterializationStatus.PARTIAL,
                    message="A local output directory is required for synthetic materialization.",
                    provenance=self.provenance,
                )
            destination = _destination_for(
                resolved_output, artifact_id, "image/png"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        original_seed = self.seed
        if seed is not None:
            self.seed = str(seed)
        try:
            destination.write_bytes(
                self._png_bytes(
                    artifact_id=artifact_id,
                    width=resolved_width,
                    height=resolved_height,
                )
            )
        finally:
            self.seed = original_seed
        artifact = HeroImageArtifact.from_file(
            destination,
            artifact_id=artifact_id,
            provenance=self.provenance,
            source="synthetic",
        )
        return ImageSourceResult(
            status=MaterializationStatus.COMPLETE,
            artifact=artifact,
            message="A deterministic synthetic PNG was materialized.",
            provenance=self.provenance,
        )

    create = materialize
    generate = materialize
    resolve = materialize
    acquire = materialize


class CodexNativeImageSource:
    """Local boundary for a future Codex-native image materializer.

    This class never invents an image. Until a caller supplies local bytes or
    a local path, the result is explicitly PARTIAL and marked not implemented
    by the result envelope.
    """

    provenance = ImageProvenance.CODEX_NATIVE

    def __init__(
        self,
        materialized_path: str | Path | None = None,
        *,
        output_dir: str | Path | None = None,
    ) -> None:
        self.materialized_path = (
            Path(materialized_path) if materialized_path is not None else None
        )
        self.output_dir = Path(output_dir) if output_dir is not None else None

    def materialize(
        self,
        output_dir: str | Path | None = None,
        *,
        materialized_path: str | Path | None = None,
        local_path: str | Path | None = None,
        path: str | Path | None = None,
        materialized: str | Path | bytes | bytearray | None = None,
        materialized_bytes: bytes | bytearray | None = None,
        output_path: str | Path | None = None,
        artifact_id: str = "hero-image",
        expected_mime: str | None = None,
        expected_width: int | None = None,
        expected_height: int | None = None,
        dimensions: Sequence[int] | Mapping[str, Any] | None = None,
    ) -> ImageSourceResult:
        resolved_output = (
            Path(output_dir) if output_dir is not None else self.output_dir
        )
        local_materialization: str | Path | bytes | bytearray | None = (
            materialized
            if materialized is not None
            else materialized_bytes
            if materialized_bytes is not None
            else materialized_path
            if materialized_path is not None
            else local_path
            if local_path is not None
            else path
            if path is not None
            else self.materialized_path
        )
        if local_materialization is None:
            result = ImageSourceResult(
                status=MaterializationStatus.PARTIAL,
                message=(
                    "Codex-native local image materialization is not implemented "
                    "until a local PNG or JPEG is supplied."
                ),
                provenance=self.provenance,
            )
            if resolved_output is None:
                return result
            resolved_output.mkdir(parents=True, exist_ok=True)
            manifest_path = _write_manifest(
                resolved_output,
                result,
                source_name=self.__class__.__name__,
            )
            return ImageSourceResult(
                status=result.status,
                artifact=None,
                message=result.message,
                manifest_path=manifest_path,
                provenance=self.provenance,
            )

        if isinstance(local_materialization, (bytes, bytearray)):
            if output_path is not None:
                destination = Path(output_path)
            elif resolved_output is not None:
                destination = _destination_for(
                    resolved_output, artifact_id, "image/png"
                )
            else:
                return ImageSourceResult(
                    status=MaterializationStatus.PARTIAL,
                    message="Local image bytes require an output path.",
                    provenance=self.provenance,
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(bytes(local_materialization))
        else:
            source_path = Path(local_materialization)
            inspected = validate_image_file(source_path)
            if output_path is not None:
                destination = Path(output_path)
            elif resolved_output is not None:
                destination = _destination_for(
                    resolved_output, artifact_id, inspected.mime
                )
            else:
                destination = source_path
            _copy_local_image(source_path, destination)

        resolved_dimensions = _coerce_dimensions(
            dimensions, expected_width, expected_height
        )
        artifact = HeroImageArtifact.from_file(
            destination,
            artifact_id=artifact_id,
            provenance=self.provenance,
            expected_mime=expected_mime,
            expected_width=resolved_dimensions[0],
            expected_height=resolved_dimensions[1],
            source="codex-native",
        )
        result = ImageSourceResult(
            status=MaterializationStatus.COMPLETE,
            artifact=artifact,
            message="A locally supplied Codex-native image was validated.",
            provenance=self.provenance,
        )
        if resolved_output is not None:
            resolved_output.mkdir(parents=True, exist_ok=True)
            manifest_path = _write_manifest(
                resolved_output,
                result,
                source_name=self.__class__.__name__,
            )
            return ImageSourceResult(
                status=result.status,
                artifact=result.artifact,
                message=result.message,
                manifest_path=manifest_path,
                provenance=self.provenance,
            )
        return result

    create = materialize
    resolve = materialize
    acquire = materialize
    load = materialize


__all__ = [
    "ArtifactProvenance",
    "ArtifactStatus",
    "CHATGPT_HANDOFF",
    "ChatGPTHandoffImageSource",
    "CodexNativeImageSource",
    "CODEX_NATIVE",
    "HeroImageArtifact",
    "ImageContractError",
    "ImageFileMetadata",
    "ImageProvenance",
    "ImageSource",
    "ImageSourceError",
    "ImageSourceProvenance",
    "ImageSourceResult",
    "ImageSourceStatus",
    "ImageValidationError",
    "JPEG_SIGNATURE",
    "MaterializationStatus",
    "PRIVATE_OWNED",
    "Provenance",
    "PNG_SIGNATURE",
    "SYNTHETIC",
    "SUPPORTED_IMAGE_MIME_TYPES",
    "SyntheticImageSource",
    "inspect_image_file",
    "read_image_metadata",
    "validate_image_file",
]


CHATGPT_HANDOFF = ImageProvenance.CHATGPT_HANDOFF.value
CODEX_NATIVE = ImageProvenance.CODEX_NATIVE.value
SYNTHETIC = ImageProvenance.SYNTHETIC.value
PRIVATE_OWNED = ImageProvenance.PRIVATE_OWNED.value
