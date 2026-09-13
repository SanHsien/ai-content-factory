"""Run the dependency-free public CI checks used by the release candidate."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def _run(command: list[str], *, root: Path, env: dict[str, str]) -> dict[str, object]:
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=root, env=env, text=True, capture_output=True, check=False)
    return {
        "command": " ".join(command),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _build_child_environment(root: Path) -> dict[str, str]:
    """Build the offline CI environment without inheriting optional credentials."""
    root = root.resolve()
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "REMOTE_WRITE", "OPENAI_API_KEY"}
    }
    env["PYTHONPATH"] = str(root / "src")
    return env


def run_public_ci(root: Path) -> dict[str, object]:
    root = root.resolve()
    env = _build_child_environment(root)
    env["REMOTE_WRITE"] = "0"
    commands = [
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
        [sys.executable, "-B", "scripts/security_scan.py", "--root", ".", "--brand-hash-file", "scripts/public_brand_hashes.sha256", "--format", "text"],
    ]
    with tempfile.TemporaryDirectory(prefix="acf-public-ci-") as temporary:
        output = Path(temporary) / "output"
        commands.extend(
            [
                [sys.executable, "-B", "-m", "ai_content_factory", "demo", "--output", str(output)],
                [sys.executable, "-B", "-m", "ai_content_factory", "validate", "--output", str(output)],
            ]
        )
        results = [_run(command, root=root, env=env) for command in commands]
    passed = all(item["exit_code"] == 0 for item in results)
    return {"checks": results, "remote_write": 0, "status": "PASS" if passed else "FAIL"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    report = run_public_ci(args.root)
    serialized = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(serialized, encoding="utf-8", newline="\n")
    print(serialized, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
