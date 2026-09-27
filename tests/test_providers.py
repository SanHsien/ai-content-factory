from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ai_content_factory.providers import (  # noqa: E402
    DEMO_TOPIC,
    PLATFORMS,
    FixtureImageProvider,
    FixtureProviders,
    FixtureResearchProvider,
    FixtureTextProvider,
    FixtureVideoProvider,
    FixtureVoiceProvider,
    ImageProvider,
    ResearchProvider,
    TextProvider,
    VideoProvider,
    VoiceProvider,
)


class ProviderContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.providers = FixtureProviders().as_mapping()

    def test_all_shipped_providers_are_fixture_only_contracts(self) -> None:
        self.assertIsInstance(self.providers["research"], ResearchProvider)
        self.assertIsInstance(self.providers["text"], TextProvider)
        self.assertIsInstance(self.providers["image"], ImageProvider)
        self.assertIsInstance(self.providers["video"], VideoProvider)
        self.assertIsInstance(self.providers["voice"], VoiceProvider)
        for provider in self.providers.values():
            self.assertTrue(provider.fixture_only)
            self.assertTrue(provider.provider_id.startswith("fixture-"))

    def test_research_and_text_are_deterministic_and_use_exact_demo_topic(self) -> None:
        research_provider: FixtureResearchProvider = self.providers["research"]
        text_provider: FixtureTextProvider = self.providers["text"]
        first_research = research_provider.research(DEMO_TOPIC)
        second_research = research_provider.research(DEMO_TOPIC)
        self.assertEqual(first_research.to_dict(), second_research.to_dict())
        self.assertEqual(first_research.topic, DEMO_TOPIC)
        self.assertEqual(first_research.evidence_status, "fixture-only")

        first_text = text_provider.generate(DEMO_TOPIC, first_research)
        second_text = text_provider.generate(DEMO_TOPIC, second_research)
        self.assertEqual(first_text.to_dict(), second_text.to_dict())
        self.assertEqual(set(first_text.platform_texts), set(PLATFORMS))
        self.assertEqual(len(first_text.platform_texts), 7)

    def test_media_providers_return_descriptors_not_real_media(self) -> None:
        image_provider: FixtureImageProvider = self.providers["image"]
        video_provider: FixtureVideoProvider = self.providers["video"]
        voice_provider: FixtureVoiceProvider = self.providers["voice"]
        image_a = image_provider.generate("senior dog on a runner", topic=DEMO_TOPIC)
        image_b = image_provider.generate("senior dog on a runner", topic=DEMO_TOPIC)
        self.assertEqual(image_a.to_dict(), image_b.to_dict())
        self.assertTrue(image_a.placeholder)
        self.assertEqual(image_a.media_type, "image")
        self.assertTrue(video_provider.generate("traction explainer", topic=DEMO_TOPIC).placeholder)
        self.assertTrue(voice_provider.generate("fixture narration", topic=DEMO_TOPIC).placeholder)
        for asset in (image_a, video_provider.generate("traction explainer", topic=DEMO_TOPIC), voice_provider.generate("fixture narration", topic=DEMO_TOPIC)):
            self.assertNotIn("url", asset.to_dict())
            self.assertNotIn("uri", asset.to_dict())


if __name__ == "__main__":
    unittest.main()
