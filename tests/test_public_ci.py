from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import scripts.public_ci as public_ci  # noqa: E402


class PublicCiCredentialBoundaryTests(unittest.TestCase):
    def test_synthetic_parent_openai_key_is_not_inherited_by_offline_ci(self) -> None:
        sentinel = "ACF_SECRET_SENTINEL_DO_NOT_PRINT_7F3C_FINAL4"
        captured: list[tuple[list[str], dict[str, str]]] = []

        def fake_run(
            command: list[str], *, root: Path, env: dict[str, str]
        ) -> dict[str, object]:
            captured.append((command, env))
            return {
                "command": " ".join(command),
                "duration_seconds": 0.0,
                "exit_code": 0,
                "stdout": "offline-pass",
                "stderr": "",
            }

        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": sentinel, "REMOTE_WRITE": "1"},
            clear=False,
        ), patch.object(public_ci, "_run", side_effect=fake_run):
            report = public_ci.run_public_ci(REPOSITORY_ROOT)

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["remote_write"], 0)
        self.assertTrue(captured)
        for command, env in captured:
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertEqual(env["REMOTE_WRITE"], "0")
            self.assertNotIn("openai", " ".join(command).lower())
        self.assertNotIn(sentinel, json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
