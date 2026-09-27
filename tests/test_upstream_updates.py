"""What the upstream checker must not be allowed to do.

Every test here names a way the check could go quiet without anybody deciding
to stop watching upstream.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import check_upstream_updates as checker  # noqa: E402, I001


BASELINE = {
    "repo": "https://github.com/example/product.git",
    "branch": "main",
    "reviewed_through": "a" * 40,
    "reviewed_date": "2026-08-29",
}


def fake_gh(payload: object, returncode: int = 0):
    """Stand in for `gh`, so no test reaches the network."""

    def runner(args, **kwargs):
        assert args[0] == "gh"
        assert "--state" in args and args[args.index("--state") + 1] == "all"
        return subprocess.CompletedProcess(
            args, returncode, stdout=json.dumps(payload), stderr=""
        )

    return runner


class UpstreamUpdatesTests(unittest.TestCase):
    def test_tickets_are_queried_with_state_all(self):
        """An item opened and closed between two runs was still never triaged."""
        with patch.object(
            checker.subprocess,
            "run",
            fake_gh([{"number": 9, "title": "closed without merging"}]),
        ):
            tickets = checker.collect_new_tickets(BASELINE, "pr")
        self.assertEqual(tickets, [{"number": 9, "title": "closed without merging"}])


    def test_items_at_or_below_the_watermark_are_not_re_reported(self):
        with patch.object(
            checker.subprocess,
            "run",
            fake_gh([{"number": 4, "title": "old"}, {"number": 5, "title": "new"}]),
        ):
            baseline = {**BASELINE, "reviewed_pr_through": 4}
            tickets = checker.collect_new_tickets(baseline, "pr")
        self.assertEqual([ticket["number"] for ticket in tickets], [5])


    def test_ticket_titles_survive_undecodable_bytes(self):
        """Titles are written by strangers and the console is not always UTF-8.

        Without an explicit `errors`, one undecodable byte kills the whole upstream
        check instead of costing one garbled character.
        """
        captured = {}

        def runner(args, **kwargs):
            captured.update(kwargs)
            return subprocess.CompletedProcess(args, 0, stdout="[]", stderr="")

        with patch.object(checker.subprocess, "run", runner):
            checker.collect_new_tickets(BASELINE, "pr")

        self.assertEqual(captured["errors"], "replace")


    def test_gh_failure_reports_unchecked_rather_than_empty(self):
        """`None`, not `[]`: "not checked" must never render as "nothing to review"."""
        with patch.object(checker.subprocess, "run", fake_gh([], returncode=1)):
            self.assertIsNone(checker.collect_new_tickets(BASELINE, "issue"))


    def test_report_says_so_when_tickets_could_not_be_enumerated(self):
        report = checker.render_markdown(BASELINE, [], prs=None, issues=None)
        self.assertIn("Not checked", report)


    def test_report_covers_all_three_axes_even_when_commits_are_clean(self):
        report = checker.render_markdown(BASELINE, [], prs=[], issues=[])
        self.assertIn("## Commits", report)
        self.assertIn("## Upstream pull requests", report)
        self.assertIn("## Upstream issues", report)


    def test_upstream_slug(self):
        for url, expected in (
            ("https://github.com/example/product.git", "example/product"),
            ("https://github.com/example/product", "example/product"),
            ("git@github.com:example/product.git", "example/product"),
            ("https://gitlab.com/example/product.git", None),
        ):
            with self.subTest(url=url):
                self.assertEqual(checker.upstream_slug(url), expected)


    def test_a_remote_name_is_resolved_through_git(self):
        """This fork's baseline names the remote, not the URL.

        The scheduled workflow adds `upstream` from the GitHub fork parent at run
        time, so the baseline cannot hardcode a URL. Without resolving the name the
        ticket axes fail closed every week -- true, but useless.
        """
        with tempfile.TemporaryDirectory() as directory, patch.object(
            checker,
            "run_git",
            lambda args, repo_dir: "https://github.com/example/product.git",
        ):
            self.assertEqual(
                checker.upstream_slug("upstream", Path(directory)), "example/product"
            )

    def test_an_unresolvable_remote_name_is_still_none(self):
        def boom(args, repo_dir):
            raise checker.UpstreamCheckError("no such remote")

        with tempfile.TemporaryDirectory() as directory, patch.object(
            checker, "run_git", boom
        ):
            self.assertIsNone(checker.upstream_slug("upstream", Path(directory)))

    def test_shipped_baseline_resolves_to_a_github_repository(self):
        """The shipped baseline names the `upstream` remote, not a URL.

        Resolving it needs the repository directory, so this also pins that the
        caller must pass it -- dropping that argument is exactly how the ticket
        axes silently went back to "not checked".
        """
        baseline = checker.load_baseline()

        with patch.object(
            checker,
            "run_git",
            return_value="https://github.com/example/product.git",
        ):
            self.assertIsNone(checker.upstream_slug(baseline["repo"]))
            self.assertIsNotNone(
                checker.upstream_slug(baseline["repo"], checker.REPO_ROOT)
            )
