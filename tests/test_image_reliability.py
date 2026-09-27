from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from ai_content_factory.media.image_reliability import (  # noqa: E402
    ImageJobState,
    SubmissionReceipt,
    materialize_verified_image,
    wait_for_stable_file,
)


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def png_bytes(width: int = 256, height: int = 256) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + b"\x72\x82\x91" * width
    return b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr) + png_chunk(b"IDAT", zlib.compress(row * height)) + png_chunk(b"IEND", b"")


class ImageReliabilityTests(unittest.TestCase):
    def test_receipt_is_secret_free_durable_and_single_submission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt = SubmissionReceipt.create(
                job_id="job-one",
                content_id="content-one",
                provider="fixture-image",
                submission_timestamp="2026-08-15T00:00:00Z",
                prompt="private prompt body",
                expected_local_output_contract=Path(temporary) / "image.png",
                expected_aspect_ratio="3:4",
            )
            path = receipt.persist(Path(temporary) / "submission-receipt.json")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["provider_submission_count"], 1)
            self.assertEqual(payload["reconciliation_state"], ImageJobState.SUBMITTED)
            self.assertNotIn("private prompt body", path.read_text(encoding="utf-8"))
            with self.assertRaises(ValueError):
                SubmissionReceipt.create(
                    job_id="job-one",
                    content_id="content-one",
                    provider="fixture-image",
                    submission_timestamp="2026-08-15T00:00:00Z",
                    prompt="prompt",
                    expected_local_output_contract=Path(temporary) / "image.png",
                    provider_submission_count=2,
                )

    def test_partial_file_never_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "partial.png"
            path.write_bytes(b"partial")
            self.assertFalse(wait_for_stable_file(path, observation_window_seconds=0, minimum_bytes=1))

    def test_stable_file_materializes_verified_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "image.png"
            path.write_bytes(png_bytes())
            receipt = SubmissionReceipt.create(
                job_id="job-ready",
                content_id="content-ready",
                provider="fixture-image",
                submission_timestamp="2026-08-15T00:00:00Z",
                prompt="safe synthetic image",
                expected_local_output_contract=path,
            )
            artifact = materialize_verified_image(
                receipt,
                observation_window_seconds=0.1,
                interval_seconds=0.001,
                stable_observations=2,
                minimum_bytes=10,
            )
            self.assertIsNotNone(artifact)
            self.assertEqual((artifact.width, artifact.height), (256, 256))
            self.assertEqual(len(artifact.sha256), 64)


if __name__ == "__main__":
    unittest.main()
