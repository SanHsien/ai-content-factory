"""Deterministic, resumable orchestration for the offline content factory."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from ai_content_factory.providers.contracts import (
    BrandProfile,
    FixtureUnavailableError,
    MediaAsset,
    ResearchResult,
    TextResult,
)
from ai_content_factory.providers.fixtures import DEMO_TOPIC, FixtureProviders, PLATFORMS
from ai_content_factory.media import evaluate_media_manifest
from ai_content_factory.core.hashing import canonical_json_hash

from .approval import build_approved_packet, validate_approved_packet
from .demo_preview import build_demo_preview
from .models import (
    FailureState,
    PipelineResult,
    PipelineState,
    RunStatus,
    STAGE_ORDER,
    Stage,
    StageRecord,
    StageStatus,
    canonical_json,
    deterministic_run_id,
    digest_file,
    digest_json,
)
from .validation import STATE_FILE


ARTIFACT_FILE_BY_STAGE = {
    Stage.TOPIC: ("packet_seed.json",),
    Stage.RESEARCH: ("research.json",),
    Stage.TEXT: ("article.md", "short_script.md"),
    Stage.STORYBOARD: ("storyboard.json",),
    Stage.MEDIA: ("media_manifest.json",),
    Stage.MEDIA_QA: ("qa_scorecard.json",),
    Stage.APPROVAL: ("content_packet.json", "approval.json"),
    Stage.PUBLISH_PACKAGE: (
        "publish_manifest.json",
        "demo_preview.html",
        *(f"platform-ready/{platform}.txt" for platform in PLATFORMS),
    ),
}
TEXT_METADATA_PREFIX = "<!-- FACTORY_TEXT_METADATA "
TEXT_METADATA_SUFFIX = " -->"
RUN_LOG_FILE = "run_log.jsonl"


class StageExecutionError(RuntimeError):
    """An expected, structured stage failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.details = dict(details or {})


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_write_text(path, canonical_json(value) + "\n")


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise StageExecutionError(
            "ARTIFACT_READ_FAILED",
            "A required local artifact could not be read.",
            retryable=True,
            details={"filename": path.name},
        ) from exc
    if not isinstance(value, Mapping):
        raise StageExecutionError(
            "ARTIFACT_SCHEMA_INVALID",
            "A required artifact is not a JSON object.",
            details={"filename": path.name},
        )
    return value


