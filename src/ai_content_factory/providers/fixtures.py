"""Offline, deterministic provider implementations.

There are intentionally no HTTP clients, SDK imports, credentials, or media
bytes in this module.  Every implementation reads only JSON under
``fixtures/synthetic`` and returns placeholder descriptors where media would
normally be produced.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    BrandProfile,
    FixtureUnavailableError,
    MediaAsset,
    ResearchFinding,
    ResearchResult,
    TextResult,
)


DEMO_TOPIC = "Why do senior dogs slip more easily on smooth floors?"
PLATFORMS = (
    "facebook",
    "threads",
    "instagram",
    "tiktok",
    "youtube",
    "xiaohongshu",
    "douyin",
)


def default_fixture_root() -> Path:
    """Return packaged synthetic fixtures, with a source-tree fallback."""
    packaged = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic"
    if packaged.exists():
        return packaged
    return Path(__file__).resolve().parents[3] / "fixtures" / "synthetic"


def _stable_id(*parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


class _FixtureProviderBase:
    fixture_only = True

    def __init__(self, fixture_root: str | Path | None = None) -> None:
        self.fixture_root = Path(fixture_root) if fixture_root else default_fixture_root()
        if not self.fixture_root.is_dir():
            raise FixtureUnavailableError(
                f"Synthetic fixture directory does not exist: {self.fixture_root}"
            )

    def _read_json(self, filename: str) -> Mapping[str, Any]:
        path = self.fixture_root / filename
        try:
            with path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise FixtureUnavailableError(
                f"Unable to load synthetic fixture {filename}: {exc}"
            ) from exc
        if not isinstance(value, Mapping):
            raise FixtureUnavailableError(
                f"Synthetic fixture {filename} must contain a JSON object"
            )
        return value


class FixtureResearchProvider(_FixtureProviderBase):
    provider_id = "fixture-research"

    def research(
        self, topic: str, *, brand: BrandProfile | None = None
    ) -> ResearchResult:
        if not topic.strip():
            raise ValueError("topic must not be empty")
        data = self._read_json("research.json")
        if topic == str(data.get("topic", "")):
            return ResearchResult.from_dict(data)
        # The fallback remains synthetic and deterministic.  It allows the
        # contract to be exercised with a custom topic without pretending that
        # a live search occurred.
        return ResearchResult(
            topic=topic,
            summary=(
                f"Synthetic research placeholder for {topic}. "
                "Validate every factual claim before public release."
            ),
            findings=(
                ResearchFinding(
                    claim="This topic requires a source-backed explanation.",
                    why_it_matters="A fixture cannot establish current evidence.",
                ),
                ResearchFinding(
                    claim="The pipeline should preserve an explicit evidence boundary.",
                    why_it_matters="Reviewers can distinguish a demo from live research.",
                ),
            ),
        )


class FixtureTextProvider(_FixtureProviderBase):
    provider_id = "fixture-text"

    def generate(
        self,
        topic: str,
        research: ResearchResult,
        *,
        brand: BrandProfile | None = None,
    ) -> TextResult:
        if not topic.strip():
            raise ValueError("topic must not be empty")
        if research.topic != topic:
            raise ValueError("research topic does not match text topic")
        data = self._read_json("text.json")
        if topic == str(data.get("topic", "")):
            result = TextResult.from_dict(data)
            if set(result.platform_texts) == set(PLATFORMS):
                return result
        brand_name = brand.name if brand else "DemoPet"
        title = topic.rstrip("?")
        hook = f"A smooth floor can turn an ordinary step into a confidence problem for an older dog."
        script = (
            f"{hook} Start with traction: add runners or mats, keep nails and paw fur tidy, "
            "and give your dog a clear route to food, water, and rest. "
            "If slipping is new, frequent, or painful, ask a veterinarian for an assessment."
        )
        caption = (
            f"{title}. Small traction changes can make daily movement feel safer. "
            f"{brand_name} demo copy: {research.evidence_status}."
        )
        platform_texts = {
            platform: f"{title}\n\n{caption}\n\n{script}"
            for platform in PLATFORMS
        }
        return TextResult(
            topic=topic,
            title=title,
            hook=hook,
            script=script,
            caption=caption,
            platform_texts=platform_texts,
        )


class _FixtureMediaProvider(_FixtureProviderBase):
    media_type = "media"
    format = "json"

    def _media_defaults(self) -> Mapping[str, Any]:
        data = self._read_json("media.json")
        values = data.get(self.media_type, {})
        return values if isinstance(values, Mapping) else {}

    def _asset(
        self,
        prompt: str,
        *,
        topic: str | None,
        duration_seconds: int | None,
    ) -> MediaAsset:
        if not prompt.strip():
            raise ValueError("media prompt must not be empty")
        defaults = self._media_defaults()
        digest = _stable_id(self.provider_id, topic or "", prompt)
        return MediaAsset(
            asset_id=f"{self.media_type}-{digest}",
            media_type=self.media_type,
            prompt=prompt,
            provider=self.provider_id,
            format=str(defaults.get("format", self.format)),
            placeholder=True,
            duration_seconds=duration_seconds,
            metadata={
                "fixture_file": "media.json",
                "source": "synthetic-fixture",
                "topic": topic or "",
            },
        )


class FixtureImageProvider(_FixtureMediaProvider):
    provider_id = "fixture-image"
    media_type = "image"
    format = "png-placeholder"

    def generate(
        self,
        prompt: str,
        *,
        topic: str | None = None,
        brand: BrandProfile | None = None,
    ) -> MediaAsset:
        return self._asset(prompt, topic=topic, duration_seconds=None)

    create = generate


class FixtureVideoProvider(_FixtureMediaProvider):
    provider_id = "fixture-video"
    media_type = "video"
    format = "mp4-placeholder"

    def generate(
        self,
        prompt: str,
        *,
        topic: str | None = None,
        brand: BrandProfile | None = None,
    ) -> MediaAsset:
        return self._asset(prompt, topic=topic, duration_seconds=12)

    create = generate


class FixtureVoiceProvider(_FixtureMediaProvider):
    provider_id = "fixture-voice"
    media_type = "voice"
    format = "wav-placeholder"

    def generate(
        self,
        text: str,
        *,
        topic: str | None = None,
        brand: BrandProfile | None = None,
    ) -> MediaAsset:
        return self._asset(text, topic=topic, duration_seconds=18)

    synthesize = generate


class FixtureProviders:
    """Factory for the complete offline provider set."""

    fixture_only = True

    def __init__(self, fixture_root: str | Path | None = None) -> None:
        self.fixture_root = Path(fixture_root) if fixture_root else default_fixture_root()
        self.research = FixtureResearchProvider(self.fixture_root)
        self.text = FixtureTextProvider(self.fixture_root)
        self.image = FixtureImageProvider(self.fixture_root)
        self.video = FixtureVideoProvider(self.fixture_root)
        self.voice = FixtureVoiceProvider(self.fixture_root)

    def as_mapping(self) -> dict[str, Any]:
        return {
            "research": self.research,
            "text": self.text,
            "image": self.image,
            "video": self.video,
            "voice": self.voice,
        }


# Friendly aliases for callers that prefer the word "synthetic".
SyntheticResearchProvider = FixtureResearchProvider
SyntheticTextProvider = FixtureTextProvider
SyntheticImageProvider = FixtureImageProvider
SyntheticVideoProvider = FixtureVideoProvider
SyntheticVoiceProvider = FixtureVoiceProvider


__all__ = [
    "DEMO_TOPIC",
    "FixtureImageProvider",
    "FixtureProviders",
    "FixtureResearchProvider",
    "FixtureTextProvider",
    "FixtureVideoProvider",
    "FixtureVoiceProvider",
    "PLATFORMS",
    "SyntheticImageProvider",
    "SyntheticResearchProvider",
    "SyntheticTextProvider",
    "SyntheticVideoProvider",
    "SyntheticVoiceProvider",
    "default_fixture_root",
]
