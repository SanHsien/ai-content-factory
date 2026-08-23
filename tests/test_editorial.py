from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ai_content_factory.media.editorial import (  # noqa: E402
    AssetPlanner,
    AudioBehavior,
    AudioEditor,
    CameraMotion,
    EditorialContractError,
    EditorialGateError,
    EditorialPlan,
    PaceProfile,
    ShotSize,
    ShotSpec,
    SourceType,
    SubtitleEditor,
    TimelineCompiler,
    TransitionSpec,
    evaluate_editorial_quality,
)


def shot(
    index: int,
    start: float,
    duration: float,
    source_type: SourceType,
    asset_id: str,
    *,
    motion: CameraMotion = CameraMotion.PUSH_IN,
    subtitle: str = "短句",
) -> ShotSpec:
    return ShotSpec(
        shot_id=f"shot-{index:02d}",
        purpose=f"purpose-{index}",
        start_time_seconds=start,
        duration_seconds=duration,
        source_type=source_type,
        asset_id=asset_id,
        image_prompt="a neutral synthetic image" if source_type is not SourceType.H3_VIDEO else "",
        video_prompt="one meaningful subject action" if source_type is SourceType.H3_VIDEO else "",
        subject_action="advance the narrative beat",
        shot_size=ShotSize.MS,
        camera_motion=motion if source_type is not SourceType.H3_VIDEO else CameraMotion.TRACKING,
        motion_intensity=0.25,
        crop_strategy=f"crop-{index}",
        overlay=f"label-{index}",
        voiceover_segment=subtitle,
        audio_behavior=AudioBehavior(ducking_db=-16.0),
        transition_in=TransitionSpec(),
        transition_out=TransitionSpec(),
    )


def plan(shots: list[ShotSpec], duration: float) -> EditorialPlan:
    return EditorialPlan(
        editorial_plan_id="neutral-editorial-plan",
        target_platform="vertical-short",
        target_duration_seconds=duration,
        fps=30,
        aspect_ratio="9:16",
        story_arc=("hook", "observe", "act", "close"),
        hook_strategy="open with meaningful subject motion",
        pace_profile=PaceProfile.BALANCED,
        shots=tuple(shots),
    )


def passing_plan() -> EditorialPlan:
    durations = [2.5, 2.5, 2.5, 3.0, 2.5, 2.5, 3.0, 2.5, 2.5]
    types = [
        SourceType.H3_VIDEO,
        SourceType.GENERATED_IMAGE,
        SourceType.BROLL_IMAGE,
        SourceType.H3_VIDEO,
        SourceType.GENERATED_IMAGE,
        SourceType.BROLL_IMAGE,
        SourceType.MOTION_RENDER_IMAGE,
        SourceType.H3_VIDEO,
        SourceType.BRAND_CLOSE,
    ]
    assets = ["video-a", "image-a", "image-b", "video-b", "image-c", "image-d", "image-e", "video-c", "close"]
    result = []
    start = 0.0
    for index, (duration, source_type, asset_id) in enumerate(zip(durations, types, assets), 1):
        result.append(shot(index, start, duration, source_type, asset_id))
        start += duration
    return plan(result, start)


