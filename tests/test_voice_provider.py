from __future__ import annotations

import sys
import tempfile
import unittest
import wave
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ai_content_factory.providers import (  # noqa: E402
    LocalCommandVoiceConfig,
    LocalCommandVoiceProvider,
    VoiceMaterializationError,
    VoiceProfile,
    inspect_wave,
)


HELPER = """\
import argparse
import wave

parser = argparse.ArgumentParser()
parser.add_argument('--text-file', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
text = open(args.text_file, encoding='utf-8').read()
if not text.strip():
    raise SystemExit(2)
with wave.open(args.output, 'wb') as stream:
    stream.setnchannels(1)
    stream.setsampwidth(2)
    stream.setframerate(8000)
    stream.writeframes(b'\\x00\\x00' * 800)
"""


class LocalVoiceProviderTests(unittest.TestCase):
    def test_materializes_valid_wave_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = root / "helper.py"
            helper.write_text(HELPER, encoding="utf-8")
            output = root / "voice.wav"
            provider = LocalCommandVoiceProvider(
                LocalCommandVoiceConfig(
                    provider_id="test-local-voice",
                    voice_id="neutral",
                    command=(
                        sys.executable,
                        str(helper),
                        "--text-file",
                        "{text_file}",
                        "--output",
                        "{output_path}",
                    ),
                )
            )
            artifact = provider.synthesize(
                "A short local narration.",
                "en-US",
                VoiceProfile(profile_id="test-profile", voice_id="test-voice"),
                1.0,
                str(output),
            )

            self.assertEqual(artifact.provider, "test-local-voice")
            self.assertEqual(artifact.voice_id, "test-voice")
            self.assertEqual(artifact.sample_rate, 8000)
            self.assertEqual(artifact.channels, 1)
            self.assertAlmostEqual(artifact.duration, 0.1)
            self.assertEqual(len(artifact.sha256), 64)
            self.assertFalse(artifact.provenance["network_fallback"])
            self.assertEqual(artifact.provenance["profile_id"], "test-profile")

    def test_invalid_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "not-wave.wav"
            path.write_text("not a wave", encoding="utf-8")
            with self.assertRaises(VoiceMaterializationError):
                inspect_wave(path)

    def test_nonzero_command_is_safely_classified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = LocalCommandVoiceProvider(
                LocalCommandVoiceConfig(
                    provider_id="failing-local-voice",
                    voice_id="none",
                    command=(sys.executable, "-c", "raise SystemExit(7)"),
                )
            )
            with self.assertRaisesRegex(
                VoiceMaterializationError, "VOICE_COMMAND_NONZERO_EXIT"
            ):
                provider.synthesize(
                    "text",
                    "en-US",
                    VoiceProfile(profile_id="test"),
                    1.0,
                    str(Path(directory) / "missing.wav"),
                )

    def test_stale_output_from_a_previous_run_is_not_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "voice.wav"
            # A valid WAV left behind by an earlier run for different text.
            with wave.open(str(output), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(8000)
                stream.writeframes(b"\x00\x00" * 800)
            provider = LocalCommandVoiceProvider(
                LocalCommandVoiceConfig(
                    provider_id="test-local-voice",
                    voice_id="neutral",
                    # Exits 0 but writes nothing.
                    command=(sys.executable, "-c", "pass"),
                )
            )
            with self.assertRaisesRegex(VoiceMaterializationError, "VOICE_OUTPUT_MISSING_OR_EMPTY"):
                provider.synthesize(
                    "new text", "en-US", VoiceProfile(profile_id="test"), 1.0, str(output)
                )


if __name__ == "__main__":
    unittest.main()
