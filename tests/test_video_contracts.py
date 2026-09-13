from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ai_content_factory.media.image_sources import (  # noqa: E402
    ImageProvenance,
    SyntheticImageSource,
)
from ai_content_factory.media.video_contracts import (  # noqa: E402
    GENERATIVE_I2V,
    MOTION_RENDER,
    VideoArtifact,
    VideoContractError,
    VideoGenerationMode,
    VideoRenderRequest,
)


class VideoContractTests(unittest.TestCase):
    def _hero(self, root: Path):
        return SyntheticImageSource(
            root / "images", width=16, height=12, seed="video-contract"
        ).materialize(artifact_id="hero").artifact

    def test_generation_modes_and_request_round_trip_are_provider_neutral(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hero = self._hero(root)
            request = VideoRenderRequest(
                request_id="render-contract",
                generation_mode=VideoGenerationMode.MOTION_RENDER,
                prompt="A gentle local motion treatment.",
                hero_image=hero,
                dimensions=(1080, 1920),
                duration_seconds=8,
                fps=30,
                provenance=ImageProvenance.SYNTHETIC,
                source_image_artifact_id=hero.artifact_id,
                aspect_ratio="9:16",
                motion_preset="EDITORIAL_SHORT",
                caption_mode="OPTIONAL_TEXT",
                voice_mode="NONE",
                brand_config_reference=root / "private-brand.yaml",
                output_format="mp4",
            )
            request.validate()
            payload = request.to_dict()

            self.assertEqual(request.mode.value, MOTION_RENDER)
            self.assertEqual(payload["generation_mode"], MOTION_RENDER)
            self.assertEqual(payload["hero_image"]["path"], "hero.png")
            self.assertEqual(payload["source_image_artifact_id"], hero.artifact_id)
            self.assertEqual(payload["aspect_ratio"], "9:16")
            self.assertEqual(payload["motion_preset"], "EDITORIAL_SHORT")
            self.assertEqual(payload["brand_config_reference"], "private-brand.yaml")
            self.assertNotIn(str(root), str(payload))

            restored = VideoRenderRequest.from_dict(
                payload, hero_image_path=hero.path
            )
            restored.validate()
            self.assertEqual(restored.request_id, request.request_id)
            self.assertEqual(restored.dimensions, (1080, 1920))

    def test_generative_i2v_requires_a_hero_image_but_motion_can_be_declared(self) -> None:
        motion = VideoRenderRequest(
            request_id="motion-only",
            mode=VideoGenerationMode.MOTION_RENDER,
        )
        motion.validate()

        generative = VideoRenderRequest(
            request_id="generative-without-image",
            mode=GENERATIVE_I2V,
        )
        with self.assertRaises(VideoContractError):
            generative.validate()

    def test_video_artifact_validates_file_mime_dimensions_duration_and_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "render.mp4"
            data = b"synthetic local video bytes"
            path.write_bytes(data)
            artifact = VideoArtifact.from_file(
                path,
                artifact_id="video-contract",
                mime="video/mp4",
                width=1080,
                height=1920,
                duration_seconds=8,
                generation_mode=GENERATIVE_I2V,
                provenance=ImageProvenance.PRIVATE_OWNED,
                fps=30,
            )

            artifact.validate()
            self.assertTrue(artifact.is_valid())
            self.assertEqual(artifact.mode, VideoGenerationMode.GENERATIVE_I2V)
            self.assertEqual(artifact.artifact_sha256, hashlib.sha256(data).hexdigest())
            payload = artifact.to_dict()
            self.assertEqual(payload["path"], "render.mp4")
            self.assertEqual(payload["generation_mode"], GENERATIVE_I2V)
            self.assertNotIn(str(path), str(payload))

            restored = VideoArtifact.from_dict(payload, path=path)
            restored.validate()
            self.assertEqual(restored.dimensions, (1080, 1920))

            conflicting = dict(payload)
            conflicting["output_sha256"] = "0" * 64
            with self.assertRaises(VideoContractError):
                VideoArtifact.from_dict(conflicting, path=path)

    def test_video_artifact_rejects_tampering_and_invalid_declared_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "render.mp4"
            path.write_bytes(b"video bytes")
            artifact = VideoArtifact.from_file(
                path,
                width=640,
                height=360,
                duration_seconds=2,
            )
            path.write_bytes(b"tampered video bytes")
            with self.assertRaises(VideoContractError):
                artifact.validate()

            bad_mime = VideoArtifact(
                artifact_id="bad-mime",
                path=path,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                mime="image/png",
                width=640,
                height=360,
                duration_seconds=2,
            )
            with self.assertRaises(VideoContractError):
                bad_mime.validate()

            bad_dimensions = VideoArtifact(
                artifact_id="bad-dimensions",
                path=path,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                mime="video/mp4",
                width=0,
                height=360,
                duration_seconds=2,
            )
            with self.assertRaises(VideoContractError):
                bad_dimensions.validate()

    def test_request_rejects_non_video_mime_and_bad_duration(self) -> None:
        bad_mime = VideoRenderRequest(
            request_id="bad-mime",
            output_mime="image/png",
        )
        with self.assertRaises(VideoContractError):
            bad_mime.validate()

        bad_duration = VideoRenderRequest(
            request_id="bad-duration",
            duration_seconds=0,
        )
        with self.assertRaises(VideoContractError):
            bad_duration.validate()

        bad_ratio = VideoRenderRequest(
            request_id="bad-ratio",
            aspect_ratio="16:9",
        )
        with self.assertRaises(VideoContractError):
            bad_ratio.validate()


if __name__ == "__main__":
    unittest.main()
