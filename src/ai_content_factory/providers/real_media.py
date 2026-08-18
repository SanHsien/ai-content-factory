"""Provider-neutral contracts for opt-in real media generation.

This module is deliberately separate from the phase-one placeholder contracts.
Importing it performs no network access and reads no credentials.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from ai_content_factory.core.hashing import canonical_json_hash, sha256_hex


class UsageRightsStatus(str, Enum):
    OWNED = "OWNED"
    LICENSED = "LICENSED"
    SYNTHETIC = "SYNTHETIC"
    UNKNOWN = "UNKNOWN"


class ReviewState(str, Enum):
    GENERATED = "GENERATED"
    QA_PENDING = "QA_PENDING"
    QA_PASSED = "QA_PASSED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ProviderErrorCode(str, Enum):
    AUTH_MISSING = "AUTH_MISSING"
    AUTH_REJECTED = "AUTH_REJECTED"
    NETWORK_OPT_IN_REQUIRED = "NETWORK_OPT_IN_REQUIRED"
    LIVE_CALL_CONFIRMATION_REQUIRED = "LIVE_CALL_CONFIRMATION_REQUIRED"
    LIVE_CALL_PLAN_MISSING = "LIVE_CALL_PLAN_MISSING"
    RATE_LIMITED = "RATE_LIMITED"
    COST_LIMIT_EXCEEDED = "COST_LIMIT_EXCEEDED"
    INVALID_INPUT = "INVALID_INPUT"
    UNSUPPORTED_MEDIA = "UNSUPPORTED_MEDIA"
    PROVIDER_REJECTED = "PROVIDER_REJECTED"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_TRANSIENT_FAILURE = "PROVIDER_TRANSIENT_FAILURE"
    OUTPUT_DOWNLOAD_FAILED = "OUTPUT_DOWNLOAD_FAILED"
    OUTPUT_INTEGRITY_FAILED = "OUTPUT_INTEGRITY_FAILED"
    PROVENANCE_INCOMPLETE = "PROVENANCE_INCOMPLETE"
    OPTIONAL_DEPENDENCY_MISSING = "OPTIONAL_DEPENDENCY_MISSING"


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    stage: str
    provider: str
    error_code: ProviderErrorCode
    sanitized_message: str
    recoverable: bool
    retryable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code.value,
            "provider": self.provider,
            "recoverable": self.recoverable,
            "retryable": self.retryable,
            "sanitized_message": self.sanitized_message,
            "stage": self.stage,
        }


class RealProviderError(RuntimeError):
    def __init__(self, failure: ProviderFailure) -> None:
        self.failure = failure
        super().__init__(failure.sanitized_message)


@dataclass(frozen=True, slots=True)
class ReferenceAsset:
    artifact_id: str
    path: Path
    sha256: str
    mime: str
    width: int
    height: int
    source_type: str
    usage_rights_status: UsageRightsStatus
    provenance: str
    consent_or_ownership_status: str

    def validate(self) -> None:
        if not self.artifact_id.strip():
            raise ValueError("reference artifact_id is required")
        if self.usage_rights_status is UsageRightsStatus.UNKNOWN:
            raise ValueError("reference usage rights are UNKNOWN")
        if self.mime not in {"image/png", "image/jpeg"}:
            raise ValueError("reference MIME must be image/png or image/jpeg")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("reference dimensions must be positive")
        if len(self.sha256) != 64 or any(char not in "0123456789abcdef" for char in self.sha256):
            raise ValueError("reference SHA-256 is malformed")
        if not self.path.is_file():
            raise ValueError("reference file is missing")
        if sha256_hex(self.path.read_bytes()) != self.sha256:
            raise ValueError("reference SHA-256 does not match local bytes")
        if not self.consent_or_ownership_status.strip():
            raise ValueError("reference ownership or consent status is required")

    def to_dict(self, *, include_path: bool = False) -> dict[str, Any]:
        value: dict[str, Any] = {
            "artifact_id": self.artifact_id,
            "consent_or_ownership_status": self.consent_or_ownership_status,
            "dimensions": {"height": self.height, "width": self.width},
            "mime": self.mime,
            "provenance": self.provenance,
            "sha256": self.sha256,
            "source_type": self.source_type,
            "usage_rights_status": self.usage_rights_status.value,
        }
        if include_path:
            value["path"] = str(self.path)
        return value


@dataclass(frozen=True, slots=True)
class CostPolicy:
    max_calls_per_run: int = 1
    max_retry_count: int = 0
    max_estimated_cost_per_run: float = 0.03

    def validate(self, *, calls: int, retries: int, estimated_cost: float) -> None:
        if calls < 0 or retries < 0 or estimated_cost < 0:
            raise ValueError("cost counters cannot be negative")
        if calls > self.max_calls_per_run:
            raise _provider_error(
                ProviderErrorCode.COST_LIMIT_EXCEEDED,
                "budget",
                "Configured call-count limit would be exceeded.",
            )
        if retries > self.max_retry_count:
            raise _provider_error(
                ProviderErrorCode.COST_LIMIT_EXCEEDED,
                "budget",
                "Configured retry limit would be exceeded.",
            )
        if estimated_cost > self.max_estimated_cost_per_run + 1e-9:
            raise _provider_error(
                ProviderErrorCode.COST_LIMIT_EXCEEDED,
                "budget",
                "Configured estimated-cost limit would be exceeded.",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_calls_per_run": self.max_calls_per_run,
            "max_estimated_cost_per_run": self.max_estimated_cost_per_run,
            "max_retry_count": self.max_retry_count,
        }


@dataclass(frozen=True, slots=True)
class RealImageRequest:
    packet_id: str
    prompt: str
    reference: ReferenceAsset
    model: str = "gpt-image-2"
    quality: str = "low"
    size: str = "1024x1024"
    provider: str = "openai-image"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def estimated_cost_usd(self) -> float:
        # Official low-quality 1024x1024 output is approximately $0.006.
        # The larger cap conservatively allows for text and reference input tokens.
        return 0.03

    @property
    def output_dimensions(self) -> tuple[int, int]:
        width, height = self.size.split("x", 1)
        return int(width), int(height)

    @property
    def prompt_sha256(self) -> str:
        return sha256_hex(self.prompt)

    @property
    def dedupe_key(self) -> str:
        return canonical_json_hash(
            {
                "artifact_type": "image",
                "model": self.model,
                "packet_id": self.packet_id,
                "prompt_sha256": self.prompt_sha256,
                "provider": self.provider,
                "provider_config": {"quality": self.quality, "size": self.size},
                "reference_sha256": self.reference.sha256,
            }
        )

    def validate(self) -> None:
        if not self.packet_id.strip() or not self.prompt.strip():
            raise ValueError("packet_id and prompt are required")
        if self.model != "gpt-image-2":
            raise ValueError("unsupported image model")
        if self.quality != "low":
            raise ValueError("phase two live validation is limited to low quality")
        if self.size != "1024x1024":
            raise ValueError("phase two live validation is limited to 1024x1024")
        self.reference.validate()


@dataclass(frozen=True, slots=True)
class GeneratedMediaArtifact:
    artifact_id: str
    path: Path
    sha256: str
    mime: str
    provider: str
    provider_request_id: str
    model: str
    width: int
    height: int
    request_dedupe_key: str
    provenance_path: Path
    qa_path: Path
    review_state: ReviewState = ReviewState.MANUAL_REVIEW_REQUIRED
    reused: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "height": self.height,
            "mime": self.mime,
            "model": self.model,
            "path": self.path.name,
            "provenance_path": self.provenance_path.name,
            "provider": self.provider,
            "provider_request_id": self.provider_request_id,
            "qa_path": self.qa_path.name,
            "request_dedupe_key": self.request_dedupe_key,
            "reused": self.reused,
            "review_state": self.review_state.value,
            "sha256": self.sha256,
            "width": self.width,
        }


def _provider_error(
    code: ProviderErrorCode,
    stage: str,
    message: str,
    *,
    retryable: bool = False,
    recoverable: bool = True,
    provider: str = "openai-image",
) -> RealProviderError:
    return RealProviderError(
        ProviderFailure(
            stage=stage,
            provider=provider,
            error_code=code,
            sanitized_message=message,
            recoverable=recoverable,
            retryable=retryable,
        )
    )


__all__ = [
    "CostPolicy",
    "GeneratedMediaArtifact",
    "ProviderErrorCode",
    "ProviderFailure",
    "RealProviderError",
    "RealImageRequest",
    "ReferenceAsset",
    "ReviewState",
    "UsageRightsStatus",
]
