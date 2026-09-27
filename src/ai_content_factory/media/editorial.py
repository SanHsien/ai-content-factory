"""Provider-neutral editorial planning, compilation, and quality gates.

The editor brain converts narrative intent into a renderable multi-shot plan.
It does not generate media, invoke HyperFrames or FFmpeg, inspect private brand
files, or perform a network/remote write.  Those remain explicit adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Iterable, Mapping, Sequence


class EditorialContractError(ValueError):
    """Raised when an editorial contract is internally inconsistent."""


class EditorialGateError(RuntimeError):
    """Raised when a timeline is technically valid but not renderable."""


class SourceType(str, Enum):
    H3_VIDEO = "H3_VIDEO"
    GENERATED_IMAGE = "GENERATED_IMAGE"
    BROLL_IMAGE = "BROLL_IMAGE"
    MOTION_RENDER_IMAGE = "MOTION_RENDER_IMAGE"
    TEXT_CARD = "TEXT_CARD"
    BRAND_CLOSE = "BRAND_CLOSE"


class SceneType(str, Enum):
    VIDEO = "video"
    IMAGE = "image"
    BROLL = "broll"
    TEXT = "text"
    BRAND_CLOSE = "brand_close"


class ShotSize(str, Enum):
    ECU = "ECU"
    CU = "CU"
    MCU = "MCU"
    MS = "MS"
    FS = "FS"
    DETAIL = "DETAIL"


class CameraAngle(str, Enum):
    EYE_LEVEL = "eye_level"
    LOW = "low"
    HIGH = "high"
    SIDE = "side"
    OVER_SHOULDER = "over_shoulder"


class CameraMotion(str, Enum):
    LOCKED = "locked"
    PUSH_IN = "push_in"
    PULL_OUT = "pull_out"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    TILT = "tilt"
    TRACKING = "tracking"
    HANDHELD_SUBTLE = "handheld_subtle"


class PaceProfile(str, Enum):
    FAST = "FAST"
    BALANCED = "BALANCED"
    CALM = "CALM"
    BALANCED_CALM = "BALANCED_CALM"


VIDEO_SOURCE_TYPES = frozenset({SourceType.H3_VIDEO})
STILL_SOURCE_TYPES = frozenset(
    {
        SourceType.GENERATED_IMAGE,
        SourceType.BROLL_IMAGE,
        SourceType.MOTION_RENDER_IMAGE,
        SourceType.BRAND_CLOSE,
    }
)


def _enum_value(enum_type: type[Enum], value: Enum | str, field_name: str):
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(str(value))
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise EditorialContractError(f"{field_name} must be one of: {allowed}") from exc


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EditorialContractError(f"{field_name} is required")
    return value.strip()


@dataclass(frozen=True, slots=True)
class AudioBehavior:
    ambient_audio: str = "none"
    sfx: tuple[str, ...] = ()
    music: str = "none"
    ducking_db: float = -16.0
    fade_in_seconds: float = 0.08
    fade_out_seconds: float = 0.12

    def validate(self) -> None:
        if not -40.0 <= self.ducking_db <= 0.0:
            raise EditorialContractError("ducking_db must be between -40 and 0")
        if not 0.0 <= self.fade_in_seconds <= 1.0:
            raise EditorialContractError("fade_in_seconds must be between 0 and 1")
        if not 0.0 <= self.fade_out_seconds <= 1.0:
            raise EditorialContractError("fade_out_seconds must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ambient_audio": self.ambient_audio,
            "ducking_db": self.ducking_db,
            "fade_in_seconds": self.fade_in_seconds,
            "fade_out_seconds": self.fade_out_seconds,
            "music": self.music,
            "sfx": list(self.sfx),
        }


@dataclass(frozen=True, slots=True)
class TransitionSpec:
    kind: str = "hard_cut"
    duration_seconds: float = 0.0

    def validate(self) -> None:
        if self.kind not in {"hard_cut", "crossfade", "dip", "masked_wipe", "push"}:
            raise EditorialContractError("unsupported transition kind")
        if not 0.0 <= self.duration_seconds <= 0.35:
            raise EditorialContractError("transition duration must be 0 to 0.35 seconds")
        if self.kind == "hard_cut" and self.duration_seconds != 0:
            raise EditorialContractError("hard_cut transition duration must be zero")

    def to_dict(self) -> dict[str, Any]:
        return {"duration_seconds": self.duration_seconds, "kind": self.kind}


@dataclass(frozen=True, slots=True)
class ShotSpec:
    shot_id: str
    purpose: str
    start_time_seconds: float
    duration_seconds: float
    source_type: SourceType | str
    asset_id: str
    asset_request: Mapping[str, Any] = field(default_factory=dict)
    image_prompt: str = ""
    video_prompt: str = ""
    subject_action: str = ""
    shot_size: ShotSize | str = ShotSize.MS
    camera_angle: CameraAngle | str = CameraAngle.EYE_LEVEL
    camera_motion: CameraMotion | str = CameraMotion.LOCKED
    motion_intensity: float = 0.0
    crop_strategy: str = "fit"
    continuity_from_previous: tuple[str, ...] = ()
    composition: str = ""
    lighting: str = ""
    overlay: str = ""
    subtitle_behavior: str = "phrase_level"
    voiceover_segment: str = ""
    transition_in: TransitionSpec = field(default_factory=TransitionSpec)
    transition_out: TransitionSpec = field(default_factory=TransitionSpec)
    audio_behavior: AudioBehavior = field(default_factory=AudioBehavior)
    quality_requirements: tuple[str, ...] = ()
    narrative_role: str = ""
    scene_type: SceneType | str | None = None

    def __post_init__(self) -> None:
        source_type = _enum_value(SourceType, self.source_type, "source_type")
        object.__setattr__(self, "source_type", source_type)
        object.__setattr__(self, "shot_size", _enum_value(ShotSize, self.shot_size, "shot_size"))
        object.__setattr__(
            self, "camera_angle", _enum_value(CameraAngle, self.camera_angle, "camera_angle")
        )
        object.__setattr__(
            self, "camera_motion", _enum_value(CameraMotion, self.camera_motion, "camera_motion")
        )
        if self.scene_type is None:
            inferred = {
                SourceType.H3_VIDEO: SceneType.VIDEO,
                SourceType.GENERATED_IMAGE: SceneType.IMAGE,
                SourceType.BROLL_IMAGE: SceneType.BROLL,
                SourceType.MOTION_RENDER_IMAGE: SceneType.IMAGE,
                SourceType.TEXT_CARD: SceneType.TEXT,
                SourceType.BRAND_CLOSE: SceneType.BRAND_CLOSE,
            }[source_type]
            object.__setattr__(self, "scene_type", inferred)
        else:
            object.__setattr__(
                self, "scene_type", _enum_value(SceneType, self.scene_type, "scene_type")
            )
        object.__setattr__(self, "asset_request", dict(self.asset_request))
        object.__setattr__(self, "continuity_from_previous", tuple(self.continuity_from_previous))
        object.__setattr__(self, "quality_requirements", tuple(self.quality_requirements))

    @property
    def end_time_seconds(self) -> float:
        return self.start_time_seconds + self.duration_seconds

    @property
    def has_intentional_motion(self) -> bool:
        return self.source_type in VIDEO_SOURCE_TYPES or self.camera_motion is not CameraMotion.LOCKED

    def validate(self) -> None:
        _require_text(self.shot_id, "shot_id")
        _require_text(self.purpose, "purpose")
        _require_text(self.asset_id, "asset_id")
        if self.start_time_seconds < 0 or self.duration_seconds <= 0:
            raise EditorialContractError("shot timing must be positive and start at or after zero")
        if not 0.0 <= self.motion_intensity <= 1.0:
            raise EditorialContractError("motion_intensity must be between 0 and 1")
        if self.source_type is SourceType.H3_VIDEO and not self.video_prompt.strip():
            raise EditorialContractError("H3_VIDEO requires video_prompt")
        if self.source_type in STILL_SOURCE_TYPES and not self.image_prompt.strip():
            raise EditorialContractError("image-backed shot requires image_prompt")
        if self.source_type is SourceType.TEXT_CARD and self.duration_seconds > 1.5:
            raise EditorialContractError("TEXT_CARD duration cannot exceed 1.5 seconds")
        if (
            self.source_type in STILL_SOURCE_TYPES
            and self.duration_seconds > 1.0
            and self.camera_motion is CameraMotion.LOCKED
        ):
            raise EditorialContractError("still shots over one second require intentional camera motion")
        self.transition_in.validate()
        self.transition_out.validate()
        self.audio_behavior.validate()

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "asset_request": dict(self.asset_request),
            "audio_behavior": self.audio_behavior.to_dict(),
            "camera_angle": self.camera_angle.value,
            "camera_motion": self.camera_motion.value,
            "composition": self.composition,
            "continuity_from_previous": list(self.continuity_from_previous),
            "crop_strategy": self.crop_strategy,
            "duration_seconds": self.duration_seconds,
            "end_time_seconds": self.end_time_seconds,
            "image_prompt": self.image_prompt,
            "lighting": self.lighting,
            "motion_intensity": self.motion_intensity,
            "narrative_role": self.narrative_role or self.purpose,
            "overlay": self.overlay,
            "purpose": self.purpose,
            "quality_requirements": list(self.quality_requirements),
            "scene_type": self.scene_type.value,
            "shot_id": self.shot_id,
            "shot_size": self.shot_size.value,
            "source_type": self.source_type.value,
            "start_time_seconds": self.start_time_seconds,
            "subject_action": self.subject_action,
            "subtitle_behavior": self.subtitle_behavior,
            "transition_in": self.transition_in.to_dict(),
            "transition_out": self.transition_out.to_dict(),
            "video_prompt": self.video_prompt,
            "voiceover_segment": self.voiceover_segment,
        }


@dataclass(frozen=True, slots=True)
class EditorialPlan:
    editorial_plan_id: str
    target_platform: str
    target_duration_seconds: float
    fps: int
    aspect_ratio: str
    story_arc: tuple[str, ...]
    hook_strategy: str
    pace_profile: PaceProfile | str
    shots: tuple[ShotSpec, ...]
    expected_cut_count: int | None = None
    schema_version: str = "2.0"

    def __post_init__(self) -> None:
        object.__setattr__(self, "story_arc", tuple(self.story_arc))
        object.__setattr__(self, "shots", tuple(self.shots))
        object.__setattr__(
            self, "pace_profile", _enum_value(PaceProfile, self.pace_profile, "pace_profile")
        )
        if self.expected_cut_count is None:
            object.__setattr__(self, "expected_cut_count", max(0, len(self.shots) - 1))

    def validate(self) -> None:
        _require_text(self.editorial_plan_id, "editorial_plan_id")
        _require_text(self.target_platform, "target_platform")
        _require_text(self.hook_strategy, "hook_strategy")
        if self.schema_version != "2.0":
            raise EditorialContractError("unsupported EditorialPlan schema_version")
        if self.fps <= 0 or self.target_duration_seconds <= 0:
            raise EditorialContractError("fps and target duration must be positive")
        if self.aspect_ratio != "9:16":
            raise EditorialContractError("editorial plan aspect_ratio must be 9:16")
        if not self.story_arc or not self.shots:
            raise EditorialContractError("story_arc and shots are required")
        shot_ids: set[str] = set()
        previous_end = 0.0
        for index, shot in enumerate(self.shots):
            shot.validate()
            if shot.shot_id in shot_ids:
                raise EditorialContractError("shot_id values must be unique")
            shot_ids.add(shot.shot_id)
            if not math.isclose(shot.start_time_seconds, previous_end, abs_tol=0.001):
                raise EditorialContractError(f"shot {index + 1} does not start at the prior shot end")
            previous_end = shot.end_time_seconds
        if not math.isclose(previous_end, self.target_duration_seconds, abs_tol=0.001):
            raise EditorialContractError("shot timeline must equal target_duration_seconds")
        if self.expected_cut_count != max(0, len(self.shots) - 1):
            raise EditorialContractError("expected_cut_count must equal shot_count - 1")

    def to_dict(self) -> dict[str, Any]:
        coverage = calculate_coverage(self)
        return {
            "aspect_ratio": self.aspect_ratio,
            "asset_diversity": coverage["unique_visual_assets"],
            "editorial_plan_id": self.editorial_plan_id,
            "expected_cut_count": self.expected_cut_count,
            "fps": self.fps,
            "hook_strategy": self.hook_strategy,
            "motion_coverage": coverage["motion_visual_coverage"],
            "pace_profile": self.pace_profile.value,
            "schema_version": self.schema_version,
            "shots": [shot.to_dict() for shot in self.shots],
            "story_arc": list(self.story_arc),
            "target_duration_seconds": self.target_duration_seconds,
            "target_platform": self.target_platform,
            "text_card_coverage": coverage["text_only_coverage"],
            "visual_coverage": coverage,
        }


@dataclass(frozen=True, slots=True)
class AssetRequirement:
    asset_id: str
    source_type: SourceType
    requested_by_shots: tuple[str, ...]
    prompt: str
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "prompt": self.prompt,
            "requested_by_shots": list(self.requested_by_shots),
            "required": self.required,
            "source_type": self.source_type.value,
        }


@dataclass(frozen=True, slots=True)
class AssetPlan:
    editorial_plan_id: str
    requirements: tuple[AssetRequirement, ...]
    missing_asset_ids: tuple[str, ...]
    ready_for_timeline: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "editorial_plan_id": self.editorial_plan_id,
            "missing_asset_ids": list(self.missing_asset_ids),
            "ready_for_timeline": self.ready_for_timeline,
            "requirements": [item.to_dict() for item in self.requirements],
        }


class AssetPlanner:
    """Builds deterministic requirements before any image/video generation."""

    def plan(self, editorial_plan: EditorialPlan, available_asset_ids: Iterable[str] = ()) -> AssetPlan:
        editorial_plan.validate()
        available = set(available_asset_ids)
        by_asset: dict[str, list[ShotSpec]] = {}
        for shot in editorial_plan.shots:
            if shot.source_type is SourceType.TEXT_CARD:
                continue
            by_asset.setdefault(shot.asset_id, []).append(shot)
        requirements = []
        for asset_id, shots in by_asset.items():
            first = shots[0]
            prompt = first.video_prompt if first.source_type is SourceType.H3_VIDEO else first.image_prompt
            requirements.append(
                AssetRequirement(
                    asset_id=asset_id,
                    source_type=first.source_type,
                    requested_by_shots=tuple(shot.shot_id for shot in shots),
                    prompt=prompt,
                )
            )
        missing = tuple(sorted(item.asset_id for item in requirements if item.asset_id not in available))
        return AssetPlan(
            editorial_plan_id=editorial_plan.editorial_plan_id,
            requirements=tuple(requirements),
            missing_asset_ids=missing,
            ready_for_timeline=not missing,
        )


@dataclass(frozen=True, slots=True)
class ScriptSegment:
    segment_id: str
    text: str
    narrative_role: str


@dataclass(frozen=True, slots=True)
class BrandVisualPolicy:
    style: str
    palette: tuple[str, ...]
    identity_constraints: tuple[str, ...]
    disclosure: str = ""


@dataclass(frozen=True, slots=True)
class ContinuityState:
    subject_identity: str
    environment: str
    lighting_family: str
    wardrobe_or_accessories: str = ""


@dataclass(frozen=True, slots=True)
class CompiledDirectorPrompts:
    image_generation_prompt: str
    h3_structured_prompt: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "h3_structured_prompt": self.h3_structured_prompt,
            "image_generation_prompt": self.image_generation_prompt,
        }


class DirectorPromptCompiler:
    """Compiles shot-specific image and H3 prompts from neutral contracts."""

    def compile(
        self,
        segment: ScriptSegment,
        shot: ShotSpec,
        brand_policy: BrandVisualPolicy,
        continuity: ContinuityState,
    ) -> CompiledDirectorPrompts:
        shot.validate()
        image_prompt = "\n".join(
            [
                f"STYLE: {brand_policy.style}",
                f"SHOT SIZE: {shot.shot_size.value}",
                f"CAMERA ANGLE: {shot.camera_angle.value}",
                f"INITIAL COMPOSITION: {shot.composition or 'clear subject-led composition'}",
                f"SUBJECT: {continuity.subject_identity}",
                f"SUBJECT ACTION: {shot.subject_action or segment.narrative_role}",
                f"ENVIRONMENT: {continuity.environment}",
                f"LIGHTING: {shot.lighting or continuity.lighting_family}",
                f"PALETTE: {', '.join(brand_policy.palette)}",
                "CONTINUITY: " + "; ".join(brand_policy.identity_constraints + shot.continuity_from_previous),
                f"EDITORIAL PURPOSE: {shot.purpose}",
                "CONSTRAINTS: no text, no watermark, anatomically coherent, preserve identity",
            ]
        )
        if shot.source_type is not SourceType.H3_VIDEO:
            return CompiledDirectorPrompts(image_prompt, None)
        h3_prompt = "\n".join(
            [
                "integrated_multimodal_description:",
                f"STYLE: {brand_policy.style}.",
                f"SHOT SIZE: {shot.shot_size.value}; CAMERA ANGLE: {shot.camera_angle.value}.",
                f"INITIAL COMPOSITION: {shot.composition or 'subject centered in a stable frame'}.",
                f"SUBJECT ACTION: {shot.subject_action}.",
                f"TIMED ACTION: {shot.video_prompt}.",
                f"CAMERA MOVEMENT: {shot.camera_motion.value}, intensity {shot.motion_intensity:.2f}.",
                "CONTINUITY: " + "; ".join(brand_policy.identity_constraints + shot.continuity_from_previous) + ".",
                "NEGATIVE CONSTRAINTS: no identity drift, no extra anatomy, no facial redesign, no eye enlargement, no flicker, no texture crawling.",
                "overall_soundscape:",
                f"{shot.audio_behavior.ambient_audio}; restrained and continuous under narration.",
                "non_diegetic_music:",
                f"{shot.audio_behavior.music}; narration remains primary with {shot.audio_behavior.ducking_db:.1f} dB ducking.",
            ]
        )
        return CompiledDirectorPrompts(image_prompt, h3_prompt)


@dataclass(frozen=True, slots=True)
class SubtitleCue:
    cue_id: str
    start_time_seconds: float
    end_time_seconds: float
    text: str
    animation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "animation": self.animation,
            "cue_id": self.cue_id,
            "end_time_seconds": self.end_time_seconds,
            "start_time_seconds": self.start_time_seconds,
            "text": self.text,
        }


class SubtitleEditor:
    """Creates phrase-level cues without karaoke-style word overload."""

    def compile(
        self,
        phrases: Sequence[str],
        start_time_seconds: float,
        end_time_seconds: float,
        animations: Sequence[str] = ("fade_up", "pop_in", "slide"),
    ) -> tuple[SubtitleCue, ...]:
        cleaned = tuple(phrase.strip() for phrase in phrases if phrase.strip())
        if not cleaned or end_time_seconds <= start_time_seconds:
            raise EditorialContractError("subtitle phrases and a positive time range are required")
        if any(len(phrase.replace(" ", "")) > 14 for phrase in cleaned):
            raise EditorialContractError("subtitle phrase exceeds 14 visible characters")
        unit = (end_time_seconds - start_time_seconds) / len(cleaned)
        cues = []
        for index, phrase in enumerate(cleaned):
            cues.append(
                SubtitleCue(
                    cue_id=f"subtitle-{index + 1:02d}",
                    start_time_seconds=start_time_seconds + unit * index,
                    end_time_seconds=start_time_seconds + unit * (index + 1),
                    text=phrase,
                    animation=animations[index % len(animations)],
                )
            )
        return tuple(cues)


@dataclass(frozen=True, slots=True)
class AudioMixEvent:
    shot_id: str
    start_time_seconds: float
    end_time_seconds: float
    narration_gain_db: float
    bed_gain_db: float
    fade_in_seconds: float
    fade_out_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "bed_gain_db": self.bed_gain_db,
            "end_time_seconds": self.end_time_seconds,
            "fade_in_seconds": self.fade_in_seconds,
            "fade_out_seconds": self.fade_out_seconds,
            "narration_gain_db": self.narration_gain_db,
            "shot_id": self.shot_id,
            "start_time_seconds": self.start_time_seconds,
        }


class AudioEditor:
    """Compiles a narration-first ducking plan without touching media files."""

    def compile(self, plan: EditorialPlan) -> tuple[AudioMixEvent, ...]:
        plan.validate()
        events = []
        for shot in plan.shots:
            audio = shot.audio_behavior
            narration_active = bool(shot.voiceover_segment.strip())
            events.append(
                AudioMixEvent(
                    shot_id=shot.shot_id,
                    start_time_seconds=shot.start_time_seconds,
                    end_time_seconds=shot.end_time_seconds,
                    narration_gain_db=0.0,
                    bed_gain_db=audio.ducking_db if narration_active else min(-8.0, audio.ducking_db + 6.0),
                    fade_in_seconds=audio.fade_in_seconds,
                    fade_out_seconds=audio.fade_out_seconds,
                )
            )
        return tuple(events)


@dataclass(frozen=True, slots=True)
class ShotTimeline:
    editorial_plan_id: str
    duration_seconds: float
    fps: int
    shots: tuple[Mapping[str, Any], ...]
    subtitle_cues: tuple[SubtitleCue, ...]
    audio_events: tuple[AudioMixEvent, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "audio_events": [event.to_dict() for event in self.audio_events],
            "duration_seconds": self.duration_seconds,
            "editorial_plan_id": self.editorial_plan_id,
            "fps": self.fps,
            "shots": [dict(shot) for shot in self.shots],
            "subtitle_cues": [cue.to_dict() for cue in self.subtitle_cues],
        }


class TimelineCompiler:
    """Produces the deterministic handoff consumed by a sequence renderer."""

    def compile(
        self,
        plan: EditorialPlan,
        asset_plan: AssetPlan,
        subtitle_cues: Sequence[SubtitleCue],
        audio_events: Sequence[AudioMixEvent],
        *,
        require_editorial_pass: bool = True,
    ) -> ShotTimeline:
        plan.validate()
        if asset_plan.editorial_plan_id != plan.editorial_plan_id:
            raise EditorialContractError("asset plan does not match editorial plan")
        if not asset_plan.ready_for_timeline:
            raise EditorialGateError("missing assets must be generated before timeline compilation")
        scorecard = evaluate_editorial_quality(plan, subtitle_cues, audio_events)
        if require_editorial_pass and scorecard.status != "PASS":
            raise EditorialGateError("editorial quality gate failed before render")
        return ShotTimeline(
            editorial_plan_id=plan.editorial_plan_id,
            duration_seconds=plan.target_duration_seconds,
            fps=plan.fps,
            shots=tuple(shot.to_dict() for shot in plan.shots),
            subtitle_cues=tuple(subtitle_cues),
            audio_events=tuple(audio_events),
        )


def _merged_unchanged_visual_duration(shots: Sequence[ShotSpec]) -> float:
    maximum = 0.0
    current = 0.0
    signature: tuple[str, str, str, str] | None = None
    for shot in shots:
        if shot.has_intentional_motion:
            current = 0.0
            signature = None
            continue
        candidate = (
            shot.asset_id,
            shot.crop_strategy,
            shot.camera_motion.value,
            shot.overlay,
        )
        if candidate == signature:
            current += shot.duration_seconds
        else:
            current = shot.duration_seconds
            signature = candidate
        maximum = max(maximum, current)
    return maximum


def calculate_coverage(plan: EditorialPlan) -> dict[str, float | int]:
    duration = plan.target_duration_seconds
    moving = sum(shot.duration_seconds for shot in plan.shots if shot.source_type in VIDEO_SOURCE_TYPES)
    motion_render = sum(
        shot.duration_seconds
        for shot in plan.shots
        if shot.source_type in STILL_SOURCE_TYPES and shot.camera_motion is not CameraMotion.LOCKED
    )
    static_image = sum(
        shot.duration_seconds
        for shot in plan.shots
        if shot.source_type in STILL_SOURCE_TYPES and shot.camera_motion is CameraMotion.LOCKED
    )
    text_only = sum(shot.duration_seconds for shot in plan.shots if shot.source_type is SourceType.TEXT_CARD)
    by_asset: dict[str, float] = {}
    for shot in plan.shots:
        by_asset[shot.asset_id] = by_asset.get(shot.asset_id, 0.0) + shot.duration_seconds
    return {
        "asset_reuse_ratio": max(by_asset.values(), default=0.0) / duration,
        "generative_video_coverage": moving / duration,
        "max_unchanged_visual_state_seconds": _merged_unchanged_visual_duration(plan.shots),
        "motion_render_seconds": motion_render,
        "motion_visual_coverage": (moving + motion_render) / duration,
        "moving_video_seconds": moving,
        "static_image_seconds": static_image,
        "text_only_coverage": text_only / duration,
        "text_only_seconds": text_only,
        "unique_visual_assets": len(by_asset),
    }


@dataclass(frozen=True, slots=True)
class EditorialQualityScorecard:
    status: str
    shot_count: int
    average_shot_duration: float
    max_static_hold: float
    unique_visual_assets: int
    h3_clip_count: int
    generative_video_coverage: float
    motion_visual_coverage: float
    text_only_coverage: float
    asset_reuse_ratio: float
    visual_change_interval: float
    subtitle_rhythm: float
    audio_continuity: float
    shot_story_alignment: float
    visual_diversity: float
    pacing_score: float
    editing_product_score: float
    blocking_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_reuse_ratio": self.asset_reuse_ratio,
            "audio_continuity": self.audio_continuity,
            "average_shot_duration": self.average_shot_duration,
            "blocking_reasons": list(self.blocking_reasons),
            "editing_product_score": self.editing_product_score,
            "generative_video_coverage": self.generative_video_coverage,
            "h3_clip_count": self.h3_clip_count,
            "max_static_hold": self.max_static_hold,
            "motion_visual_coverage": self.motion_visual_coverage,
            "pacing_score": self.pacing_score,
            "shot_count": self.shot_count,
            "shot_story_alignment": self.shot_story_alignment,
            "status": self.status,
            "subtitle_rhythm": self.subtitle_rhythm,
            "text_only_coverage": self.text_only_coverage,
            "unique_visual_assets": self.unique_visual_assets,
            "visual_change_interval": self.visual_change_interval,
            "visual_diversity": self.visual_diversity,
        }


def evaluate_editorial_quality(
    plan: EditorialPlan,
    subtitle_cues: Sequence[SubtitleCue] = (),
    audio_events: Sequence[AudioMixEvent] = (),
) -> EditorialQualityScorecard:
    plan.validate()
    coverage = calculate_coverage(plan)
    shot_count = len(plan.shots)
    average = plan.target_duration_seconds / shot_count
    h3_count = len({shot.asset_id for shot in plan.shots if shot.source_type is SourceType.H3_VIDEO})
    blocking: list[str] = []
    premium = 20.0 <= plan.target_duration_seconds <= 30.0
    if premium and shot_count < 8:
        blocking.append("SHOT_DENSITY_TOO_LOW")
    if premium and not 1.5 <= average <= 3.5:
        blocking.append("AVERAGE_SHOT_DURATION_OUT_OF_RANGE")
    if coverage["max_unchanged_visual_state_seconds"] > 3.0:
        blocking.append("UNCHANGED_VISUAL_STATE_OVER_3_SECONDS")
    if premium and coverage["unique_visual_assets"] < 5:
        blocking.append("INSUFFICIENT_VISUAL_ASSETS")
    if premium and h3_count < 2:
        blocking.append("INSUFFICIENT_GENERATIVE_VIDEO_CLIPS")
    if premium and coverage["generative_video_coverage"] < 0.30:
        blocking.append("GENERATIVE_VIDEO_COVERAGE_BELOW_30_PERCENT")
    if premium and coverage["motion_visual_coverage"] < 0.85:
        blocking.append("MOTION_VISUAL_COVERAGE_BELOW_85_PERCENT")
    if coverage["text_only_coverage"] > 0.15:
        blocking.append("TEXT_ONLY_COVERAGE_TOO_HIGH")
    if coverage["asset_reuse_ratio"] > 0.40:
        blocking.append("ASSET_REUSE_TOO_HIGH")
    if any(
        shot.source_type is SourceType.TEXT_CARD and shot.duration_seconds > 1.5
        for shot in plan.shots
    ):
        blocking.append("TEXT_CARD_OVER_1_5_SECONDS")
    if any(
        shot.source_type in STILL_SOURCE_TYPES
        and shot.duration_seconds > 1.0
        and shot.camera_motion is CameraMotion.LOCKED
        for shot in plan.shots
    ):
        blocking.append("STATIC_STILL_WITHOUT_MOTION")

    subtitle_rhythm = 10.0
    if subtitle_cues:
        longest = max(len(cue.text.replace(" ", "")) for cue in subtitle_cues)
        overlap = any(
            current.end_time_seconds > following.start_time_seconds + 0.001
            for current, following in zip(subtitle_cues, subtitle_cues[1:])
        )
        subtitle_rhythm = max(0.0, 10.0 - max(0, longest - 14) * 0.5 - (4.0 if overlap else 0.0))
        if overlap or longest > 14:
            blocking.append("SUBTITLE_RHYTHM_FAIL")
    audio_continuity = 10.0
    if audio_events:
        if len(audio_events) != shot_count:
            audio_continuity = 6.0
            blocking.append("AUDIO_TIMELINE_INCOMPLETE")
        elif any(event.bed_gain_db > -8.0 for event in audio_events):
            audio_continuity = 7.0
            blocking.append("AUDIO_DUCKING_INSUFFICIENT")
    shot_story_alignment = round(
        10.0 * sum(bool(shot.purpose and shot.voiceover_segment) for shot in plan.shots) / shot_count,
        2,
    )
    visual_diversity = round(min(10.0, 10.0 * coverage["unique_visual_assets"] / max(5, shot_count)), 2)
    pacing_score = round(
        max(0.0, 10.0 - abs(average - 2.5) * 2.0 - max(0.0, coverage["max_unchanged_visual_state_seconds"] - 3.0) * 2.0),
        2,
    )
    coverage_score = min(
        10.0,
        10.0 * coverage["motion_visual_coverage"] / 0.85,
        10.0 * coverage["generative_video_coverage"] / 0.30,
    )
    editing_score = round(
        (
            subtitle_rhythm
            + audio_continuity
            + shot_story_alignment
            + visual_diversity
            + pacing_score
            + coverage_score
        )
        / 6.0,
        2,
    )
    return EditorialQualityScorecard(
        status="PASS" if not blocking and editing_score >= 8.0 else "FAIL",
        shot_count=shot_count,
        average_shot_duration=round(average, 3),
        max_static_hold=round(float(coverage["max_unchanged_visual_state_seconds"]), 3),
        unique_visual_assets=int(coverage["unique_visual_assets"]),
        h3_clip_count=h3_count,
        generative_video_coverage=round(float(coverage["generative_video_coverage"]), 4),
        motion_visual_coverage=round(float(coverage["motion_visual_coverage"]), 4),
        text_only_coverage=round(float(coverage["text_only_coverage"]), 4),
        asset_reuse_ratio=round(float(coverage["asset_reuse_ratio"]), 4),
        visual_change_interval=round(float(coverage["max_unchanged_visual_state_seconds"]), 3),
        subtitle_rhythm=round(subtitle_rhythm, 2),
        audio_continuity=round(audio_continuity, 2),
        shot_story_alignment=shot_story_alignment,
        visual_diversity=visual_diversity,
        pacing_score=pacing_score,
        editing_product_score=editing_score,
        blocking_reasons=tuple(dict.fromkeys(blocking)),
    )
