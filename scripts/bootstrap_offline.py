"""Install the local source tree into an existing virtual environment.

This bootstrap deliberately uses only the Python standard library. It does not
invoke pip, resolve packages, or contact a package index.
"""

from __future__ import annotations

import argparse
import json
import os
import site
import stat
import sys
from pathlib import Path


def _default_site_packages() -> Path:
    candidates = [Path(value) for value in site.getsitepackages()]
    if not candidates:
        raise RuntimeError("Python did not report a site-packages directory")
    return candidates[0]


def _default_launcher_dir() -> Path:
    # Keep the virtualenv executable directory.  Resolving a POSIX venv's
    # python symlink would incorrectly redirect the launcher to system bin.
    return Path(sys.executable).parent


def install(
    *,
    repo_root: Path,
    site_packages: Path,
    launcher_dir: Path,
    python_executable: Path,
) -> dict[str, str]:
    repo_root = repo_root.resolve()
    source_dir = repo_root / "src"
    package_dir = source_dir / "ai_content_factory"
    if not package_dir.is_dir():
        raise RuntimeError(f"package source missing: {package_dir}")

    site_packages.mkdir(parents=True, exist_ok=True)
    launcher_dir.mkdir(parents=True, exist_ok=True)

    pth_path = site_packages / "ai_content_factory_local.pth"
    pth_path.write_text(str(source_dir) + os.linesep, encoding="utf-8")

    if os.name == "nt":
        launcher_path = launcher_dir / "ai-content-factory.cmd"
        launcher_path.write_text(
            f'@"{python_executable}" -B -m ai_content_factory %*{os.linesep}',
            encoding="utf-8",
        )
    else:
        launcher_path = launcher_dir / "ai-content-factory"
        launcher_path.write_text(
            "#!/bin/sh\n"
            f'exec "{python_executable}" -B -m ai_content_factory "$@"\n',
            encoding="utf-8",
        )
        launcher_path.chmod(launcher_path.stat().st_mode | stat.S_IXUSR)

    result = {
        "status": "OFFLINE_BOOTSTRAP_COMPLETE",
        "source": str(source_dir),
        "pth": str(pth_path),
        "launcher": str(launcher_path),
        "network_required": "no",
        "third_party_packages_installed": "0",
    }
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--site-packages",
        type=Path,
        default=None,
        help="Override used by tests; defaults to the current interpreter site-packages.",
    )
    parser.add_argument(
        "--launcher-dir",
        type=Path,
        default=None,
        help="Override used by tests; defaults to the current interpreter directory.",
    )
    parser.add_argument(
        "--python-executable",
        type=Path,
        default=Path(sys.executable),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = install(
        repo_root=args.repo_root,
        site_packages=args.site_packages or _default_site_packages(),
        launcher_dir=args.launcher_dir or _default_launcher_dir(),
        python_executable=args.python_executable,
    )
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
