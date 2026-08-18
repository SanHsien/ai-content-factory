from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ai_content_factory.media.image_sources import (  # noqa: E402
    CHATGPT_HANDOFF,
    CODEX_NATIVE,
    PRIVATE_OWNED,
    SYNTHETIC,
    ChatGPTHandoffImageSource,
    CodexNativeImageSource,
    HeroImageArtifact,
    ImageProvenance,
    ImageValidationError,
    MaterializationStatus,
    SyntheticImageSource,
    validate_image_file,
)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return (
        struct.pack(">I", len(payload))
        + body
        + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    )


def _png_bytes(width: int = 4, height: int = 3) -> bytes:
    row = b"\x00" + bytes((32, 96, 160, 255)) * width
    raw = row * height
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


def _jpeg_bytes(width: int = 7, height: int = 5) -> bytes:
    app0 = (
        b"\xff\xe0"
        + struct.pack(">H", 16)
        + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    )
    sof0 = (
        b"\xff\xc0"
        + struct.pack(">H", 17)
        + bytes([8])
        + struct.pack(">HH", height, width)
        + bytes([3, 1, 0x11, 0, 2, 0x11, 0, 3, 0x11, 0])
    )
    sos = (
        b"\xff\xda"
        + struct.pack(">H", 12)
        + bytes([3, 1, 0, 2, 0, 3, 0, 0, 0x3F, 0])
    )
    return b"\xff\xd8" + app0 + sof0 + sos + b"\x00\xff\xd9"


