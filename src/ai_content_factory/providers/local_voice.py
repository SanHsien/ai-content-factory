"""Generic local-command voice materialization with WAV integrity checks."""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .contracts import ProviderContractError, VoiceArtifact, VoiceProfile


class VoiceMaterializationError(ProviderContractError):
    """Raised when a local voice process does not produce a valid WAV file."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_wave(path: str | Path) -> tuple[float, int, int, str]:
    """Return duration, sample rate, channels, and SHA-256 for a PCM WAV."""

    resolved = Path(path).resolve()
    if not resolved.is_file() or resolved.stat().st_size <= 44:
        raise VoiceMaterializationError("VOICE_OUTPUT_MISSING_OR_EMPTY")
    try:
        with wave.open(str(resolved), "rb") as stream:
            frames = stream.getnframes()
            sample_rate = stream.getframerate()
            channels = stream.getnchannels()
    except (OSError, EOFError, wave.Error) as exc:
        raise VoiceMaterializationError("VOICE_OUTPUT_INVALID_WAV") from exc
    if frames <= 0 or sample_rate <= 0 or channels <= 0:
        raise VoiceMaterializationError("VOICE_OUTPUT_INVALID_METADATA")
    return frames / sample_rate, sample_rate, channels, _sha256(resolved)


@dataclass(frozen=True)
class LocalCommandVoiceConfig:
    provider_id: str
    command: tuple[str, ...]
    voice_id: str
    environment: Mapping[str, str] | None = None
    timeout_seconds: float = 180.0


class LocalCommandVoiceProvider:
    """Run an explicitly configured local synthesizer without adding dependencies.

    Command entries may use ``{text_file}``, ``{output_path}``, ``{language}``,
    ``{voice_id}``, and ``{speaking_rate}``. The adapter never discovers a
    command, downloads a model, or falls back to a network service.
    """

    fixture_only = False

    def __init__(self, config: LocalCommandVoiceConfig) -> None:
        if not config.provider_id.strip() or not config.command:
            raise ValueError("provider_id and command are required")
        self.config = config
        self.provider_id = config.provider_id

    def synthesize(
        self,
        text: str,
        language: str,
        voice_profile: VoiceProfile,
        speaking_rate: float,
        output_path: str,
    ) -> VoiceArtifact:
        if not text.strip():
            raise ValueError("voice text must not be empty")
        if not language.strip():
            raise ValueError("language must not be empty")
        if not 0.5 <= speaking_rate <= 2.0:
            raise ValueError("speaking_rate must be between 0.5 and 2.0")

        output = Path(output_path).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        voice_id = voice_profile.voice_id or self.config.voice_id
        with tempfile.TemporaryDirectory(prefix="aicf-voice-") as directory:
            text_file = Path(directory) / "narration.txt"
            text_file.write_text(text, encoding="utf-8")
            values = {
                "language": language,
                "output_path": str(output),
                "speaking_rate": str(speaking_rate),
                "text_file": str(text_file),
                "voice_id": voice_id,
            }
            command = [part.format_map(values) for part in self.config.command]
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    env=dict(self.config.environment) if self.config.environment else None,
                    text=True,
                    timeout=self.config.timeout_seconds,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise VoiceMaterializationError("VOICE_COMMAND_EXECUTION_FAILED") from exc
            if completed.returncode != 0:
                raise VoiceMaterializationError("VOICE_COMMAND_NONZERO_EXIT")

        duration, sample_rate, channels, digest = inspect_wave(output)
        return VoiceArtifact(
            audio_path=str(output),
            duration=round(duration, 6),
            sample_rate=sample_rate,
            channels=channels,
            sha256=digest,
            provider=self.provider_id,
            voice_id=voice_id,
            language=language,
            speaking_rate=speaking_rate,
            provenance={
                "execution": "explicit-local-command",
                "network_fallback": False,
                "profile_id": voice_profile.profile_id,
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            },
        )

    def generate(self, *args, **kwargs) -> VoiceArtifact:
        return self.synthesize(*args, **kwargs)


__all__ = [
    "LocalCommandVoiceConfig",
    "LocalCommandVoiceProvider",
    "VoiceMaterializationError",
    "inspect_wave",
]
