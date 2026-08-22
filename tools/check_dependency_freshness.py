"""Compare the dependencies declared in pyproject.toml against PyPI.

Dependabot proposes an upgrade when a package it watches publishes a release, but
it cannot answer the question a maintainer actually asks once a month: how far
behind is everything this repo declares? This reads every direct requirement --
runtime, optional extras, build backend -- asks PyPI for the current release, and
writes a Markdown report.

Declarations only. The installed environment is never inspected and no file is
ever edited: a newer release is a prompt to read the release notes and run the
suite, not a merge.

    python tools/check_dependency_freshness.py --output report.md --github-output
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "ai-content-factory-dependency-freshness"

_REQUIREMENT_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?\s*(.*)$")
_MINIMUM_RE = re.compile(r"(>=|>|==|~=)\s*([0-9][0-9A-Za-z.!+_-]*)")
_RELEASE_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)*")


class DependencyCheckError(RuntimeError):
    """Raised when pyproject.toml cannot be read."""


def _load_toml(path: Path) -> dict[str, Any]:
    # tomllib arrived in 3.11 and this package still supports 3.10, so the
    # import stays inside the one function that needs it. The scheduled check
    # runs on 3.13; on 3.10 only this call fails, not the whole module.
    try:
        import tomllib
    except ModuleNotFoundError as exc:  # pragma: no cover - 3.10 only
        raise DependencyCheckError(
            "reading pyproject.toml needs Python 3.11 or newer (tomllib)"
        ) from exc
    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except OSError as exc:
        raise DependencyCheckError(f"cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise DependencyCheckError(f"invalid TOML in {path}: {exc}") from exc


def release_key(version: str) -> tuple[int, ...] | None:
    """Return the numeric release segment of a version, or None if unparsable.

    Pre-release and local suffixes are dropped, so 7.0.0rc1 and 7.0.0 rank the
    same -- precise enough for "has the declared floor aged?" without adding a
    PEP 440 parser to a package whose only runtime dependency is PyYAML.
    """
    match = _RELEASE_RE.match(version.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.group(0).split("."))


def is_newer_version(latest: str, declared: str) -> bool:
    """Is `latest` newer than `declared` at the precision `declared` states?

    A floor of `PyYAML>=6` says "any 6.x"; reporting 6.0.3 against it would be a
    standing false alarm, and a report that cries wolf every month gets ignored.
    So the comparison happens at the depth the declaration commits to: `>=6` is
    compared on the major alone, `>=1.26` on major and minor.
    """
    latest_key = release_key(latest)
    declared_key = release_key(declared)
    if latest_key is None or declared_key is None:
        return False
    depth = len(declared_key)
    padded = latest_key + (0,) * (depth - len(latest_key))
    return padded[:depth] > declared_key


def parse_requirements(requirements: list[str], group: str) -> list[dict[str, str]]:
    packages: list[dict[str, str]] = []
    for requirement in requirements:
        head = requirement.split(";", 1)[0]
        match = _REQUIREMENT_RE.match(head)
        if not match:
            continue
        name, specifiers = match.groups()
        minimum = _MINIMUM_RE.search(specifiers)
        packages.append(
            {
                "name": name,
                "minimum": minimum.group(2) if minimum else "",
                "requirement": requirement.strip(),
                "group": group,
            }
        )
    return packages


def load_direct_dependencies(
    pyproject_path: Path = REPO_ROOT / "pyproject.toml",
) -> list[dict[str, str]]:
    data = _load_toml(pyproject_path)
    project = data.get("project", {})
    packages = parse_requirements(project.get("dependencies", []), "runtime")
    for extra, requirements in project.get("optional-dependencies", {}).items():
        packages.extend(parse_requirements(requirements, f"extra:{extra}"))
    packages.extend(
        parse_requirements(data.get("build-system", {}).get("requires", []), "build-system")
    )
    return packages


def fetch_pypi_version(package_name: str, timeout: float = 10.0) -> str | None:
    quoted_name = urllib.parse.quote(package_name, safe="")
    request = urllib.request.Request(
        f"https://pypi.org/pypi/{quoted_name}/json",
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    version = payload.get("info", {}).get("version")
    return str(version) if version else None


def collect_status(packages: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for package in packages:
        minimum = package["minimum"]
        latest = fetch_pypi_version(package["name"])
        rows.append(
            {
                **package,
                "latest": latest or "unknown",
                "outdated": bool(minimum and latest and is_newer_version(latest, minimum)),
                # 缺下限與查不到版本是兩件事：前者是宣告本身沒說話（值得修，但檢查
                # 本身是成功的），後者才是這支檢查沒能拿到答案。
                "no_floor": not minimum,
                "check_failed": latest is None,
            }
        )
    return rows


def render_markdown(rows: list[dict[str, Any]], error: str | None = None) -> str:
    lines = ["# 依賴新鮮度報告", ""]
    if error:
        lines.extend(["## 檢查失敗", "", f"```text\n{error}\n```", ""])
        return "\n".join(lines)

    lines.extend(
        [
            "| 套件 | 群組 | 宣告 | PyPI 現行版 | 狀態 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        if row["check_failed"]:
            status = "檢查失敗"
        elif row.get("no_floor"):
            status = "未宣告下限"
        elif row["outdated"]:
            status = "待審視"
        else:
            status = "OK"
        lines.append(
            f"| `{row['name']}` | `{row['group']}` | `{row['requirement']}` | "
            f"`{row['latest']}` | {status} |"
        )
    if not rows:
        lines.append("| - | - | - | - | 檢查失敗 |")
    lines.extend(
        [
            "",
            "本報告只比對 `pyproject.toml` 的宣告與 PyPI 現行版本，不檢查已安裝環境，",
            "也不會修改任何檔案。",
            "",
            "## 處理流程",
            "",
            "1. 讀 release notes，確認仍涵蓋 `requires-python` 宣告的 >=3.11。",
            "2. 在 Windows 與 Linux 兩邊跑 `python -m pytest` 再調宣告；`openai` 是精確 pin，",
            "   升版前要確認影像產出路徑仍可用。",
            "3. 本專案 offline-first：新增執行期依賴前先確認離線路徑不受影響。",
            "",
        ]
    )
    return "\n".join(lines)


def write_github_output(rows: list[dict[str, Any]], report_path: Path) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    outdated = any(bool(row["outdated"]) for row in rows)
    check_failed = not rows or any(bool(row["check_failed"]) for row in rows)
    no_floor = any(bool(row.get("no_floor")) for row in rows)
    with open(output_path, "a", encoding="utf-8") as output:
        output.write(f"outdated={'true' if outdated else 'false'}\n")
        output.write(f"check_failed={'true' if check_failed else 'false'}\n")
        output.write(f"no_floor={'true' if no_floor else 'false'}\n")
        output.write(
            f"needs_attention={'true' if outdated or check_failed or no_floor else 'false'}\n"
        )
        output.write(f"report_path={report_path.as_posix()}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="dependency-freshness-report.md")
    parser.add_argument("--github-output", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when a declared floor has aged.",
    )
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    error: str | None = None
    try:
        rows = collect_status(load_direct_dependencies())
    except DependencyCheckError as exc:
        error = str(exc)

    report = render_markdown(rows, error)
    output_path = Path(args.output)
    output_path.write_text(report, encoding="utf-8")
    print(report)

    if args.github_output:
        write_github_output(rows, output_path)
    if error:
        return 2
    if args.strict and any(
        bool(row["outdated"]) or bool(row["check_failed"]) or bool(row.get("no_floor"))
        for row in rows
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
