from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ai_content_factory.media.motion_render import (  # noqa: E402
    DEFAULT_TEMPLATE_PATH,
    MotionPreset,
    MotionRenderError,
    MotionRenderErrorCode,
    MotionRenderVideoProvider,
    _offline_process_env,
)
from ai_content_factory.media.image_sources import (  # noqa: E402
    ImageProvenance,
    SyntheticImageSource,
)
from ai_content_factory.media.video_contracts import (  # noqa: E402
    VideoGenerationMode,
    VideoRenderRequest,
)


class MotionRenderProviderTests(unittest.TestCase):
    def _source(self, root: Path, name: str = "private-input.svg") -> Path:
        path = root / name
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="#789"/></svg>',
            encoding="utf-8",
        )
        return path

    def _ffprobe_payload(self) -> str:
        return json.dumps(
            {
                "format": {"duration": "8.000000"},
                "streams": [
                    {
                        "avg_frame_rate": "30/1",
                        "codec_type": "video",
                        "duration": "8.000000",
                        "height": 1920,
                        "width": 1080,
                    }
                ],
            }
        )

    def test_renderer_environment_is_offline_and_excludes_arbitrary_secrets(self) -> None:
        with patch.dict(
            os.environ,
            {"EXAMPLE_API_KEY": "must-not-pass", "PATH": "local-tools"},
            clear=True,
        ):
            environment = _offline_process_env()
        self.assertEqual(environment["npm_config_offline"], "true")
        self.assertEqual(environment["NO_UPDATE_NOTIFIER"], "1")
        self.assertEqual(environment["PATH"], "local-tools")
        self.assertNotIn("EXAMPLE_API_KEY", environment)

    def test_create_job_is_deterministic_and_does_not_start_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._source(root)
            runner = Mock()
            provider = MotionRenderVideoProvider(
                template_path=DEFAULT_TEMPLATE_PATH,
                runner=runner,
                timeout_seconds=None,
            )

            first = provider.create_job(
                source,
                output_dir=root / "out",
                preset=MotionPreset.SLOW_PAN,
                hook="A & B",
                subtitle="Safe <local> motion",
                cta="Review locally",
            )
            second = provider.create_job(
                source,
                output_dir=root / "out",
                preset="SLOW_PAN",
                hook="A & B",
                subtitle="Safe <local> motion",
                cta="Review locally",
            )

            self.assertFalse(runner.called)
            self.assertEqual(first.job_id, second.job_id)
            self.assertEqual(first.composition_sha256, second.composition_sha256)
            self.assertEqual(first.source_image_path.name, "source-image.svg")
            composition = first.composition_path.read_text(encoding="utf-8")
            self.assertIn('data-width="1080"', composition)
            self.assertIn('data-height="1920"', composition)
            self.assertIn('data-fps="30"', composition)
            self.assertIn('data-duration="8"', composition)
            self.assertIn('class="preset-SLOW_PAN"', composition)
            self.assertIn('src="source-image.svg"', composition)
            self.assertIn("A &amp; B", composition)
            self.assertIn("Safe &lt;local&gt; motion", composition)
            self.assertNotIn("__HOOK__", composition)

    def test_render_runs_required_commands_and_writes_local_qa_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._source(root)
            calls: list[list[str]] = []

            def runner(command: list[str], **kwargs):
                calls.append(command)
                if "render" in command:
                    Path(kwargs["cwd"]) .joinpath("render.mp4").write_bytes(b"synthetic-local-mp4")
                if command and command[0] == "ffprobe":
                    return type("Result", (), {"returncode": 0, "stdout": self._ffprobe_payload(), "stderr": ""})()
                return type("Result", (), {"returncode": 0, "stdout": "{}", "stderr": ""})()

            provider = MotionRenderVideoProvider(
                template_path=DEFAULT_TEMPLATE_PATH,
                runner=runner,
                timeout_seconds=None,
            )
            with patch("ai_content_factory.media.motion_render.shutil.which", return_value="ffprobe"):
                artifact = provider.render(
                    source_image=source,
                    output_dir=root / "out",
                    preset=MotionPreset.EDITORIAL_SHORT,
                )

            self.assertEqual([command[4] for command in calls[:4]], ["lint", "validate", "inspect", "render"])
            self.assertTrue(
                all(
                    command[:4]
                    == ["npx", "--offline", "--yes", "hyperframes@0.7.106"]
                    for command in calls[:4]
                )
            )
            self.assertEqual(calls[4][0], "ffprobe")
            self.assertEqual(artifact.preset, "EDITORIAL_SHORT")
            self.assertTrue(artifact.path.is_file())
            self.assertTrue(artifact.provenance_path.is_file())
            self.assertTrue(artifact.qa_path.is_file())

            qa = json.loads(artifact.qa_path.read_text(encoding="utf-8"))
            provenance = json.loads(artifact.provenance_path.read_text(encoding="utf-8"))
            self.assertEqual(qa["status"], "PASS")
            self.assertEqual(qa["evidence_status"], "LOCAL_VERIFIED")
            self.assertEqual(qa["ffprobe"]["fps"], 30.0)
            self.assertEqual(provenance["output"]["sha256"], artifact.sha256)
            self.assertEqual(provenance["input"]["path"], "source-image.svg")
            self.assertNotIn(str(source), json.dumps(provenance))
            self.assertNotIn("OPENAI_API_KEY", json.dumps(provenance))
            self.assertEqual(artifact.review_state, "MANUAL_REVIEW_REQUIRED")

    def test_render_records_unverified_ffprobe_boundary_when_tool_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._source(root)

            def runner(command: list[str], **kwargs):
                if "render" in command:
                    Path(kwargs["cwd"]).joinpath("render.mp4").write_bytes(b"synthetic-local-mp4")
                return type("Result", (), {"returncode": 0, "stdout": "{}", "stderr": ""})()

            provider = MotionRenderVideoProvider(
                template_path=DEFAULT_TEMPLATE_PATH,
                runner=runner,
                timeout_seconds=None,
            )
            with patch("ai_content_factory.media.motion_render.shutil.which", return_value=None):
                artifact = provider.render(source_image=source, output_dir=root / "out")

            qa = json.loads(artifact.qa_path.read_text(encoding="utf-8"))
            self.assertEqual(qa["status"], "FAIL")
            self.assertEqual(qa["evidence_status"], "FFPROBE_REQUIRED")
            self.assertFalse(qa["ffprobe"]["validated"])

    def test_provider_neutral_contract_bridge_returns_verified_video_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hero = SyntheticImageSource(root / "images", width=48, height=64).materialize(
                artifact_id="neutral-hero"
            ).artifact

            def runner(command: list[str], **kwargs):
                if "render" in command:
                    Path(kwargs["cwd"]).joinpath("public_demo.mp4").write_bytes(
                        b"synthetic-local-mp4"
                    )
                if command and command[0] == "ffprobe":
                    return type(
                        "Result",
                        (),
                        {"returncode": 0, "stdout": self._ffprobe_payload(), "stderr": ""},
                    )()
                return type("Result", (), {"returncode": 0, "stdout": "{}", "stderr": ""})()

            provider = MotionRenderVideoProvider(
                template_path=DEFAULT_TEMPLATE_PATH,
                runner=runner,
                timeout_seconds=None,
            )
            request = VideoRenderRequest(
                request_id="contract-bridge",
                generation_mode=VideoGenerationMode.MOTION_RENDER,
                prompt="Neutral local motion.",
                hero_image=hero,
                motion_preset="EDITORIAL_SHORT",
                provenance=ImageProvenance.SYNTHETIC,
                metadata={
                    "hook": "Small changes",
                    "subtitle": "A local motion example",
                    "output_name": "public_demo.mp4",
                },
            )
            with patch("ai_content_factory.media.motion_render.shutil.which", return_value="ffprobe"):
                artifact = provider.render_contract(request, output_dir=root / "out")

            self.assertEqual(artifact.generation_mode, VideoGenerationMode.MOTION_RENDER)
            self.assertEqual(artifact.metadata["review_state"], "MANUAL_REVIEW_REQUIRED")
            self.assertEqual(artifact.metadata["source_image_artifact_id"], "neutral-hero")
            self.assertEqual(artifact.source_image_sha256, hero.sha256)
            self.assertEqual(artifact.output_sha256, artifact.sha256)
            self.assertEqual(artifact.renderer, "hyperframes")
            self.assertEqual(artifact.renderer_version, "0.7.106")
            self.assertEqual(artifact.preset, "EDITORIAL_SHORT")
            self.assertTrue(artifact.created_at)
            self.assertTrue(artifact.path.is_file())

    def test_missing_renderer_is_structured_and_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._source(root)
            provider = MotionRenderVideoProvider(
                template_path=DEFAULT_TEMPLATE_PATH,
                runner=Mock(side_effect=FileNotFoundError("secret/private/npx")),
                timeout_seconds=None,
            )

            with self.assertRaises(MotionRenderError) as context:
                provider.render(source_image=source, output_dir=root / "out")

            error = context.exception
            self.assertEqual(error.error_code, MotionRenderErrorCode.RENDERER_MISSING)
            self.assertEqual(error.failure.stage, "lint")
            self.assertNotIn("secret/private/npx", str(error))
            self.assertEqual(error.to_dict()["details"], {})

    def test_render_failure_does_not_leak_process_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._source(root)
            calls = 0

            def runner(command: list[str], **kwargs):
                nonlocal calls
                calls += 1
                if "render" in command:
                    return type(
                        "Result",
                        (),
                        {
                            "returncode": 1,
                            "stdout": "sensitive-renderer-marker",
                            "stderr": "renderer failure at a private location",
                        },
                    )()
                return type("Result", (), {"returncode": 0, "stdout": "{}", "stderr": ""})()

            provider = MotionRenderVideoProvider(
                template_path=DEFAULT_TEMPLATE_PATH,
                runner=runner,
                timeout_seconds=None,
            )
            with self.assertRaises(MotionRenderError) as context:
                provider.render(source_image=source, output_dir=root / "out")

            error = context.exception
            self.assertEqual(error.error_code, MotionRenderErrorCode.RENDER_FAILED)
            self.assertEqual(error.failure.stage, "render")
            self.assertEqual(calls, 4)
            self.assertNotIn("sensitive-renderer-marker", str(error))
            self.assertNotIn("renderer failure at a private location", json.dumps(error.to_dict()))

    def test_generate_requires_explicit_render_and_does_not_start_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._source(root)
            runner = Mock()
            provider = MotionRenderVideoProvider(template_path=DEFAULT_TEMPLATE_PATH, runner=runner)

            with self.assertRaises(MotionRenderError) as context:
                provider.generate(source_image=source, output_dir=root / "out")

            self.assertEqual(context.exception.error_code, MotionRenderErrorCode.RENDER_EXPLICIT_REQUIRED)
            self.assertFalse(runner.called)


if __name__ == "__main__":
    unittest.main()
