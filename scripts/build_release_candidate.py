"""Build and verify an allowlist-only local source release candidate."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import security_scan  # noqa: E402


class ReleaseCandidateError(RuntimeError):
    pass


def _load_manifest(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseCandidateError("release manifest is unreadable or invalid") from exc
    if not isinstance(value, Mapping) or value.get("schema_version") != "1.0":
        raise ReleaseCandidateError("unsupported release manifest")
    return value


def _excluded(relative: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(relative, pattern) for pattern in patterns)


def _collect_files(source: Path, manifest: Mapping[str, Any]) -> tuple[Path, ...]:
    includes = manifest.get("include", ())
    excludes = tuple(str(item) for item in manifest.get("exclude", ()))
    if not isinstance(includes, list) or not includes:
        raise ReleaseCandidateError("release include allowlist is empty")
    selected: dict[str, Path] = {}
    for raw in includes:
        relative = Path(str(raw))
        if relative.is_absolute() or ".." in relative.parts:
            raise ReleaseCandidateError("release include path is unsafe")
        candidate = source / relative
        paths = candidate.rglob("*") if candidate.is_dir() else (candidate,)
        for path in paths:
            if path.is_symlink() or not path.is_file():
                continue
            name = path.relative_to(source).as_posix()
            if not _excluded(name, excludes):
                selected[name] = path
    return tuple(selected[name] for name in sorted(selected))


def _validate_file(relative: str, path: Path, manifest: Mapping[str, Any]) -> None:
    lowered_parts = {part.casefold() for part in Path(relative).parts}
    forbidden_parts = {str(item).casefold() for item in manifest.get("forbidden_path_parts", ())}
    if lowered_parts & forbidden_parts:
        raise ReleaseCandidateError(f"forbidden release path: {relative}")
    forbidden_suffixes = {str(item).casefold() for item in manifest.get("forbidden_suffixes", ())}
    if path.suffix.casefold() in forbidden_suffixes:
        raise ReleaseCandidateError(f"forbidden release suffix: {relative}")
    if path.stat().st_size > int(manifest.get("max_file_bytes", 5_000_000)):
        raise ReleaseCandidateError(f"release file exceeds size limit: {relative}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_release_tree(root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    if not root.is_dir():
        raise ReleaseCandidateError("release candidate directory is missing")
    files = tuple(path for path in sorted(root.rglob("*")) if path.is_file())
    for path in files:
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ReleaseCandidateError(f"release symlink is forbidden: {relative}")
        _validate_file(relative, path, manifest)
    missing = [name for name in manifest.get("required", ()) if not (root / str(name)).is_file()]
    if missing:
        raise ReleaseCandidateError("required release files are missing: " + ", ".join(missing))
    hash_file = root / "scripts" / "public_brand_hashes.sha256"
    fingerprints = security_scan.load_brand_fingerprints(hash_files=(hash_file,))
    findings = security_scan.run_checks(root, brand_fingerprints=fingerprints)
    if findings:
        first = findings[0]
        raise ReleaseCandidateError(
            f"public safety scan failed: {first.check}:{first.path}:{first.rule}"
        )
    return {
        "file_count": len(files),
        "release_version": str(manifest.get("release_version", "")),
        "safety_scan": "PASS",
        "status": "PUBLIC_RELEASE_TREE_VALID",
    }


def build_release_candidate(source: Path, destination: Path, manifest_path: Path) -> dict[str, Any]:
    source = source.resolve()
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ReleaseCandidateError("destination already exists and is not empty")
    manifest = _load_manifest(manifest_path)
    selected = _collect_files(source, manifest)
    if not selected:
        raise ReleaseCandidateError("release allowlist selected no files")
    destination.mkdir(parents=True, exist_ok=True)
    try:
        for path in selected:
            relative = path.relative_to(source).as_posix()
            _validate_file(relative, path, manifest)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        files = {
            path.relative_to(destination).as_posix(): _sha256(path)
            for path in sorted(destination.rglob("*"))
            if path.is_file()
        }
        (destination / "PUBLIC_RELEASE_FILES.json").write_text(
            json.dumps(
                {"files": files, "release_version": manifest["release_version"], "schema_version": "1.0"},
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        result = verify_release_tree(destination, manifest)
    except Exception:
        if destination.is_dir():
            shutil.rmtree(destination)
        raise
    return {**result, "destination": str(destination), "source_file_count": len(selected)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = args.manifest or args.source / "public_release_manifest.json"
    try:
        result = build_release_candidate(args.source, args.destination, manifest)
    except ReleaseCandidateError as exc:
        print(json.dumps({"error": str(exc), "status": "FAILED"}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