def _write_text_artifacts(root: Path, result: TextResult) -> None:
    """Write human-readable markdown plus compact resumable text metadata."""

    metadata = json.dumps(
        result.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    article = (
        f"{TEXT_METADATA_PREFIX}{metadata}{TEXT_METADATA_SUFFIX}\n"
        f"# {result.title}\n\n"
        f"## Hook\n\n{result.hook}\n\n"
        f"## Article\n\n{result.script}\n\n"
        f"## Caption\n\n{result.caption}\n"
    )
    short_script = f"# {result.title}\n\n{result.hook}\n\n{result.script}\n"
    _atomic_write_text(root / "article.md", article)
    _atomic_write_text(root / "short_script.md", short_script)


def _read_text_result(root: Path) -> TextResult:
    try:
        first_line = (root / "article.md").read_text(encoding="utf-8").splitlines()[0]
        if not first_line.startswith(TEXT_METADATA_PREFIX) or not first_line.endswith(
            TEXT_METADATA_SUFFIX
        ):
            raise ValueError("text metadata marker is missing")
        raw = first_line[len(TEXT_METADATA_PREFIX) : -len(TEXT_METADATA_SUFFIX)]
        result = TextResult.from_dict(json.loads(raw))
    except (OSError, IndexError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise StageExecutionError(
            "TEXT_ARTIFACT_INVALID",
            "Markdown text artifacts cannot be resumed.",
            retryable=True,
            details={"exception_type": type(exc).__name__},
        ) from exc
    if not (root / "short_script.md").is_file():
        raise StageExecutionError(
            "TEXT_ARTIFACT_INVALID",
            "Short script artifact is missing.",
            retryable=True,
        )
    return result


def _resolve_run_root(base: Path, run_id: str) -> Path:
    """Use output/<run_id>, while accepting an explicit run directory."""

    if base.name == run_id or (base / STATE_FILE).is_file():
        return base
    return base / run_id


def _files_digest(root: Path, filenames: Sequence[str]) -> str:
    return digest_json({filename: digest_file(root / filename) for filename in filenames})


def _normalize_stage(value: Stage | str | None) -> Stage | None:
    if value is None:
        return None
    if isinstance(value, Stage):
        return value
    try:
        return Stage(str(value).upper())
    except ValueError as exc:
        raise ValueError(f"Unknown stage: {value}") from exc


def _safe_exception_message(exc: BaseException) -> str:
    if isinstance(exc, FixtureUnavailableError):
        return "Synthetic fixture unavailable."
    message = str(exc).strip()
    # Failure artifacts must not leak machine-specific or private paths.
    if re.search(r"(?:[A-Za-z]:\\|/|\\\\)", message):  # security-scan: path-pattern
        return "Stage execution failed without exposing a local path."
    return message or "Stage execution failed."


class PipelineOrchestrator:
    """Run only the offline fixture graph and persist after every stage."""

    required_provider_keys = ("research", "text", "image", "video", "voice")

    def __init__(
        self,
        providers: Mapping[str, Any] | FixtureProviders | None = None,
        *,
        fixture_root: str | Path | None = None,
        enforce_fixture_only: bool = True,
    ) -> None:
        if providers is None:
            providers = FixtureProviders(fixture_root=fixture_root)
        if isinstance(providers, FixtureProviders):
            providers = providers.as_mapping()
        elif hasattr(providers, "as_mapping"):
            providers = providers.as_mapping()
        self.providers = dict(providers)
        self.enforce_fixture_only = enforce_fixture_only

    def run(
        self,
        topic: str,
        *,
        brand: BrandProfile | Mapping[str, Any] | None = None,
        output_dir: str | Path,
        resume: bool = False,
        stop_after: Stage | str | None = None,
    ) -> PipelineResult:
        topic = str(topic)
        brand_profile = (
            brand
            if isinstance(brand, BrandProfile)
            else BrandProfile.from_dict(brand)
        )
        run_id = deterministic_run_id(topic, brand_profile)
        root = _resolve_run_root(Path(output_dir), run_id)
        stop_stage = _normalize_stage(stop_after)

        if not topic.strip():
            state = PipelineState.new(run_id=run_id, topic=topic, brand=brand_profile)
            failure = FailureState(
                code="TOPIC_EMPTY",
                message="Topic must not be empty.",
                stage=Stage.TOPIC.value,
            )
            state.status = RunStatus.FAILED
            state.current_stage = Stage.TOPIC
            state.failure = failure
            root.mkdir(parents=True, exist_ok=True)
            self._save_state(root, state)
            return PipelineResult(state=state, output_dir=root)

        state_path = root / STATE_FILE
        if state_path.is_file():
            try:
                state = PipelineState.from_dict(_read_json(state_path))
            except (StageExecutionError, TypeError, ValueError, KeyError) as exc:
                state = PipelineState.new(run_id=run_id, topic=topic, brand=brand_profile)
                failure = FailureState(
                    code="STATE_INVALID",
                    message="Existing pipeline state is invalid.",
                    stage=Stage.TOPIC.value,
                    retryable=False,
                    details={"exception_type": type(exc).__name__},
                )
                state.status = RunStatus.FAILED
                state.current_stage = Stage.TOPIC
                state.failure = failure
                return PipelineResult(state=state, output_dir=root)

            if state.run_id != run_id or state.topic != topic:
                return self._result_with_failure(
                    root,
                    state,
                    code="RESUME_INPUT_MISMATCH",
                    message="Existing state belongs to a different deterministic run.",
                    stage=Stage.TOPIC,
                )
            if state.brand.to_dict() != brand_profile.to_dict():
                return self._result_with_failure(
                    root,
                    state,
                    code="RESUME_BRAND_MISMATCH",
                    message="Existing state belongs to a different brand profile.",
                    stage=Stage.TOPIC,
                )
            if not resume:
                duplicate = FailureState(
                    code="DUPLICATE_RUN",
                    message="A deterministic run already exists; use resume explicitly.",
                    stage=Stage.PUBLISH_PACKAGE.value,
                    retryable=False,
                    details={"run_id": state.run_id},
                )
                duplicate_state = PipelineState.from_dict(state.to_dict())
                duplicate_state.status = RunStatus.DUPLICATE
                duplicate_state.failure = duplicate
                return PipelineResult(state=duplicate_state, output_dir=root)
        else:
            if root.exists() and any(root.iterdir()):
                state = PipelineState.new(run_id=run_id, topic=topic, brand=brand_profile)
                return self._result_with_failure(
                    root,
                    state,
                    code="OUTPUT_DIRECTORY_NOT_EMPTY",
                    message="Output directory contains files but no matching state.",
                    stage=Stage.TOPIC,
                    persist=False,
                )
            root.mkdir(parents=True, exist_ok=True)
            state = PipelineState.new(run_id=run_id, topic=topic, brand=brand_profile)

        # An existing approval is never trusted until local artifact bytes are
        # revalidated.  Mutation blocks resume instead of silently minting a
        # fresh approval for changed content.
        if resume and (root / "approval.json").is_file():
            packet_valid, packet_errors, _ = validate_approved_packet(root)
            if not packet_valid:
                return self._result_with_failure(
                    root,
                    state,
                    code="APPROVAL_INVALIDATED",
                    message="Approved packet integrity changed; resume to publishing is blocked.",
                    stage=Stage.APPROVAL,
                )

        self._rewind_invalid_completed_stages(root, state)
        # A completed, unchanged resume is a deterministic no-op, not a second
        # logical publish event.
        if resume and all(
            state.record(stage).status == StageStatus.SUCCEEDED for stage in STAGE_ORDER
        ):
            return PipelineResult(state=state, output_dir=root, no_op=True)
        state.status = RunStatus.RUNNING
        state.failure = None
        self._save_state(root, state)

        provider_failure = self._provider_set_failure()
        if provider_failure is not None:
            state.status = RunStatus.FAILED
            state.current_stage = Stage.TOPIC
            state.failure = provider_failure
            self._save_state(root, state)
            return PipelineResult(state=state, output_dir=root)

        for stage in STAGE_ORDER:
            record = state.record(stage)
            if record.status == StageStatus.SUCCEEDED:
                continue
            state.current_stage = stage
            record.status = StageStatus.RUNNING
            record.attempts += 1
            record.failure = None
            record.input_digest = digest_json(self._stage_input(state, stage))
            self._save_state(root, state)
            try:
                files = self._execute_stage(stage, state, root)
                record.status = StageStatus.SUCCEEDED
                record.output_files = tuple(files)
                record.output_digest = _files_digest(root, files)
                record.failure = None
                self._save_state(root, state)
            except Exception as exc:  # persisted below as a structured state
                failure = self._failure_for_exception(stage, exc)
                record.status = StageStatus.FAILED
                record.failure = failure
                state.status = RunStatus.FAILED
                state.failure = failure
                self._save_state(root, state)
                return PipelineResult(state=state, output_dir=root)

            if stop_stage == stage:
                state.status = RunStatus.PAUSED
                self._save_state(root, state)
                return PipelineResult(state=state, output_dir=root)

        state.status = RunStatus.SUCCEEDED
        state.current_stage = None
        state.failure = None
        self._save_state(root, state)
        return PipelineResult(state=state, output_dir=root)

    def resume(
        self,
        output_dir: str | Path,
        *,
        stop_after: Stage | str | None = None,
    ) -> PipelineResult:
        root = Path(output_dir)
        if not (root / STATE_FILE).is_file() and root.is_dir():
            candidates = sorted(
                child
                for child in root.iterdir()
                if child.is_dir() and (child / STATE_FILE).is_file()
            )
            if len(candidates) == 1:
                root = candidates[0]
        state = PipelineState.from_dict(_read_json(root / STATE_FILE))
        return self.run(
            state.topic,
            brand=state.brand,
            output_dir=root,
            resume=True,
            stop_after=stop_after,
        )

    def _provider_set_failure(self) -> FailureState | None:
        missing = [key for key in self.required_provider_keys if key not in self.providers]
        if missing:
            return FailureState(
                code="PROVIDER_SET_INCOMPLETE",
                message="The offline provider set is incomplete.",
                stage=Stage.TOPIC.value,
                details={"missing": missing},
            )
        if self.enforce_fixture_only:
            live = [
                key
                for key in self.required_provider_keys
                if not bool(getattr(self.providers[key], "fixture_only", False))
            ]
            if live:
                return FailureState(
                    code="LIVE_PROVIDER_FORBIDDEN",
                    message="Only fixture providers are allowed in phase one.",
                    stage=Stage.TOPIC.value,
                    details={"providers": live},
                )
        if os.environ.get("REMOTE_WRITE", "0") != "0":
            return FailureState(
                code="REMOTE_WRITE_DISABLED",
                message="REMOTE_WRITE must remain 0 for phase one.",
                stage=Stage.PUBLISH_PACKAGE.value,
                details={"remote_write": os.environ.get("REMOTE_WRITE")},
            )
        return None

    def _result_with_failure(
        self,
        root: Path,
        state: PipelineState,
        *,
        code: str,
        message: str,
        stage: Stage,
        persist: bool = True,
    ) -> PipelineResult:
        failure = FailureState(code=code, message=message, stage=stage.value)
        state.status = RunStatus.FAILED
        state.current_stage = stage
        state.failure = failure
        if persist:
            root.mkdir(parents=True, exist_ok=True)
            self._save_state(root, state)
        return PipelineResult(state=state, output_dir=root)

    def _save_state(self, root: Path, state: PipelineState) -> None:
        _write_json(root / STATE_FILE, state.to_dict())
        events = [
            {
                "attempts": state.record(stage).attempts,
                "event": "stage-state",
                "packet_id": state.run_id,
                "provider": self._provider_name_for_log(stage),
                "run_id": state.run_id,
                "stage": stage.value,
                "status": state.record(stage).status.value,
            }
            for stage in STAGE_ORDER
        ]
        events.append(
            {
                "event": "run-state",
                "packet_id": state.run_id,
                "run_id": state.run_id,
                "stage": state.current_stage.value if state.current_stage else None,
                "status": state.status.value,
            }
        )
        _atomic_write_text(
            root / RUN_LOG_FILE,
            "".join(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for event in events),
        )

    def _provider_name_for_log(self, stage: Stage) -> str | None:
        provider_key = {
            Stage.RESEARCH: "research",
            Stage.TEXT: "text",
            Stage.MEDIA: "media",
        }.get(stage)
        if provider_key == "media":
            return "fixture-media-set"
        provider = self.providers.get(provider_key) if provider_key else None
        return str(getattr(provider, "provider_id", provider_key)) if provider else None

    def _stage_input(self, state: PipelineState, stage: Stage) -> dict[str, Any]:
        previous = {
            item.value: state.record(item).output_digest
            for index, item in enumerate(STAGE_ORDER)
            if index < STAGE_ORDER.index(stage)
        }
        return {
            "brand": state.brand.to_dict(),
            "previous_output_digests": previous,
            "run_id": state.run_id,
            "stage": stage.value,
            "topic": state.topic,
        }

    def _rewind_invalid_completed_stages(
        self, root: Path, state: PipelineState
    ) -> None:
        rewind = False
        for stage in STAGE_ORDER:
            record = state.record(stage)
            if rewind:
                record.status = StageStatus.PENDING
                record.output_digest = ""
                record.output_files = ()
                record.failure = None
                continue
            if record.status != StageStatus.SUCCEEDED:
                rewind = True
                continue
            if not record.output_files or any(
                not (root / filename).is_file() for filename in record.output_files
            ):
                record.status = StageStatus.PENDING
                record.output_digest = ""
                record.output_files = ()
                rewind = True
                continue
            try:
                current_digest = _files_digest(root, record.output_files)
            except OSError:
                current_digest = ""
            if current_digest != record.output_digest:
                record.status = StageStatus.PENDING
                record.output_digest = ""
                record.output_files = ()
                rewind = True

    def _provider(self, key: str, stage: Stage) -> Any:
        provider = self.providers.get(key)
        if provider is None:
            raise StageExecutionError(
                "PROVIDER_MISSING",
                "Required fixture provider is missing.",
                details={"provider_key": key},
            )
        if self.enforce_fixture_only and not bool(
            getattr(provider, "fixture_only", False)
        ):
            raise StageExecutionError(
                "LIVE_PROVIDER_FORBIDDEN",
                "Only fixture providers are allowed in the offline pipeline.",
                details={"provider_key": key},
            )
        return provider

    def _execute_stage(self, stage: Stage, state: PipelineState, root: Path) -> tuple[str, ...]:
        if stage == Stage.TOPIC:
            _write_json(
                root / "packet_seed.json",
                {
                    "brand": state.brand.to_dict(),
                    "evidence_status": "fixture-only",
                    "run_id": state.run_id,
                    "topic": state.topic,
                },
            )
            return ARTIFACT_FILE_BY_STAGE[stage]

        if stage == Stage.RESEARCH:
            provider = self._provider("research", stage)
            result = provider.research(state.topic, brand=state.brand)
            if not isinstance(result, ResearchResult):
                raise StageExecutionError(
                    "PROVIDER_RESULT_INVALID",
                    "Research provider returned an invalid result.",
                    details={"provider_key": "research"},
                )
            payload = result.to_dict()
            payload["provider_id"] = str(getattr(provider, "provider_id", "fixture-research"))
            _write_json(root / "research.json", payload)
            return ARTIFACT_FILE_BY_STAGE[stage]

        if stage == Stage.TEXT:
            provider = self._provider("text", stage)
            research = ResearchResult.from_dict(_read_json(root / "research.json"))
            result = provider.generate(state.topic, research, brand=state.brand)
            if not isinstance(result, TextResult):
                raise StageExecutionError(
                    "PROVIDER_RESULT_INVALID",
                    "Text provider returned an invalid result.",
                    details={"provider_key": "text"},
                )
            if set(result.platform_texts) != set(PLATFORMS):
                raise StageExecutionError(
                    "PLATFORM_SET_INVALID",
                    "Text provider must return exactly seven platform texts.",
                    details={"expected": list(PLATFORMS)},
                )
            _write_text_artifacts(root, result)
            return ARTIFACT_FILE_BY_STAGE[stage]

        if stage == Stage.STORYBOARD:
            text = _read_text_result(root)
            scenes = (
                {
                    "end_seconds": 4,
                    "id": "scene-01",
                    "purpose": "hook",
                    "start_seconds": 0,
                    "visual_prompt": "Senior dog carefully testing a paw on a smooth floor; warm home; placeholder visual.",
                    "voiceover": text.hook,
                },
                {
                    "end_seconds": 10,
                    "id": "scene-02",
                    "purpose": "explanation",
                    "start_seconds": 4,
                    "visual_prompt": "Simple traction diagram comparing a smooth floor and a runner; placeholder visual.",
                    "voiceover": "Older dogs may have less strength, balance, or paw grip, so a smooth surface gives them less traction.",
                },
                {
                    "end_seconds": 18,
                    "id": "scene-03",
                    "purpose": "practical steps",
                    "start_seconds": 10,
                    "visual_prompt": "Floor runners, tidy paw fur, and a clear path to water; placeholder visual.",
                    "voiceover": "Add traction, keep pathways clear, and ask a veterinarian about new or painful slipping.",
                },
            )
            _write_json(
                root / "storyboard.json",
                {
                    "evidence_status": "fixture-only",
                    "scenes": list(scenes),
                    "source": "synthetic-storyboard",
                    "topic": state.topic,
                },
            )
            return ARTIFACT_FILE_BY_STAGE[stage]

        if stage == Stage.MEDIA:
            storyboard = _read_json(root / "storyboard.json")
            scenes = storyboard.get("scenes", [])
            if not isinstance(scenes, list) or not scenes:
                raise StageExecutionError(
                    "STORYBOARD_EMPTY",
                    "Storyboard must contain scenes before media planning.",
                )
            image_provider = self._provider("image", stage)
            video_provider = self._provider("video", stage)
            voice_provider = self._provider("voice", stage)
            assets: list[MediaAsset] = []
            assets.append(
                image_provider.generate(
                    str(scenes[0]["visual_prompt"]), topic=state.topic, brand=state.brand
                )
            )
            assets.append(
                image_provider.generate(
                    str(scenes[2]["visual_prompt"]), topic=state.topic, brand=state.brand
                )
            )
            assets.append(
                video_provider.generate(
                    "Senior dog traction explainer placeholder video.",
                    topic=state.topic,
                    brand=state.brand,
                )
            )
            assets.append(
                voice_provider.generate(
                    " ".join(str(scene["voiceover"]) for scene in scenes),
                    topic=state.topic,
                    brand=state.brand,
                )
            )
            if not all(isinstance(asset, MediaAsset) for asset in assets):
                raise StageExecutionError(
                    "PROVIDER_RESULT_INVALID",
                    "A media provider returned an invalid result.",
                    details={"provider_key": "media"},
                )
            descriptors = []
            for asset in assets:
                descriptor = asset.to_dict()
                media_type = descriptor["media_type"]
                extension = {"image": ".png", "video": ".mp4", "voice": ".wav"}[media_type]
                descriptor["path_or_reference"] = f"synthetic/{descriptor['asset_id']}{extension}"
                descriptor["metadata"] = {
                    **descriptor["metadata"],
                    "mime_type": {"image": "image/png", "video": "video/mp4", "voice": "audio/wav"}[media_type],
                    **({"width": 1080, "height": 1920} if media_type in {"image", "video"} else {}),
                    **({"sample_rate_hz": 48000, "channels": 2} if media_type == "voice" else {}),
                }
                descriptor["descriptor_sha256"] = canonical_json_hash(descriptor)
                descriptors.append(descriptor)
            _write_json(
                root / "media_manifest.json",
                {
                    "assets": descriptors,
                    "evidence_status": "fixture-only",
                    "source": "synthetic-media-descriptors",
                    "topic": state.topic,
                },
            )
            return ARTIFACT_FILE_BY_STAGE[stage]

        if stage == Stage.MEDIA_QA:
            media = _read_json(root / "media_manifest.json")
            scorecard = evaluate_media_manifest(media, storyboard=_read_json(root / "storyboard.json"))
            scorecard["topic"] = state.topic
            if scorecard["status"] != "PASS":
                raise StageExecutionError(
                    "MEDIA_QA_FAILED",
                    "Media QA rejected one or more synthetic descriptors.",
                    details={"blocking_reasons": scorecard["blocking_reasons"]},
                )
            _write_json(root / "qa_scorecard.json", scorecard)
            return ARTIFACT_FILE_BY_STAGE[stage]

        if stage == Stage.APPROVAL:
            text = _read_text_result(root)
            packet, document = build_approved_packet(
                root,
                packet_id=state.run_id,
                topic=state.topic,
                platform_copy=text.platform_texts,
                artifact_filenames=(
                    "research.json",
                    "article.md",
                    "short_script.md",
                    "storyboard.json",
                    "media_manifest.json",
                    "qa_scorecard.json",
                ),
            )
            _write_json(root / "content_packet.json", document)
            _write_json(
                root / "approval.json",
                {
                    "approval_scope": "offline-dry-run-and-manual-package-only",
                    "approval_status": packet.approval_state.value,
                    "approved": packet.approval_is_valid,
                    "approved_by": "offline-demo-fixture",
                    "evidence_boundary": "synthetic-fixture-only-not-live-publication",
                    "integrity_valid": packet.validate_integrity().valid,
                    "packet_sha256": packet.packet_hash(),
                    "remote_write": 0,
                    "topic": state.topic,
                },
            )
            return ARTIFACT_FILE_BY_STAGE[stage]

        if stage == Stage.PUBLISH_PACKAGE:
            return self._execute_publish_package(state, root)

        raise StageExecutionError(
            "STAGE_UNSUPPORTED",
            "Pipeline stage is not implemented.",
            details={"stage": stage.value},
        )

    def _execute_publish_package(self, state: PipelineState, root: Path) -> tuple[str, ...]:
        text = _read_text_result(root)
        qa = _read_json(root / "qa_scorecard.json")
        if qa.get("status") != "PASS":
            raise StageExecutionError(
                "MEDIA_QA_REQUIRED",
                "Media QA must pass before packaging.",
            )
        approval = _read_json(root / "approval.json")
        packet_document = _read_json(root / "content_packet.json")
        packet_valid, packet_errors, packet = validate_approved_packet(root, packet_document)
        if approval.get("approval_status") != "APPROVED" or approval.get("approved") is not True:
            raise StageExecutionError(
                "APPROVAL_REQUIRED",
                "An APPROVED packet is required before local publishing paths.",
            )
        if not packet_valid or packet is None or approval.get("packet_sha256") != packet.packet_hash():
            raise StageExecutionError(
                "APPROVAL_INVALIDATED",
                "Packet integrity changed after approval.",
                details={"errors": list(packet_errors)},
            )
        if os.environ.get("REMOTE_WRITE", "0") != "0":
            raise StageExecutionError(
                "REMOTE_WRITE_DISABLED",
                "REMOTE_WRITE must remain 0 for phase one.",
            )
        platform_texts = {platform: str(text.platform_texts[platform]) for platform in PLATFORMS}
        packet_sha256 = packet.packet_hash()
        package_id = digest_json(
            {"packet_sha256": packet_sha256, "platforms": platform_texts, "topic": state.topic}
        )[:16]
        platform_files = {platform: f"platform-ready/{platform}.txt" for platform in PLATFORMS}
        preview = build_demo_preview(
            topic=state.topic,
            title=text.title,
            hook=text.hook,
            script=text.script,
            storyboard=_read_json(root / "storyboard.json"),
            platform_files=platform_files,
            package_id=package_id,
        )
        package_path = root / "publish_manifest.json"
        if package_path.is_file():
            existing = _read_json(package_path)
            if str(existing.get("package_id", "")) != package_id:
                raise StageExecutionError(
                    "DUPLICATE_PACKAGE",
                    "A different deterministic package already exists.",
                    details={"package_id": package_id},
                )
            # A matching package may be safely resumed after a process stop.
            for platform in PLATFORMS:
                if (root / "platform-ready" / f"{platform}.txt").read_text(encoding="utf-8") != platform_texts[platform] + "\n":
                    raise StageExecutionError(
                        "DUPLICATE_PACKAGE",
                        "Existing package text does not match the deterministic package.",
                        details={"platform": platform},
                    )
            preview_path = root / "demo_preview.html"
            if not preview_path.is_file() or preview_path.read_text(encoding="utf-8") != preview:
                raise StageExecutionError(
                    "DUPLICATE_PACKAGE",
                    "Existing demo preview does not match the deterministic package.",
                )
            return ARTIFACT_FILE_BY_STAGE[Stage.PUBLISH_PACKAGE]

        for platform in PLATFORMS:
            _atomic_write_text(root / "platform-ready" / f"{platform}.txt", platform_texts[platform] + "\n")
        # Write auxiliary artifacts first. The manifest is the commit marker,
        # so an interruption before it lands remains safely resumable.
        _atomic_write_text(root / "demo_preview.html", preview)
        _write_json(
            package_path,
            {
                "approval_status": "APPROVED",
                "approval_integrity": "PASS",
                "approval_scope": "offline-dry-run-and-manual-package-only",
                "duplicate_guard": {"package_id": package_id},
                "dedupe_key": package_id,
                "evidence_status": "fixture-only",
                "package_id": package_id,
                "packet_sha256": packet_sha256,
                "artifact_references": {
                    "content_packet": "content_packet.json",
                    "media_manifest": "media_manifest.json",
                    "qa_scorecard": "qa_scorecard.json",
                },
                "platform_files": platform_files,
                "preview_file": "demo_preview.html",
                "platforms": platform_texts,
                "planned_actions": {
                    platform: {
                        "action": "prepare-local-platform-copy",
                        "destination": platform,
                        "remote_write": 0,
                    }
                    for platform in PLATFORMS
                },
                "publisher_modes": ["dry-run", "manual"],
                "remote_write": 0,
                "topic": state.topic,
            },
        )
        return ARTIFACT_FILE_BY_STAGE[Stage.PUBLISH_PACKAGE]

    def _failure_for_exception(self, stage: Stage, exc: BaseException) -> FailureState:
        provider = None
        key_by_stage = {
            Stage.RESEARCH: "research",
            Stage.TEXT: "text",
            Stage.MEDIA: "media",
        }
        provider_key = key_by_stage.get(stage)
        if provider_key and provider_key in self.providers:
            provider = str(getattr(self.providers[provider_key], "provider_id", provider_key))
        if isinstance(exc, StageExecutionError):
            return FailureState(
                code=exc.code,
                message=_safe_exception_message(exc),
                stage=stage.value,
                retryable=exc.retryable,
                provider=provider,
                details=exc.details,
            )
        if isinstance(exc, FixtureUnavailableError):
            return FailureState(
                code="FIXTURE_UNAVAILABLE",
                message="Synthetic fixture unavailable.",
                stage=stage.value,
                retryable=True,
                provider=provider,
                details={"exception_type": type(exc).__name__},
            )
        return FailureState(
            code="STAGE_EXECUTION_FAILED",
            message=_safe_exception_message(exc),
            stage=stage.value,
            retryable=False,
            provider=provider,
            details={"exception_type": type(exc).__name__},
        )


def run_demo(
    output_dir: str | Path,
    *,
    resume: bool = False,
    stop_after: Stage | str | None = None,
) -> PipelineResult:
    """Run the deterministic, public-safe demonstration topic."""

    return PipelineOrchestrator().run(
        DEMO_TOPIC,
        brand=BrandProfile(),
        output_dir=output_dir,
        resume=resume,
        stop_after=stop_after,
    )


__all__ = [
    "ARTIFACT_FILE_BY_STAGE",
    "DEMO_TOPIC",
    "PipelineOrchestrator",
    "StageExecutionError",
    "run_demo",
]
