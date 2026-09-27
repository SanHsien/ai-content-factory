"""Provider-neutral contracts for durable image submission and materialization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
from pathlib import Path
import time
from typing import Callable, Mapping, Any

from .image_sources import HeroImageArtifact, ImageProvenance


class ImageJobState(StrEnum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    WAITING = "WAITING"
    MATERIALIZING = "MATERIALIZING"
    VERIFYING = "VERIFYING"
    READY = "READY"
    DEFINITE_FAILURE = "DEFINITE_FAILURE"
    AMBIGUOUS = "AMBIGUOUS"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass(frozen=True, slots=True)
class SubmissionReceipt:
    job_id: str
    content_id: str
    provider: str
    submission_timestamp: str
    provider_submission_count: int
    prompt_hash: str
    expected_aspect_ratio: str | None
    expected_asset_type: str
    expected_local_output_contract: str
    reconciliation_state: ImageJobState

    @classmethod
    def create(
        cls,
        *,
        job_id: str,
        content_id: str,
        provider: str,
        submission_timestamp: str,
        prompt: str,
        expected_local_output_contract: str | Path,
        expected_aspect_ratio: str | None = None,
        expected_asset_type: str = "image",
        provider_submission_count: int = 1,
        reconciliation_state: ImageJobState = ImageJobState.SUBMITTED,
    ) -> "SubmissionReceipt":
        if not job_id.strip() or not content_id.strip() or not provider.strip():
            raise ValueError("job_id, content_id and provider are required")
        if provider_submission_count != 1:
            raise ValueError("provider_submission_count must remain exactly one")
        output = Path(expected_local_output_contract).resolve()
        return cls(
            job_id=job_id,
            content_id=content_id,
            provider=provider,
            submission_timestamp=submission_timestamp,
            provider_submission_count=1,
            prompt_hash=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            expected_aspect_ratio=expected_aspect_ratio,
            expected_asset_type=expected_asset_type,
            expected_local_output_contract=str(output),
            reconciliation_state=ImageJobState(reconciliation_state),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "IMAGE_SUBMISSION_RECEIPT_V1",
            "job_id": self.job_id,
            "content_id": self.content_id,
            "provider": self.provider,
            "submission_timestamp": self.submission_timestamp,
            "provider_submission_count": self.provider_submission_count,
            "prompt_hash": self.prompt_hash,
            "expected_aspect_ratio": self.expected_aspect_ratio,
            "expected_asset_type": self.expected_asset_type,
            "expected_local_output_contract": self.expected_local_output_contract,
            "reconciliation_state": self.reconciliation_state.value,
        }

    def persist(self, path: str | Path) -> Path:
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f"{target.name}.tmp")
        temporary.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        return target


@dataclass(frozen=True, slots=True)
class VerifiedImageArtifact:
    artifact_path: Path
    sha256: str
    width: int
    height: int
    mime: str
    provider: str
    job_id: str
    content_id: str
    provenance: Mapping[str, Any]

    @classmethod
    def from_stable_file(
        cls,
        path: str | Path,
        *,
        provider: str,
        job_id: str,
        content_id: str,
        provenance: Mapping[str, Any] | None = None,
    ) -> "VerifiedImageArtifact":
        image = HeroImageArtifact.from_file(
            path,
            artifact_id=f"{job_id}-verified-image",
            provenance=ImageProvenance.SYNTHETIC,
            source=provider,
        )
        return cls(
            artifact_path=image.path.resolve(),
            sha256=image.sha256,
            width=image.width,
            height=image.height,
            mime=image.mime,
            provider=provider,
            job_id=job_id,
            content_id=content_id,
            provenance={
                **dict(provenance or {}),
                "verification": "LOCAL_DECODE_MIME_DIMENSIONS_SHA256_FILE_STABILITY",
            },
        )


def wait_for_stable_file(
    path: str | Path,
    *,
    observation_window_seconds: float,
    interval_seconds: float = 1.0,
    stable_observations: int = 3,
    minimum_bytes: int = 1024,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> bool:
    target = Path(path).resolve()
    deadline = monotonic() + max(0.0, observation_window_seconds)
    previous_size: int | None = None
    stable_count = 0
    while True:
        try:
            size = target.stat().st_size if target.is_file() else 0
        except OSError:
            size = 0
        if size >= max(1, minimum_bytes):
            stable_count = stable_count + 1 if size == previous_size else 1
            previous_size = size
            if stable_count >= max(2, stable_observations):
                return True
        else:
            previous_size = size
            stable_count = 0
        if monotonic() >= deadline:
            return False
        sleep(min(max(0.001, interval_seconds), max(0.001, deadline - monotonic())))


def materialize_verified_image(
    receipt: SubmissionReceipt,
    *,
    observation_window_seconds: float,
    interval_seconds: float = 1.0,
    stable_observations: int = 3,
    minimum_bytes: int = 1024,
) -> VerifiedImageArtifact | None:
    if receipt.provider_submission_count != 1:
        raise ValueError("provider submission identity is not durable")
    if not wait_for_stable_file(
        receipt.expected_local_output_contract,
        observation_window_seconds=observation_window_seconds,
        interval_seconds=interval_seconds,
        stable_observations=stable_observations,
        minimum_bytes=minimum_bytes,
    ):
        return None
    return VerifiedImageArtifact.from_stable_file(
        receipt.expected_local_output_contract,
        provider=receipt.provider,
        job_id=receipt.job_id,
        content_id=receipt.content_id,
        provenance={"prompt_hash": receipt.prompt_hash},
    )
