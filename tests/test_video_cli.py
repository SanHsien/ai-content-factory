from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ai_content_factory.cli import build_parser, main  # noqa: E402
from ai_content_factory.media.image_sources import (  # noqa: E402
    ImageProvenance,
    SyntheticImageSource,
)
from ai_content_factory.media.video_contracts import (  # noqa: E402
    VideoArtifact,
    VideoGenerationMode,
)


class VideoCliTests(unittest.TestCase):
    def test_render_video_parser_is_explicit_and_offline_by_default(self) -> None:
        args = build_parser().parse_args(
            [
                "render-video",
                "--image",
                "hero.png",
                "--output",
                "out",
            ]
        )
        self.assertEqual(args.command, "render-video")
        self.assertEqual(args.duration, 8.0)
        self.assertEqual(args.preset, "GENTLE_PUSH_IN")
        self.assertFalse(args.no_network)

    def test_render_video_cli_emits_manual_review_artifact_without_live_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hero = SyntheticImageSource(root / "images", width=24, height=32).materialize(
                artifact_id="cli-hero"
            ).artifact

            def render_contract(provider, request, *, output_dir):
                del provider
                output = Path(output_dir) / "job-cli"
                output.mkdir(parents=True)
                video = output / "public_demo.mp4"
                video.write_bytes(b"local-test-video")
                return VideoArtifact.from_file(
                    video,
                    artifact_id="video-cli",
                    width=1080,
                    height=1920,
                    duration_seconds=8,
                    generation_mode=VideoGenerationMode.MOTION_RENDER,
                    provenance=request.provenance,
                    fps=30,
                    metadata={"review_state": "MANUAL_REVIEW_REQUIRED"},
                )

            stream = io.StringIO()
            with patch(
                "ai_content_factory.media.motion_render.MotionRenderVideoProvider.render_contract",
                autospec=True,
                side_effect=render_contract,
            ), patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(stream):
                exit_code = main(
                    [
                        "render-video",
                        "--image",
                        str(hero.path),
                        "--output",
                        str(root / "out"),
                        "--provenance",
                        ImageProvenance.SYNTHETIC.value,
                        "--no-network",
                    ]
                )
                self.assertFalse("OPENAI_API_KEY" in os.environ)

            payload = json.loads(stream.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["generation_mode"], "MOTION_RENDER")
            self.assertEqual(payload["network"], "DISABLED")
            self.assertEqual(payload["status"], "MANUAL_REVIEW_REQUIRED")
            self.assertTrue((root / "out" / "job-cli" / "video_artifact.json").is_file())

    def test_render_video_cli_rejects_missing_private_brand_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hero = SyntheticImageSource(root / "images", width=24, height=32).materialize(
                artifact_id="cli-hero"
            ).artifact
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                exit_code = main(
                    [
                        "render-video",
                        "--image",
                        str(hero.path),
                        "--output",
                        str(root / "out"),
                        "--brand-config",
                        str(root / "missing.yaml"),
                    ]
                )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stream.getvalue())["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