class ImageSourceContractTests(unittest.TestCase):
    def test_png_and_jpeg_are_parsed_from_bytes_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            png_path = root / "hero.png"
            jpeg_path = root / "hero.jpeg"
            png_data = _png_bytes()
            jpeg_data = _jpeg_bytes()
            png_path.write_bytes(png_data)
            jpeg_path.write_bytes(jpeg_data)

            png_metadata = validate_image_file(
                png_path,
                expected_mime="image/png",
                expected_dimensions=(4, 3),
                expected_sha256=hashlib.sha256(png_data).hexdigest(),
            )
            jpeg_metadata = validate_image_file(
                jpeg_path,
                expected_mime_type="image/jpeg",
                expected_width=7,
                expected_height=5,
                expected_sha256=hashlib.sha256(jpeg_data).hexdigest(),
            )

            self.assertEqual(png_metadata.mime, "image/png")
            self.assertEqual(png_metadata.dimensions, (4, 3))
            self.assertEqual(jpeg_metadata.mime_type, "image/jpeg")
            self.assertEqual(jpeg_metadata.dimensions, (7, 5))

    def test_hero_artifact_rechecks_file_mime_dimensions_and_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "hero.png"
            path.write_bytes(_png_bytes(8, 6))
            artifact = HeroImageArtifact.from_file(
                path,
                artifact_id="hero-contract",
                provenance=ImageProvenance.PRIVATE_OWNED,
            )

            artifact.validate()
            self.assertTrue(artifact.is_valid())
            self.assertEqual(artifact.mime_type, "image/png")
            self.assertEqual(artifact.dimensions, (8, 6))
            self.assertEqual(artifact.provenance, ImageProvenance.PRIVATE_OWNED)
            payload = artifact.to_dict()
            self.assertEqual(payload["path"], "hero.png")
            self.assertNotIn(str(path), json.dumps(payload))

            wrong_mime = HeroImageArtifact(
                artifact_id=artifact.artifact_id,
                path=artifact.path,
                sha256=artifact.sha256,
                mime="image/jpeg",
                width=artifact.width,
                height=artifact.height,
                provenance=artifact.provenance,
            )
            with self.assertRaises(ImageValidationError):
                wrong_mime.validate()

            wrong_dimensions = HeroImageArtifact(
                artifact_id=artifact.artifact_id,
                path=artifact.path,
                sha256=artifact.sha256,
                mime=artifact.mime,
                width=9,
                height=artifact.height,
                provenance=artifact.provenance,
            )
            with self.assertRaises(ImageValidationError):
                wrong_dimensions.validate()

            wrong_hash = HeroImageArtifact(
                artifact_id=artifact.artifact_id,
                path=artifact.path,
                sha256="0" * 64,
                mime=artifact.mime,
                width=artifact.width,
                height=artifact.height,
                provenance=artifact.provenance,
            )
            with self.assertRaises(ImageValidationError):
                wrong_hash.validate()

    def test_synthetic_source_is_deterministic_and_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = SyntheticImageSource(
                root / "first", width=12, height=9, seed="stable-test-seed"
            ).materialize(artifact_id="hero")
            second = SyntheticImageSource(
                root / "second", width=12, height=9, seed="stable-test-seed"
            ).materialize(artifact_id="hero")

            self.assertEqual(first.status, MaterializationStatus.COMPLETE)
            self.assertIsNotNone(first.artifact)
            self.assertEqual(first.artifact.provenance.value, SYNTHETIC)
            self.assertEqual(
                first.artifact.path.read_bytes(), second.artifact.path.read_bytes()
            )
            self.assertEqual(first.artifact.sha256, second.artifact.sha256)
            first.artifact.validate()

    def test_chatgpt_handoff_writes_request_and_partial_manifest_without_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inbox = root / "inbox"
            output = root / "handoff"
            inbox.mkdir()
            result = ChatGPTHandoffImageSource(
                inbox, output_dir=output
            ).import_from_inbox()

            self.assertEqual(result.status, MaterializationStatus.PARTIAL)
            self.assertIsNone(result.artifact)
            self.assertEqual(result.provenance.value, CHATGPT_HANDOFF)
            self.assertEqual(result.request_path.name, "image_request.md")
            self.assertEqual(result.manifest_path.name, "image_manifest.json")
            self.assertTrue(result.request_path.is_file())
            self.assertTrue(result.manifest_path.is_file())
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "PARTIAL")
            self.assertEqual(manifest["artifacts"], [])
            self.assertNotIn(str(root), result.manifest_path.read_text(encoding="utf-8"))

    def test_chatgpt_handoff_imports_jpeg_and_writes_safe_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inbox = root / "inbox"
            output = root / "output"
            inbox.mkdir()
            source = inbox / "handoff.jpeg"
            source.write_bytes(_jpeg_bytes(21, 13))

            result = ChatGPTHandoffImageSource(
                inbox, output_dir=output
            ).materialize(artifact_id="approved-hero")

            self.assertEqual(result.status, MaterializationStatus.COMPLETE)
            self.assertIsNotNone(result.artifact)
            self.assertEqual(result.artifact.mime, "image/jpeg")
            self.assertEqual(result.artifact.dimensions, (21, 13))
            self.assertEqual(result.artifact.provenance, ImageProvenance.CHATGPT_HANDOFF)
            self.assertTrue((output / "approved-hero.jpg").is_file())
            manifest_text = result.manifest_path.read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)
            self.assertEqual(manifest["artifact"]["path"], "approved-hero.jpg")
            self.assertEqual(manifest["input_file"], "handoff.jpeg")
            self.assertEqual(manifest["provenance"], CHATGPT_HANDOFF)
            self.assertNotIn(str(root), manifest_text)
            self.assertIn("No API request or network call is made.", result.request_path.read_text(encoding="utf-8"))

    def test_codex_native_is_explicitly_partial_until_local_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "codex"
            result = CodexNativeImageSource(output_dir=output).materialize()

            self.assertEqual(result.status, MaterializationStatus.PARTIAL)
            self.assertTrue(result.not_implemented)
            self.assertIsNone(result.artifact)
            self.assertIn("not implemented", result.message.lower())
            self.assertTrue(result.manifest_path.is_file())
            self.assertEqual(
                json.loads(result.manifest_path.read_text(encoding="utf-8"))["provenance"],
                CODEX_NATIVE,
            )
            self.assertEqual(list(output.glob("*.png")), [])
            self.assertEqual(list(output.glob("*.jpg")), [])

    def test_codex_native_accepts_only_explicit_local_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "local.png"
            source.write_bytes(_png_bytes(10, 11))
            output = root / "materialized"

            result = CodexNativeImageSource(output_dir=output).materialize(
                materialized_path=source,
                artifact_id="codex-hero",
                dimensions=(10, 11),
            )

            self.assertEqual(result.status, MaterializationStatus.COMPLETE)
            self.assertEqual(result.artifact.provenance.value, CODEX_NATIVE)
            self.assertEqual(result.artifact.dimensions, (10, 11))
            self.assertTrue((output / "codex-hero.png").is_file())
            self.assertNotIn(str(root), result.manifest_path.read_text(encoding="utf-8"))

    def test_invalid_inbox_bytes_are_not_materialized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inbox = root / "inbox"
            output = root / "output"
            inbox.mkdir()
            (inbox / "bad.png").write_bytes(b"not-an-image")

            result = ChatGPTHandoffImageSource(
                inbox, output_dir=output
            ).materialize()

            self.assertEqual(result.status, MaterializationStatus.PARTIAL)
            self.assertIsNone(result.artifact)
            self.assertEqual(list(output.glob("*.png")), [])
            self.assertEqual(list(output.glob("*.jpg")), [])


if __name__ == "__main__":
    unittest.main()
