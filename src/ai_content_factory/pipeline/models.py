"""State and serialization models for the resumable pipeline."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from ai_content_factory.providers.contracts import BrandProfile


class Stage(str, Enum):
    TOPIC = "TOPIC"
    RESEARCH = "RESEARCH"
    TEXT = "TEXT"
    STORYBOARD = "STORYBOARD"
    MEDIA = "MEDIA"
    MEDIA_QA = "MEDIA_QA"
    APPROVAL = "APPROVAL"
    PUBLISH_PACKAGE = "PUBLISH_PACKAGE"


STAGE_ORDER = (
    Stage.TOPIC,
    Stage.RESEARCH,
    Stage.TEXT,
    Stage.STORYBOARD,
    Stage.MEDIA,
    Stage.MEDIA_QA,
    Stage.APPROVAL,
    Stage.PUBLISH_PACKAGE,
)


class StageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"


@dataclass(frozen=True)
class FailureState:
    """Machine-readable failure information persisted with every failed run."""

    code: str
    message: str
    stage: str
    retryable: bool = False
    provider: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "details": {
                str(key): self.details[key] for key in sorted(self.details)
            },
            "message": self.message,
            "provider": self.provider,
            "retryable": self.retryable,
            "stage": self.stage,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "FailureState | None":
        if not value:
            return None
        details = value.get("details", {})
        if not isinstance(details, Mapping):
            details = {}
        return cls(
            code=str(value.get("code", "UNKNOWN_FAILURE")),
            message=str(value.get("message", "")),
            stage=str(value.get("stage", "")),
            retryable=bool(value.get("retryable", False)),
            provider=(
                str(value["provider"])
                if value.get("provider") is not None
                else None
            ),
            details=dict(details),
        )


@dataclass
class StageRecord:
    stage: Stage
    status: StageStatus = StageStatus.PENDING
    attempts: int = 0
    input_digest: str = ""
    output_digest: str = ""
    output_files: tuple[str, ...] = ()
    failure: FailureState | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempts": self.attempts,
            "failure": self.failure.to_dict() if self.failure else None,
            "input_digest": self.input_digest,
            "output_digest": self.output_digest,
            "output_files": list(self.output_files),
            "stage": self.stage.value,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StageRecord":
        files = value.get("output_files", ())
        if not isinstance(files, (list, tuple)):
            files = ()
        return cls(
            stage=Stage(str(value.get("stage", Stage.TOPIC.value))),
            status=StageStatus(str(value.get("status", StageStatus.PENDING.value))),
            attempts=int(value.get("attempts", 0)),
            input_digest=str(value.get("input_digest", "")),
            output_digest=str(value.get("output_digest", "")),
            output_files=tuple(str(item) for item in files),
            failure=FailureState.from_dict(value.get("failure")),
        )


@dataclass
class PipelineState:
    schema_version: int
    run_id: str
    topic: str
    brand: BrandProfile
    status: RunStatus = RunStatus.PENDING
    current_stage: Stage | None = None
    stage_records: dict[Stage, StageRecord] = field(default_factory=dict)
    failure: FailureState | None = None

    @classmethod
    def new(cls, *, run_id: str, topic: str, brand: BrandProfile) -> "PipelineState":
        return cls(
            schema_version=1,
            run_id=run_id,
            topic=topic,
            brand=brand,
            stage_records={stage: StageRecord(stage=stage) for stage in STAGE_ORDER},
        )

    def record(self, stage: Stage) -> StageRecord:
        if stage not in self.stage_records:
            self.stage_records[stage] = StageRecord(stage=stage)
        return self.stage_records[stage]

    def to_dict(self) -> dict[str, Any]:
        return {
            "brand": self.brand.to_dict(),
            "current_stage": self.current_stage.value if self.current_stage else None,
            "failure": self.failure.to_dict() if self.failure else None,
            "run_id": self.run_id,
            "schema_version": self.schema_version,
            "stage_records": {
                stage.value: self.record(stage).to_dict() for stage in STAGE_ORDER
            },
            "status": self.status.value,
            "topic": self.topic,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PipelineState":
        raw_records = value.get("stage_records", {})
        if not isinstance(raw_records, Mapping):
            raw_records = {}
        records = {
            stage: StageRecord.from_dict(
                raw_records.get(stage.value, {"stage": stage.value})
            )
            for stage in STAGE_ORDER
        }
        current_stage = value.get("current_stage")
        return cls(
            schema_version=int(value.get("schema_version", 1)),
            run_id=str(value.get("run_id", "")),
            topic=str(value.get("topic", "")),
            brand=BrandProfile.from_dict(value.get("brand")),
            status=RunStatus(str(value.get("status", RunStatus.PENDING.value))),
            current_stage=Stage(str(current_stage)) if current_stage else None,
            stage_records=records,
            failure=FailureState.from_dict(value.get("failure")),
        )

    def next_stage(self) -> Stage | None:
        for stage in STAGE_ORDER:
            if self.record(stage).status != StageStatus.SUCCEEDED:
                return stage
        return None


@dataclass(frozen=True)
class PipelineResult:
    state: PipelineState
    output_dir: Path
    no_op: bool = False

    @property
    def succeeded(self) -> bool:
        return self.state.status in {RunStatus.SUCCEEDED, RunStatus.PAUSED}

    @property
    def failure(self) -> FailureState | None:
        return self.state.failure

    def summary(self) -> dict[str, Any]:
        return {
            "current_stage": (
                self.state.current_stage.value if self.state.current_stage else None
            ),
            "failure": self.failure.to_dict() if self.failure else None,
            "no_op": self.no_op,
            "output_dir": str(self.output_dir),
            "run_id": self.state.run_id,
            "status": self.state.status.value,
            "succeeded": self.succeeded,
        }


def canonical_json(value: Any) -> str:
    """Serialize JSON in the one format used for all deterministic artifacts."""

    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        separators=(",", ": "),
    )


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_json(value: Any) -> str:
    return digest_bytes(canonical_json(value).encode("utf-8"))


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def deterministic_run_id(topic: str, brand: BrandProfile) -> str:
    return f"run-{digest_json({'brand': brand.to_dict(), 'topic': topic})[:16]}"


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return value or "untitled"


# Kept as an alias for callers that use the shorter name.
Brand = BrandProfile


__all__ = [
    "Brand",
    "BrandProfile",
    "FailureState",
    "PipelineResult",
    "PipelineState",
    "RunStatus",
    "STAGE_ORDER",
    "Stage",
    "StageRecord",
    "StageStatus",
    "canonical_json",
    "deterministic_run_id",
    "digest_bytes",
    "digest_file",
    "digest_json",
    "slugify",
]
