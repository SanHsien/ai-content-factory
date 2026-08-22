from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import check_links  # noqa: E402
import check_upstream_updates as checker  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class ForkDocsTests(unittest.TestCase):
    def test_maintainer_markdown_links_resolve(self) -> None:
        failures = []
        for path in check_links.iter_documents():
            for problem in check_links.check_document(path):
                failures.append(f"{path.relative_to(ROOT)}: {problem}")
        self.assertEqual([], failures)

    def test_required_fork_documents_exist(self) -> None:
        required = (
            "FORK.md",
            "NOTICE.md",
            "AGENTS.md",
            "CLAUDE.md",
            "README.en.md",
            "docs/DEVELOPMENT.md",
            "docs/DECISIONS.md",
            "docs/UPSTREAM.md",
            "tools/dev_check.ps1",
            "tools/bootstrap_dev.ps1",
            "tools/upstream_baseline.json",
        )
        missing = [name for name in required if not (ROOT / name).is_file()]
        self.assertEqual([], missing)


class UpstreamCheckTests(unittest.TestCase):
    def test_baseline_file_is_valid_and_complete(self) -> None:
        baseline = checker.load_baseline()
        self.assertEqual(baseline["repo"], "upstream")
        self.assertEqual(baseline["branch"], "main")
        self.assertEqual(len(baseline["reviewed_through"]), 40)
        self.assertTrue(baseline["reviewed_date"])

    def test_workflow_is_scheduled_and_fails_on_unreviewed_commits(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "upstream-check.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("schedule:", workflow)
        self.assertIn("cron:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("tools/check_upstream_updates.py", workflow)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn("exit 1", workflow)

    def test_render_markdown_reports_no_new_commits(self) -> None:
        baseline = {
            "repo": "https://example.invalid/upstream.git",
            "branch": "main",
            "reviewed_through": "a" * 40,
            "reviewed_date": "2026-08-22",
        }
        report = checker.render_markdown(baseline, [])
        self.assertIn("No new upstream commits", report)

    def test_render_markdown_surfaces_check_failure(self) -> None:
        baseline = {
            "repo": "https://example.invalid/upstream.git",
            "branch": "main",
            "reviewed_through": "a" * 40,
            "reviewed_date": "2026-08-22",
        }
        report = checker.render_markdown(baseline, [], error="git fetch failed")
        self.assertIn("Check failed", report)
        self.assertIn("git fetch failed", report)

    def test_load_baseline_rejects_missing_file(self) -> None:
        with self.assertRaises(checker.UpstreamCheckError):
            checker.load_baseline(ROOT / "tools" / "missing-baseline.json")

    def test_baseline_matches_decisions_record(self) -> None:
        decisions = (ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
        baseline = json.loads(
            (ROOT / "tools" / "upstream_baseline.json").read_text(encoding="utf-8")
        )
        self.assertIn(baseline["reviewed_date"], decisions)


if __name__ == "__main__":
    unittest.main()
