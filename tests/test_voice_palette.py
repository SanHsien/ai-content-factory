from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_content_factory.providers.voice_palette import (  # noqa: E402
    VoicePalette,
    VoicePaletteEntry,
    VoiceSelectionContext,
    VoiceSelectionError,
    VoiceSelectionPolicy,
    VoiceUsageHistory,
    VoiceUsageRecord,
)


def voice(profile: str, *, gender: str, approved: bool, warmth: float, maturity: float) -> VoicePaletteEntry:
    return VoicePaletteEntry(
        voice_profile_id=profile,
        provider_id="local-test",
        engine="fixture",
        voice_id=profile,
        language="zh-TW",
        locale_style="neutral-traditional-chinese",
        gender_presentation=gender,
        warmth=warmth,
        brightness=0.6,
        maturity=maturity,
        energy=0.4,
        approved_for_production=approved,
        supported_content_styles=("narration",),
        cooldown=2,
    )


class VoicePaletteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.male = voice("male_warm_01", gender="male", approved=True, warmth=0.9, maturity=0.9)
        self.female = voice("female_warm_01", gender="female", approved=True, warmth=0.95, maturity=0.8)
        self.provisional = voice("female_review_01", gender="female", approved=False, warmth=1.0, maturity=1.0)
        self.palette = VoicePalette("test-palette", (self.male, self.female, self.provisional))
        self.policy = VoiceSelectionPolicy()

    def context(self, content_id: str = "content-001", history: tuple[str, ...] = ()) -> VoiceSelectionContext:
        return VoiceSelectionContext(
            content_id=content_id,
            topic="溫暖陪伴",
            tone="warm companionship",
            script_style="narration",
            platform="video",
            recent_voice_history=history,
        )

    def test_palette_separates_production_and_review_pools(self) -> None:
        self.assertEqual([item.voice_profile_id for item in self.palette.production_voices], ["male_warm_01", "female_warm_01"])
        self.assertEqual([item.voice_profile_id for item in self.palette.review_voices], ["female_review_01"])

    def test_selection_is_deterministic_for_same_content_and_history(self) -> None:
        first = self.policy.select(self.palette, self.context())
        second = self.policy.select(self.palette, self.context())
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_provisional_voice_is_excluded_from_production(self) -> None:
        decision = self.policy.select(self.palette, self.context())
        self.assertNotEqual(decision.selected_voice, "female_review_01")
        self.assertEqual(decision.excluded_voices["female_review_01"], "PROVISIONAL_NOT_ALLOWED_FOR_PRODUCTION")

    def test_cooldown_uses_approved_alternative(self) -> None:
        decision = self.policy.select(self.palette, self.context(history=("female_warm_01", "female_warm_01")))
        self.assertEqual(decision.selected_voice, "male_warm_01")
        self.assertEqual(decision.excluded_voices["female_warm_01"], "COOLDOWN_MAX_CONSECUTIVE_REACHED")

    def test_single_narrator_is_default_and_dialogue_requires_roles(self) -> None:
        selected = self.policy.select_narrators(self.palette, self.context())
        self.assertEqual(tuple(selected), ("narrator",))
        dialogue = VoiceSelectionContext(
            content_id="dialogue-1", topic="conversation", tone="light", script_style="dialogue",
            platform="video", script_mode="DIALOGUE"
        )
        with self.assertRaises(VoiceSelectionError):
            self.policy.select_narrators(self.palette, dialogue)
        cast = self.policy.select_narrators(self.palette, dialogue, character_roles=("guardian", "vet"))
        self.assertEqual(set(cast), {"guardian", "vet"})

    def test_no_approved_voice_fails_closed(self) -> None:
        palette = VoicePalette("review-only", (self.provisional,))
        with self.assertRaisesRegex(VoiceSelectionError, "NO_APPROVED_PRODUCTION_VOICE"):
            self.policy.select(palette, self.context())

    def test_usage_history_only_records_accepted_output_and_is_idempotent(self) -> None:
        record = VoiceUsageRecord("content-1", "2026-08-15", "male_warm_01", "warm", "threads", "shadow")
        history = VoiceUsageHistory()
        with self.assertRaises(VoiceSelectionError):
            history.append(record, accepted_output=False)
        history.append(record, accepted_output=True)
        history.append(record, accepted_output=True)
        self.assertEqual(history.recent_profile_ids(), ("male_warm_01",))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "history.json"
            history.write(output)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))[0]["content_id"], "content-1")


if __name__ == "__main__":
    unittest.main()
