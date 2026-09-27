"""Provider contracts and deterministic data objects.

The first phase deliberately keeps the provider boundary small.  Providers
return structured Python objects and do not know anything about orchestration,
publishing, network clients, or private brand storage.  The fixture providers
in :mod:`fixtures` are the only implementations shipped with this phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class BrandProfile:
    """The minimal public brand context accepted by the pipeline."""

    name: str = "DemoPet"
    tone: str = "warm, practical, evidence-aware"
    audience: str = "people caring for senior dogs"
    call_to_action: str = "Save this checklist and share it with another dog guardian."
    prohibited_claims: tuple[str, ...] = ()

    def to_dict(self) -> JsonObject:
        return {
            "audience": self.audience,
            "call_to_action": self.call_to_action,
            "name": self.name,
            "prohibited_claims": list(self.prohibited_claims),
            "tone": self.tone,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "BrandProfile":
        if not value:
            return cls()
        prohibited = value.get("prohibited_claims", ())
        if isinstance(prohibited, str):
            prohibited = (prohibited,)
        return cls(
            name=str(value.get("name", cls.name)),
            tone=str(value.get("tone", cls.tone)),
            audience=str(value.get("audience", cls.audience)),
            call_to_action=str(value.get("call_to_action", cls.call_to_action)),
            prohibited_claims=tuple(str(item) for item in prohibited),
        )


@dataclass(frozen=True)
class ResearchFinding:
    claim: str
    why_it_matters: str
    confidence: str = "fixture"

    def to_dict(self) -> JsonObject:
        return {
            "claim": self.claim,
            "confidence": self.confidence,
            "why_it_matters": self.why_it_matters,
        }


@dataclass(frozen=True)
class ResearchResult:
    topic: str
    summary: str
    findings: tuple[ResearchFinding, ...]
    source: str = "synthetic-fixture"
    evidence_status: str = "fixture-only"

    def to_dict(self) -> JsonObject:
        return {
            "evidence_status": self.evidence_status,
            "findings": [finding.to_dict() for finding in self.findings],
            "source": self.source,
            "summary": self.summary,
            "topic": self.topic,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ResearchResult":
        findings = tuple(
            ResearchFinding(
                claim=str(item.get("claim", "")),
                why_it_matters=str(item.get("why_it_matters", "")),
                confidence=str(item.get("confidence", "fixture")),
            )
            for item in value.get("findings", ())
        )
        return cls(
            topic=str(value.get("topic", "")),
            summary=str(value.get("summary", "")),
            findings=findings,
            source=str(value.get("source", "synthetic-fixture")),
            evidence_status=str(value.get("evidence_status", "fixture-only")),
        )


@dataclass(frozen=True)
class TextResult:
    topic: str
    title: str
    hook: str
    script: str
    caption: str
    platform_texts: Mapping[str, str]

    def to_dict(self) -> JsonObject:
        return {
            "caption": self.caption,
            "hook": self.hook,
            "platform_texts": {
                str(key): str(self.platform_texts[key])
                for key in sorted(self.platform_texts)
            },
            "script": self.script,
            "title": self.title,
            "topic": self.topic,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TextResult":
        platform_texts = value.get("platform_texts", {})
        if not isinstance(platform_texts, Mapping):
            platform_texts = {}
        return cls(
            topic=str(value.get("topic", "")),
            title=str(value.get("title", "")),
            hook=str(value.get("hook", "")),
            script=str(value.get("script", "")),
            caption=str(value.get("caption", "")),
            platform_texts={str(key): str(item) for key, item in platform_texts.items()},
        )


@dataclass(frozen=True)
class MediaAsset:
    """A media descriptor, never media bytes.

    ``placeholder`` is intentionally required in phase 1.  A real asset or a
    remote URI is a contract violation and is rejected by MEDIA_QA.
    """

    asset_id: str
    media_type: str
    prompt: str
    provider: str
    format: str
    placeholder: bool = True
    duration_seconds: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return {
            "asset_id": self.asset_id,
            "duration_seconds": self.duration_seconds,
            "format": self.format,
            "media_type": self.media_type,
            "metadata": {
                str(key): self.metadata[key] for key in sorted(self.metadata)
            },
            "placeholder": self.placeholder,
            "prompt": self.prompt,
            "provider": self.provider,
        }


@dataclass(frozen=True)
class MediaResult:
    assets: tuple[MediaAsset, ...]
    source: str = "synthetic-fixture"

    def to_dict(self) -> JsonObject:
        return {
            "assets": [asset.to_dict() for asset in self.assets],
            "source": self.source,
        }


@dataclass(frozen=True)
class VoiceProfile:
    """Provider-neutral narration direction owned by a private brand layer."""

    profile_id: str
    tone: tuple[str, ...] = ()
    voice_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return {
            "metadata": {str(key): self.metadata[key] for key in sorted(self.metadata)},
            "profile_id": self.profile_id,
            "tone": list(self.tone),
            "voice_id": self.voice_id,
        }


@dataclass(frozen=True)
class VoiceArtifact:
    """A materialized narration file plus reproducible provenance."""

    audio_path: str
    duration: float
    sample_rate: int
    channels: int
    sha256: str
    provider: str
    voice_id: str
    language: str
    speaking_rate: float
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return {
            "audio_path": self.audio_path,
            "channels": self.channels,
            "duration": self.duration,
            "language": self.language,
            "provider": self.provider,
            "provenance": {
                str(key): self.provenance[key] for key in sorted(self.provenance)
            },
            "sample_rate": self.sample_rate,
            "sha256": self.sha256,
            "speaking_rate": self.speaking_rate,
            "voice_id": self.voice_id,
        }


@dataclass(frozen=True)
class ProviderErrorInfo:
    code: str
    message: str
    retryable: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)


class ProviderContractError(RuntimeError):
    """Raised when an implementation breaks the local provider contract."""


class FixtureUnavailableError(ProviderContractError):
    """Raised when a required synthetic fixture cannot be loaded."""


@runtime_checkable
class ResearchProvider(Protocol):
    fixture_only: bool
    provider_id: str

    def research(
        self, topic: str, *, brand: BrandProfile | None = None
    ) -> ResearchResult:
        ...


@runtime_checkable
class TextProvider(Protocol):
    fixture_only: bool
    provider_id: str

    def generate(
        self,
        topic: str,
        research: ResearchResult,
        *,
        brand: BrandProfile | None = None,
    ) -> TextResult:
        ...


@runtime_checkable
class ImageProvider(Protocol):
    fixture_only: bool
    provider_id: str

    def generate(
        self,
        prompt: str,
        *,
        topic: str | None = None,
        brand: BrandProfile | None = None,
    ) -> MediaAsset:
        ...


@runtime_checkable
class VideoProvider(Protocol):
    fixture_only: bool
    provider_id: str

    def generate(
        self,
        prompt: str,
        *,
        topic: str | None = None,
        brand: BrandProfile | None = None,
    ) -> MediaAsset:
        ...


@runtime_checkable
class VoiceProvider(Protocol):
    fixture_only: bool
    provider_id: str

    def generate(
        self,
        text: str,
        *,
        topic: str | None = None,
        brand: BrandProfile | None = None,
    ) -> MediaAsset:
        ...

    def synthesize(
        self,
        text: str,
        language: str,
        voice_profile: VoiceProfile,
        speaking_rate: float,
        output_path: str,
    ) -> VoiceArtifact:
        ...


Provider = (
    ResearchProvider
    | TextProvider
    | ImageProvider
    | VideoProvider
    | VoiceProvider
)


__all__ = [
    "BrandProfile",
    "FixtureUnavailableError",
    "ImageProvider",
    "JsonObject",
    "MediaAsset",
    "MediaResult",
    "Provider",
    "ProviderContractError",
    "ProviderErrorInfo",
    "ResearchFinding",
    "ResearchProvider",
    "ResearchResult",
    "TextProvider",
    "TextResult",
    "VideoProvider",
    "VoiceArtifact",
    "VoiceProfile",
    "VoiceProvider",
]