class EditorialBrainTests(unittest.TestCase):
    def test_single_clip_then_static_cards_must_fail(self) -> None:
        shots = [shot(1, 0, 4, SourceType.H3_VIDEO, "video-a")]
        start = 4.0
        for index in range(2, 8):
            shots.append(shot(index, start, 4, SourceType.GENERATED_IMAGE, "hero"))
            start += 4
        score = evaluate_editorial_quality(plan(shots, start))
        self.assertEqual(score.status, "FAIL")
        self.assertIn("INSUFFICIENT_GENERATIVE_VIDEO_CLIPS", score.blocking_reasons)
        self.assertIn("ASSET_REUSE_TOO_HIGH", score.blocking_reasons)

    def test_static_card_over_three_seconds_must_fail(self) -> None:
        with self.assertRaises(EditorialContractError):
            shot(1, 0, 4, SourceType.TEXT_CARD, "card", motion=CameraMotion.LOCKED).validate()

    def test_insufficient_visual_assets_must_fail(self) -> None:
        candidate = passing_plan()
        reused = tuple(
            replace(item, asset_id=f"asset-{index % 4}")
            for index, item in enumerate(candidate.shots)
        )
        score = evaluate_editorial_quality(plan(list(reused), candidate.target_duration_seconds))
        self.assertIn("INSUFFICIENT_VISUAL_ASSETS", score.blocking_reasons)

    def test_text_only_coverage_too_high_must_fail(self) -> None:
        specifications = [
            (2.5, SourceType.H3_VIDEO, "video-a"),
            (2.5, SourceType.H3_VIDEO, "video-b"),
            (2.0, SourceType.GENERATED_IMAGE, "image-a"),
            (2.0, SourceType.GENERATED_IMAGE, "image-b"),
            (2.0, SourceType.GENERATED_IMAGE, "image-c"),
            (2.0, SourceType.GENERATED_IMAGE, "image-d"),
            (2.0, SourceType.GENERATED_IMAGE, "image-e"),
            (1.5, SourceType.TEXT_CARD, "text-a"),
            (1.5, SourceType.TEXT_CARD, "text-b"),
            (1.5, SourceType.TEXT_CARD, "text-c"),
            (1.0, SourceType.BRAND_CLOSE, "close"),
        ]
        shots = []
        start = 0.0
        for index, (duration, source_type, asset_id) in enumerate(specifications, 1):
            shots.append(
                shot(
                    index,
                    start,
                    duration,
                    source_type,
                    asset_id,
                    motion=CameraMotion.LOCKED if source_type is SourceType.TEXT_CARD else CameraMotion.PUSH_IN,
                )
            )
            start += duration
        score = evaluate_editorial_quality(plan(shots, start))
        self.assertGreater(score.text_only_coverage, 0.15)
        self.assertIn("TEXT_ONLY_COVERAGE_TOO_HIGH", score.blocking_reasons)

    def test_shot_density_too_low_must_fail(self) -> None:
        durations = [4.0] * 6
        shots = []
        start = 0.0
        for index, duration in enumerate(durations, 1):
            source = SourceType.H3_VIDEO if index <= 2 else SourceType.GENERATED_IMAGE
            shots.append(shot(index, start, duration, source, f"asset-{index}"))
            start += duration
        score = evaluate_editorial_quality(plan(shots, start))
        self.assertIn("SHOT_DENSITY_TOO_LOW", score.blocking_reasons)

    def test_asset_reuse_too_high_must_fail(self) -> None:
        candidate = passing_plan()
        altered = []
        for index, item in enumerate(candidate.shots):
            altered.append(replace(item, asset_id="reused" if index < 5 else item.asset_id))
        score = evaluate_editorial_quality(plan(altered, candidate.target_duration_seconds))
        self.assertIn("ASSET_REUSE_TOO_HIGH", score.blocking_reasons)

    def test_proper_hybrid_timeline_passes(self) -> None:
        candidate = passing_plan()
        cues = SubtitleEditor().compile(
            ("先看起身情境", "再看左右差異", "也看整體狀態", "觀察不是診斷"),
            0,
            candidate.target_duration_seconds,
        )
        audio = AudioEditor().compile(candidate)
        score = evaluate_editorial_quality(candidate, cues, audio)
        self.assertEqual(score.status, "PASS")
        self.assertGreaterEqual(score.editing_product_score, 8.0)
        self.assertEqual(score.max_static_hold, 0.0)
        asset_plan = AssetPlanner().plan(candidate, [shot.asset_id for shot in candidate.shots])
        timeline = TimelineCompiler().compile(candidate, asset_plan, cues, audio)
        self.assertEqual(len(timeline.shots), 9)

    def test_missing_assets_block_timeline(self) -> None:
        candidate = passing_plan()
        asset_plan = AssetPlanner().plan(candidate)
        with self.assertRaises(EditorialGateError):
            TimelineCompiler().compile(candidate, asset_plan, (), ())

    def test_subtitle_rhythm_rejects_long_phrase(self) -> None:
        with self.assertRaises(EditorialContractError):
            SubtitleEditor().compile(("這是一句明顯超過十四個中文字的字幕內容",), 0, 2)

    def test_audio_ducking_stays_below_narration(self) -> None:
        events = AudioEditor().compile(passing_plan())
        self.assertTrue(all(event.bed_gain_db <= -8.0 for event in events))

    def test_transition_duration_is_bounded(self) -> None:
        with self.assertRaises(EditorialContractError):
            TransitionSpec(kind="crossfade", duration_seconds=0.5).validate()


if __name__ == "__main__":
    unittest.main()
