from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ai_content_factory.media import evaluate_media_manifest  # noqa: E402
from ai_content_factory.pipeline import run_demo  # noqa: E402


class MediaQATests(unittest.TestCase):
    def _generated(self) -> tuple[dict, dict]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        run = run_demo(Path(temporary.name) / "output")
        media = json.loads((run.output_dir / "media_manifest.json").read_text(encoding="utf-8"))
        storyboard = json.loads((run.output_dir / "storyboard.json").read_text(encoding="utf-8"))
        return media, storyboard

    def test_valid_synthetic_media_manifest_passes(self) -> None:
        media, storyboard = self._generated()
        report = evaluate_media_manifest(media, storyboard=storyboard)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["blocking_reasons"], [])

    def test_missing_required_asset_fails(self) -> None:
        media, storyboard = self._generated()
        media["assets"] = [item for item in media["assets"] if item["media_type"] != "voice"]
        report = evaluate_media_manifest(media, storyboard=storyboard)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("required_asset_types", report["blocking_reasons"])

    def test_checksum_mime_metadata_and_subtitle_failures_are_blocking(self) -> None:
        media, storyboard = self._generated()
        broken = copy.deepcopy(media)
        broken["assets"][0]["descriptor_sha256"] = "0" * 64
        broken["assets"][0]["metadata"]["mime_type"] = "application/octet-stream"
        storyboard["scenes"][0]["voiceover"] = ""
        report = evaluate_media_manifest(broken, storyboard=storyboard)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any(item.endswith("_checksum") for item in report["blocking_reasons"]))
        self.assertTrue(any(item.endswith("_mime_type") for item in report["blocking_reasons"]))
        self.assertIn("subtitle_manifest_valid", report["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()
