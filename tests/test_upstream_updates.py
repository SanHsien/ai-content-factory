"""What the upstream checker must not be allowed to do.

Every test here names a way the check could go quiet without anybody deciding
to stop watching upstream.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_tickets_are_queried_with_state_all(monkeypatch):
    """An item opened and closed between two runs was still never triaged."""
    monkeypatch.setattr(
        checker.subprocess,
        "run",
        fake_gh([{"number": 9, "title": "closed without merging"}]),
    )
    tickets = checker.collect_new_tickets(BASELINE, "pr")
    assert tickets == [{"number": 9, "title": "closed without merging"}]


def test_items_at_or_below_the_watermark_are_not_re_reported(monkeypatch):
    monkeypatch.setattr(
        checker.subprocess,
        "run",
        fake_gh([{"number": 4, "title": "old"}, {"number": 5, "title": "new"}]),
    )
    baseline = {**BASELINE, "reviewed_pr_through": 4}
    assert [t["number"] for t in checker.collect_new_tickets(baseline, "pr")] == [5]


def test_ticket_titles_survive_undecodable_bytes(monkeypatch):
    """Titles are written by strangers and the console is not always UTF-8.

    Without an explicit `errors`, one undecodable byte kills the whole upstream
    check instead of costing one garbled character.
    """
    captured = {}

    def runner(args, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args, 0, stdout="[]", stderr="")

    monkeypatch.setattr(checker.subprocess, "run", runner)
    checker.collect_new_tickets(BASELINE, "pr")

    assert captured["errors"] == "replace"


def test_gh_failure_reports_unchecked_rather_than_empty(monkeypatch):
    """`None`, not `[]`: "not checked" must never render as "nothing to review"."""
    monkeypatch.setattr(checker.subprocess, "run", fake_gh([], returncode=1))
    assert checker.collect_new_tickets(BASELINE, "issue") is None


def test_report_says_so_when_tickets_could_not_be_enumerated():
    report = checker.render_markdown(BASELINE, [], prs=None, issues=None)
    assert "Not checked" in report


def test_report_covers_all_three_axes_even_when_commits_are_clean():
    report = checker.render_markdown(BASELINE, [], prs=[], issues=[])
    assert "## Commits" in report
    assert "## Upstream pull requests" in report
    assert "## Upstream issues" in report


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/example/product.git", "example/product"),
        ("https://github.com/example/product", "example/product"),
        ("git@github.com:example/product.git", "example/product"),
        ("https://gitlab.com/example/product.git", None),
    ],
)
def test_upstream_slug(url, expected):
    assert checker.upstream_slug(url) == expected


def test_a_remote_name_is_resolved_through_git(monkeypatch, tmp_path):
    """This fork's baseline names the remote, not the URL.

    The scheduled workflow adds `upstream` from the GitHub fork parent at run
    time, so the baseline cannot hardcode a URL. Without resolving the name the
    ticket axes fail closed every week -- true, but useless.
    """
    monkeypatch.setattr(
        checker,
        "run_git",
        lambda args, repo_dir: "https://github.com/example/product.git",
    )

    assert checker.upstream_slug("upstream", tmp_path) == "example/product"


def test_an_unresolvable_remote_name_is_still_none(monkeypatch, tmp_path):
    def boom(args, repo_dir):
        raise checker.UpstreamCheckError("no such remote")

    monkeypatch.setattr(checker, "run_git", boom)

    assert checker.upstream_slug("upstream", tmp_path) is None


def test_shipped_baseline_resolves_to_a_github_repository():
    """The shipped baseline names the `upstream` remote, not a URL.

    Resolving it needs the repository directory, so this also pins that the
    caller must pass it -- dropping that argument is exactly how the ticket
    axes silently went back to "not checked".
    """
    baseline = checker.load_baseline()

    assert checker.upstream_slug(baseline["repo"]) is None
    assert checker.upstream_slug(baseline["repo"], checker.REPO_ROOT) is not None
