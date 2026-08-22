#!/usr/bin/env python3
"""檢查維護文件之間的相對連結指得到東西。

本 fork 的公開入口互相連來連去：README、FORK、NOTICE、AGENTS 與 docs。
文件被重新定位或改名時，這些連結會靜靜斷掉。只驗相對連結；外部網址交給人看。

    python tools/check_links.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
SKIP_PREFIXES = ("http://", "https://", "mailto:", "tel:", "#")
MAINTAINED_DOCUMENTS = (
    "README.md",
    "README.en.md",
    "FORK.md",
    "NOTICE.md",
    "AGENTS.md",
    "AGENTS.en.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "CONTRIBUTING.en.md",
    "SECURITY.md",
    "SECURITY.en.md",
    "CODE_OF_CONDUCT.md",
    "CODE_OF_CONDUCT.en.md",
    "REVIEW.md",
    "docs/DEVELOPMENT.md",
    "docs/DECISIONS.md",
    "docs/UPSTREAM.md",
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/bug_report.md",
    ".github/ISSUE_TEMPLATE/feature_request.md",
)


def iter_documents() -> list[Path]:
    missing = [relative for relative in MAINTAINED_DOCUMENTS if not (ROOT / relative).is_file()]
    if missing:
        raise FileNotFoundError("maintained documents missing: " + ", ".join(missing))
    return [ROOT / relative for relative in MAINTAINED_DOCUMENTS]


def check_document(path: Path) -> list[str]:
    problems: list[str] = []
    for match in LINK_PATTERN.finditer(path.read_text(encoding="utf-8")):
        target = match.group(1).strip().strip("<>")
        if not target or target.startswith(SKIP_PREFIXES):
            continue
        file_part = unquote(target.split("#", 1)[0])
        if not file_part:
            continue
        resolved = (path.parent / file_part).resolve()
        if not resolved.exists():
            try:
                shown = resolved.relative_to(ROOT)
            except ValueError:
                shown = resolved
            problems.append(f"{target} → 找不到 {shown}")
    return problems


def main() -> int:
    documents = iter_documents()
    if not documents:
        print("找不到任何維護用 Markdown 檔")
        return 1

    failures = 0
    for path in documents:
        problems = check_document(path)
        rel = path.relative_to(ROOT)
        if problems:
            failures += 1
            for problem in problems:
                print(f"FAIL {rel}: {problem}")
        else:
            print(f"OK   {rel}")

    print(f"\n共 {len(documents)} 份文件，{failures} 份有斷掉的相對連結。")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
