from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "build_release_candidate.py"
SPEC = importlib.util.spec_from_file_location("release_builder_under_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class ReleaseCandidateTests(unittest.TestCase):
    def test_allowlist_build_is_public_safe_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "rc"
            result = BUILDER.build_release_candidate(
                REPOSITORY_ROOT,
                destination,
                REPOSITORY_ROOT / "public_release_manifest.json",
            )
            self.assertEqual(result["status"], "PUBLIC_RELEASE_TREE_VALID")
            self.assertEqual(result["safety_scan"], "PASS")
            self.assertTrue((destination / "README.md").is_file())
            self.assertTrue((destination / "PUBLIC_RELEASE_FILES.json").is_file())
            self.assertTrue((destination / "examples" / "demo-brand" / "video" / "index.html").is_file())
            self.assertTrue((destination / "fixtures" / "recorded" / "openai_image" / "success.json").is_file())
            self.assertFalse((destination / ".git").exists())
            self.assertFalse((destination / "docs" / "research").exists())
            self.assertFalse((destination / "tests_live").exists())
            manifest = json.loads(
                (destination / "PUBLIC_RELEASE_FILES.json").read_text(encoding="utf-8")
            )
            self.assertIn("src/ai_content_factory/cli.py", manifest["files"])

    def test_nonempty_destination_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "rc"
            destination.mkdir()
            marker = destination / "keep.txt"
            marker.write_text("preserve", encoding="utf-8")
            with self.assertRaises(BUILDER.ReleaseCandidateError):
                BUILDER.build_release_candidate(
                    REPOSITORY_ROOT,
                    destination,
                    REPOSITORY_ROOT / "public_release_manifest.json",
                )
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")


if __name__ == "__main__":
    unittest.main()
