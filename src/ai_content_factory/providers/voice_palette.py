"""Provider-neutral voice palette and deterministic contextual selection."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .contracts import ProviderContractError


class VoiceSelectionError(ProviderContractError):
    """Raised when no policy-compliant voice can be selected."""


def _bounded(value: float, name: str) -> float:
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return number


@dataclass(frozen=True, slots=True)
class VoicePaletteEntry:
    voice_profile_id: str
    provider_id: str
    engine: str
    voice_id: str
    language: str
    locale_style: str
    gender_presentation: str
    warmth: float
    brightness: float
    maturity: float
    energy: float
    speaking_rate: float = 1.0
    pitch_strategy: str = "provider_default"
    approved_for_production: bool = False
    supported_content_styles: tuple[str, ...] = ()
    cooldown: int = 2
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        required = {
            "voice_profile_id": self.voice_profile_id,
            "provider_id": self.provider_id,
            "engine": self.engine,
            "voice_id": self.voice_id,
            "language": self.language,
            "locale_style": self.locale_style,
            "gender_presentation": self.gender_presentation,
        }
        for name, value in required.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")
        for name in ("warmth", "brightness", "maturity", "energy"):
            object.__setattr__(self, name, _bounded(getattr(self, name), name))
        if not 0.5 <= float(self.speaking_rate) <= 2.0:
            raise ValueError("speaking_rate must be between 0.5 and 2.0")
        if self.cooldown < 0:
            raise ValueError("cooldown cannot be negative")
        object.__setattr__(
            self,
            "supported_content_styles",
            tuple(str(item).strip().lower() for item in self.supported_content_styles if str(item).strip()),
        )
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved_for_production": self.approved_for_production,
            "brightness": self.brightness,
            "cooldown": self.cooldown,
            "energy": self.energy,
            "engine": self.engine,
            "gender_presentation": self.gender_presentation,
            "language": self.language,
            "locale_style": self.locale_style,
            "maturity": self.maturity,
            "metadata": {str(key): self.metadata[key] for key in sorted(self.metadata)},
            "pitch_strategy": self.pitch_strategy,
            "provider_id": self.provider_id,
            "speaking_rate": self.speaking_rate,
            "supported_content_styles": list(self.supported_content_styles),
            "voice_id": self.voice_id,
            "voice_profile_id": self.voice_profile_id,
            "warmth": self.warmth,
        }


@dataclass(frozen=True, slots=True)
class VoicePalette:
    palette_id: str
    voices: tuple[VoicePaletteEntry, ...]
    policy_version: str = "contextual-rotation-v1"

    def __post_init__(self) -> None:
        if not self.palette_id.strip() or not self.voices:
            raise ValueError("palette_id and voices are required")
        object.__setattr__(self, "voices", tuple(self.voices))
        identifiers = [voice.voice_profile_id for voice in self.voices]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("voice_profile_id values must be unique")

    @property
    def production_voices(self) -> tuple[VoicePaletteEntry, ...]:
        return tuple(voice for voice in self.voices if voice.approved_for_production)

    @property
    def review_voices(self) -> tuple[VoicePaletteEntry, ...]:
        return tuple(voice for voice in self.voices if not voice.approved_for_production)

    def to_dict(self) -> dict[str, Any]:
        return {
            "palette_id": self.palette_id,
            "policy_version": self.policy_version,
            "production_voice_pool": [voice.voice_profile_id for voice in self.production_voices],
            "review_voice_pool": [voice.voice_profile_id for voice in self.review_voices],
            "voices": [voice.to_dict() for voice in self.voices],
        }


@dataclass(frozen=True, slots=True)
class VoiceUsageRecord:
    content_id: str
    date: str
    voice_profile_id: str
    tone: str
    platform: str
    published_or_shadow: str

    def to_dict(self) -> dict[str, str]:
        return {
            "content_id": self.content_id,
            "date": self.date,
            "platform": self.platform,
            "published_or_shadow": self.published_or_shadow,
            "tone": self.tone,
            "voice_profile_id": self.voice_profile_id,
        }


class VoiceUsageHistory:
    """Small JSON ledger that records only accepted materialized outputs."""

    def __init__(self, records: Iterable[VoiceUsageRecord] = ()) -> None:
        self._records = list(records)

    @property
    def records(self) -> tuple[VoiceUsageRecord, ...]:
        return tuple(self._records)

    def append(self, record: VoiceUsageRecord, *, accepted_output: bool) -> None:
        if not accepted_output:
            raise VoiceSelectionError("VOICE_HISTORY_REQUIRES_ACCEPTED_OUTPUT")
        if any(item.content_id == record.content_id for item in self._records):
            return
        self._records.append(record)

    def recent_profile_ids(self, limit: int = 10) -> tuple[str, ...]:
        return tuple(item.voice_profile_id for item in self._records[-limit:])

    def write(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps([item.to_dict() for item in self._records], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


@dataclass(frozen=True, slots=True)
class VoiceSelectionContext:
    content_id: str
    topic: str
    tone: str
    script_style: str
    platform: str
    recent_voice_history: tuple[str, ...] = ()
    script_mode: str = "NARRATION"

    def __post_init__(self) -> None:
        if not self.content_id.strip() or not self.platform.strip():
            raise ValueError("content_id and platform are required")
        object.__setattr__(self, "recent_voice_history", tuple(self.recent_voice_history))


@dataclass(frozen=True, slots=True)
class VoiceDecision:
    content_id: str
    candidate_voices: tuple[str, ...]
    excluded_voices: Mapping[str, str]
    selected_voice: str
    selection_reason: str
    recent_history: tuple[str, ...]
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_voices": list(self.candidate_voices),
            "content_id": self.content_id,
            "excluded_voices": dict(sorted(self.excluded_voices.items())),
            "policy_version": self.policy_version,
            "recent_history": list(self.recent_history),
            "selected_voice": self.selected_voice,
            "selection_reason": self.selection_reason,
        }

    def write(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


class VoiceSelectionPolicy:
    """Choose one stable narrator using tone fit, approval and cooldown."""

    def __init__(self, *, mode: str = "CONTEXTUAL_ROTATION") -> None:
        if mode != "CONTEXTUAL_ROTATION":
            raise ValueError("only CONTEXTUAL_ROTATION is supported")
        self.mode = mode

    @staticmethod
    def _tone_score(voice: VoicePaletteEntry, context: VoiceSelectionContext) -> float:
        words = " ".join((context.topic, context.tone, context.script_style)).lower()
        if any(term in words for term in ("warm", "emotional", "companionship", "溫暖", "陪伴", "安心")):
            score = voice.warmth * 4 + voice.maturity * 2 + (0.35 if "female" in voice.gender_presentation.lower() else 0.15)
        elif any(term in words for term in ("safety", "red flag", "warning", "安全", "警示", "危險")):
            score = voice.maturity * 4 + voice.warmth * 2 - voice.energy
        elif any(term in words for term in ("light", "conversational", "輕鬆", "對話")):
            score = voice.brightness * 3 + voice.energy * 2 + voice.warmth
        else:
            score = voice.maturity * 2 + voice.warmth * 2 + voice.brightness
        style = context.script_style.strip().lower()
        if voice.supported_content_styles and style in voice.supported_content_styles:
            score += 1.0
        return score

    @staticmethod
    def _stable_tiebreak(content_id: str, policy_version: str, profile_id: str) -> int:
        payload = f"{content_id}|{policy_version}|{profile_id}".encode("utf-8")
        return int(hashlib.sha256(payload).hexdigest(), 16)

    def select(
        self,
        palette: VoicePalette,
        context: VoiceSelectionContext,
        *,
        require_production_approval: bool = True,
    ) -> VoiceDecision:
        eligible = list(palette.production_voices if require_production_approval else palette.voices)
        excluded = {
            voice.voice_profile_id: "PROVISIONAL_NOT_ALLOWED_FOR_PRODUCTION"
            for voice in palette.review_voices
            if require_production_approval
        }
        if not eligible:
            raise VoiceSelectionError("NO_APPROVED_PRODUCTION_VOICE")

        for voice in tuple(eligible):
            if voice.cooldown <= 0 or len(context.recent_voice_history) < voice.cooldown:
                continue
            if all(item == voice.voice_profile_id for item in context.recent_voice_history[-voice.cooldown:]):
                alternatives = [item for item in eligible if item.voice_profile_id != voice.voice_profile_id]
                if alternatives:
                    eligible.remove(voice)
                    excluded[voice.voice_profile_id] = "COOLDOWN_MAX_CONSECUTIVE_REACHED"

        ranked = sorted(
            eligible,
            key=lambda voice: (
                self._tone_score(voice, context),
                self._stable_tiebreak(context.content_id, palette.policy_version, voice.voice_profile_id),
            ),
            reverse=True,
        )
        selected = ranked[0]
        reason = "tone_fit_then_deterministic_content_tiebreak"
        if len(ranked) == 1:
            reason = "only_policy_eligible_voice"
        return VoiceDecision(
            content_id=context.content_id,
            candidate_voices=tuple(voice.voice_profile_id for voice in ranked),
            excluded_voices=excluded,
            selected_voice=selected.voice_profile_id,
            selection_reason=reason,
            recent_history=context.recent_voice_history,
            policy_version=palette.policy_version,
        )

    def select_narrators(
        self,
        palette: VoicePalette,
        context: VoiceSelectionContext,
        *,
        character_roles: Sequence[str] = (),
    ) -> Mapping[str, str]:
        decision = self.select(palette, context, require_production_approval=True)
        if context.script_mode.upper() != "DIALOGUE":
            return {"narrator": decision.selected_voice}
        roles = tuple(role.strip() for role in character_roles if role.strip())
        if not roles:
            raise VoiceSelectionError("DIALOGUE_REQUIRES_EXPLICIT_CHARACTER_ROLES")
        approved = palette.production_voices
        return {
            role: approved[index % len(approved)].voice_profile_id
            for index, role in enumerate(roles)
        }


__all__ = [
    "VoiceDecision",
    "VoicePalette",
    "VoicePaletteEntry",
    "VoiceSelectionContext",
    "VoiceSelectionError",
    "VoiceSelectionPolicy",
    "VoiceUsageHistory",
    "VoiceUsageRecord",
]
