from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ai_content_factory.pipeline import run_demo  # noqa: E402
from ai_content_factory.publishers import DryRunPublisher, ManualPublisher  # noqa: E402


class PublisherTests(unittest.TestCase):
    def _package(self, output: Path) -> dict:
        return json.loads((output / "publish_manifest.json").read_text(encoding="utf-8"))

    def test_dry_run_is_local_plan_only_and_remote_write_is_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            run = run_demo(output)
            self.assertTrue(run.succeeded)
            before = sorted(path.name for path in run.output_dir.iterdir())
            result = DryRunPublisher().publish(self._package(run.output_dir), output_dir=run.output_dir)
            after = sorted(path.name for path in run.output_dir.iterdir())
            self.assertTrue(result.succeeded)
            self.assertEqual(result.status, "DRY_RUN_READY")
            self.assertEqual(result.remote_write, 0)
            self.assertEqual(before, after)
            self.assertTrue(result.manual_action_required)

    def test_manual_publisher_writes_a_local_handoff_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            run = run_demo(output)
            self.assertTrue(run.succeeded)
            package = self._package(run.output_dir)
            handoff_dir = Path(temporary) / "handoff"
            first = ManualPublisher().publish(package, output_dir=handoff_dir)
            self.assertTrue(first.succeeded)
            self.assertEqual(first.status, "MANUAL_HANDOFF_READY")
            self.assertEqual(first.remote_write, 0)
            handoff = json.loads((handoff_dir / "manual_handoff.json").read_text(encoding="utf-8"))
            self.assertEqual(handoff["package_id"], package["package_id"])
            self.assertEqual(handoff["remote_write"], 0)

            duplicate = ManualPublisher().publish(package, output_dir=handoff_dir)
            self.assertFalse(duplicate.succeeded)
            self.assertEqual(duplicate.status, "DUPLICATE_PACKAGE")
            self.assertEqual(duplicate.failure.code, "DUPLICATE_PACKAGE")

    def test_nonzero_remote_write_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            run = run_demo(output)
            self.assertTrue(run.succeeded)
            package = self._package(run.output_dir)
            with patch.dict(os.environ, {"REMOTE_WRITE": "1"}):
                result = DryRunPublisher().publish(package)
            self.assertFalse(result.succeeded)
            self.assertEqual(result.failure.code, "REMOTE_WRITE_DISABLED")

    def test_unapproved_rejected_or_invalidated_package_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            run = run_demo(output)
            package = self._package(run.output_dir)
            for approval_state in ("DRAFT", "REJECTED", "APPROVAL_INVALIDATED"):
                candidate = dict(package)
                candidate["approval_status"] = approval_state
                result = DryRunPublisher().publish(candidate)
                self.assertFalse(result.succeeded, approval_state)
                self.assertEqual(result.failure.code, "APPROVAL_REQUIRED")

            malformed = dict(package)
            malformed["packet_sha256"] = "not-a-sha256"
            result = ManualPublisher().publish(malformed, output_dir=Path(temporary) / "manual")
            self.assertFalse(result.succeeded)
            self.assertEqual(result.failure.code, "APPROVAL_INVALIDATED")

            no_integrity = dict(package)
            no_integrity["approval_integrity"] = "FAIL"
            result = DryRunPublisher().publish(no_integrity)
            self.assertFalse(result.succeeded)
            self.assertEqual(result.failure.code, "APPROVAL_INVALIDATED")


if __name__ == "__main__":
    unittest.main()
