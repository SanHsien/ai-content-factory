#!/usr/bin/env python3
"""Offline security checks for the Stranger Test repository.

The scanner deliberately emits repository-relative locations and SHA-256
fingerprints only. It never prints the matched secret, brand token, or
private path. The implementation uses only the Python 3.11 standard library.
"""

# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import dataclasses
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import unicodedata
from typing import Iterable, Iterator, Sequence


DEFAULT_MAX_FILE_BYTES = 5_000_000
DEFAULT_IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "build",
        "browser-profile",
        "cache",
        "dist",
        "logs",
        "node_modules",
        "output",
        "private",
        "venv",
    }
)


@dataclasses.dataclass(frozen=True)
class Finding:
    """A redacted finding suitable for text or JSON output."""

    check: str
    path: str
    line: int | None
    rule: str
    fingerprint: str | None
    detail: str

    def as_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class FileSnapshot:
    """The small amount of file state needed by all checks."""

    relative_path: str
    absolute_path: Path
    text: str | None
    skipped_reason: str | None


def _sha256(value: str | bytes) -> str:
    payload = value.encode("utf-8", errors="replace") if isinstance(value, str) else value
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def normalize_brand_token(value: str) -> str:
    """Normalize an owner-supplied brand token before hashing it."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def brand_fingerprint(value: str) -> str:
    """Return the fingerprint expected by ``--brand-sha256``."""

    return _sha256(normalize_brand_token(value))


def _normalise_relative(path: Path) -> str:
    return path.as_posix()


def iter_repository_files(
    root: Path,
    *,
    excludes: Sequence[str] = (),
) -> Iterator[tuple[str, Path]]:
    """Yield regular files without following symlinks or VCS metadata."""

    for directory, dirnames, filenames in os.walk(
        root,
        topdown=True,
        followlinks=False,
    ):
        dirnames[:] = sorted(
            name for name in dirnames if name not in DEFAULT_IGNORED_DIRS
        )
        filenames.sort()
        directory_path = Path(directory)
        for filename in filenames:
            candidate = directory_path / filename
            try:
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                relative = _normalise_relative(candidate.relative_to(root))
            except (OSError, ValueError):
                continue
            if any(fnmatch.fnmatch(relative, pattern) for pattern in excludes):
                continue
            yield relative, candidate


def _read_text(path: Path, max_file_bytes: int) -> tuple[str | None, str | None]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, f"unreadable file ({exc.__class__.__name__})"
    if len(raw) > max_file_bytes:
        return None, "file exceeds configured size limit"
    if b"\x00" in raw:
        return None, "binary file"
    return raw.decode("utf-8", errors="replace"), None


def load_snapshots(
    root: Path,
    *,
    excludes: Sequence[str] = (),
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> list[FileSnapshot]:
    snapshots: list[FileSnapshot] = []
    for relative, absolute in iter_repository_files(root, excludes=excludes):
        text, skipped_reason = _read_text(absolute, max_file_bytes)
        snapshots.append(
            FileSnapshot(
                relative_path=relative,
                absolute_path=absolute,
                text=text,
                skipped_reason=skipped_reason,
            )
        )
    return snapshots


_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "aws-access-key-id",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "credential-shaped identifier matched; value omitted",
    ),
    (
        "github-token-shaped",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        "credential-shaped token matched; value omitted",
    ),
    (
        "google-key-shaped",
        re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
        "credential-shaped key matched; value omitted",
    ),
    (
        "jwt-shaped",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        "token-shaped JWT matched; value omitted",
    ),
    (
        "private-key-block",
        re.compile(r"-----BEGIN [A-Z0-9 ]+-----"),
        "private-key marker matched; value omitted",
    ),
    (
        "generic-secret-assignment",
        re.compile(
            r"""(?ix)
            \b(?:api[ _-]?key|access[ _-]?token|client[ _-]?secret|secret|token|password|passwd|private[ _-]?key)\b
            \s*(?:=|:)\s*
            (?P<quote>[\"']?)
            (?P<value>[A-Za-z0-9][A-Za-z0-9_./+=:-]{11,})
            (?P=quote)
            """
        ),
        "secret-like assignment matched; value omitted",
    ),
)

_SENSITIVE_FILENAME = re.compile(
    r"(?ix)(?:^|/)(?:\.env(?:\..*)?|credentials(?:\..*)?|secrets?(?:\..*)?|"
    r"id_(?:rsa|dsa|ecdsa|ed25519)|[^/]+\.(?:pem|key|p12|pfx))$"
)


def scan_secrets(snapshots: Iterable[FileSnapshot]) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str, int | None, str, str | None]] = set()
    for snapshot in snapshots:
        if snapshot.relative_path != ".env.example" and _SENSITIVE_FILENAME.search(
            snapshot.relative_path
        ):
            finding = Finding(
                check="secrets",
                path=snapshot.relative_path,
                line=None,
                rule="sensitive-file-name",
                fingerprint=_sha256(snapshot.relative_path),
                detail="sensitive material filename matched; content is not reported",
            )
            key = (finding.path, finding.line, finding.rule, finding.fingerprint)
            if key not in seen:
                seen.add(key)
                findings.append(finding)
        if snapshot.text is None:
            continue
        for line_number, line in enumerate(snapshot.text.splitlines(), start=1):
            for rule, pattern, detail in _SECRET_PATTERNS:
                for match in pattern.finditer(line):
                    value = match.groupdict().get("value") or match.group(0)
                    finding = Finding(
                        check="secrets",
                        path=snapshot.relative_path,
                        line=line_number,
                        rule=rule,
                        fingerprint=_sha256(value),
                        detail=detail,
                    )
                    key = (finding.path, finding.line, finding.rule, finding.fingerprint)
                    if key not in seen:
                        seen.add(key)
                        findings.append(finding)
    return findings


_BRAND_TOKEN = re.compile(r"[^\W_]+(?:[-'_][^\W_]+)*", re.UNICODE)


def _brand_candidates(value: str, *, max_words: int = 5) -> Iterator[str]:
    matches = list(_BRAND_TOKEN.finditer(value))
    for start, match in enumerate(matches):
        for width in range(1, min(max_words, len(matches) - start) + 1):
            end = matches[start + width - 1].end()
            candidate = value[match.start() : end]
            normalized = normalize_brand_token(candidate)
            if len(normalized) >= 2:
                yield normalized


def _validate_fingerprint(value: str) -> str:
    cleaned = value.strip().casefold()
    if cleaned.startswith("sha256:"):
        cleaned = cleaned[7:]
    if not re.fullmatch(r"[0-9a-f]{64}", cleaned):
        raise ValueError("brand fingerprints must be 64 hexadecimal characters")
    return "sha256:" + cleaned


def load_brand_fingerprints(
    values: Iterable[str] = (),
    *,
    hash_files: Iterable[Path] = (),
    environ: dict[str, str] | None = None,
) -> frozenset[str]:
    """Load redacted fingerprints without requiring cleartext brand names."""

    raw_values = list(values)
    environment = os.environ if environ is None else environ
    raw_values.extend(
        item for item in environment.get("SECURITY_BRAND_HASHES", "").split(",") if item.strip()
    )
    for hash_file in hash_files:
        try:
            lines = hash_file.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ValueError(f"cannot read brand hash file: {exc.__class__.__name__}") from exc
        raw_values.extend(
            line.strip()
            for line in lines
            if line.strip() and not line.lstrip().startswith("#")
        )
    try:
        return frozenset(_validate_fingerprint(item) for item in raw_values)
    except ValueError:
        raise


def scan_brands(
    snapshots: Iterable[FileSnapshot],
    fingerprints: Iterable[str],
) -> list[Finding]:
    configured = frozenset(_validate_fingerprint(value) for value in fingerprints)
    if not configured:
        return []
    findings: list[Finding] = []
    seen: set[tuple[str, int | None, str, str | None]] = set()
    for snapshot in snapshots:
        candidates: Iterator[tuple[int | None, str]]
        if snapshot.text is None:
            candidates = iter(((None, candidate) for candidate in _brand_candidates(snapshot.relative_path)))
        else:
            def line_candidates() -> Iterator[tuple[int | None, str]]:
                for line_number, line in enumerate(snapshot.text.splitlines(), start=1):
                    for candidate in _brand_candidates(line):
                        yield line_number, candidate
                for candidate in _brand_candidates(snapshot.relative_path):
                    yield None, candidate

            candidates = line_candidates()
        for line_number, candidate in candidates:
            fingerprint = _sha256(candidate)
            if fingerprint not in configured:
                continue
            finding = Finding(
                check="brands",
                path=snapshot.relative_path,
                line=line_number,
                rule="configured-brand-fingerprint",
                fingerprint=fingerprint,
                detail="configured brand fingerprint matched; token omitted",
            )
            key = (finding.path, finding.line, finding.rule, finding.fingerprint)
            if key not in seen:
                seen.add(key)
                findings.append(finding)
    return findings


_PRIVATE_PATH_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "windows-absolute-path",
        re.compile(r"(?i)(?<![A-Za-z0-9])[A-Z]:[\\/](?:[^\\/\r\n]+[\\/])*[^\\/\r\n]*"),
    ),
    (
        "unc-path",
        re.compile(r"(?<![A-Za-z0-9])\\\\[^\\/\r\n]+[\\/][^\\/\r\n]+(?:[\\/][^\\/\r\n]*)*"),
    ),
    (
        "posix-home-path",
        re.compile(r"(?<![A-Za-z0-9_])/(?:home|Users|root)/[^/\s\"']+(?:/[^/\s\"']*)*"),
    ),
    (
        "tilde-home-path",
        re.compile(r"(?<![A-Za-z0-9_])~[\\/][^\s\"']+"),
    ),
)


def scan_private_paths(snapshots: Iterable[FileSnapshot]) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str, int | None, str, str | None]] = set()
    for snapshot in snapshots:
        if snapshot.text is None:
            continue
        for line_number, line in enumerate(snapshot.text.splitlines(), start=1):
            if "security-scan: path-pattern" in line:
                continue
            for rule, pattern in _PRIVATE_PATH_PATTERNS:
                for match in pattern.finditer(line):
                    finding = Finding(
                        check="private-paths",
                        path=snapshot.relative_path,
                        line=line_number,
                        rule=rule,
                        fingerprint=_sha256(match.group(0)),
                        detail="private path matched; path text omitted",
                    )
                    key = (finding.path, finding.line, finding.rule, finding.fingerprint)
                    if key not in seen:
                        seen.add(key)
                        findings.append(finding)
    return findings


def run_checks(
    root: Path,
    *,
    checks: Sequence[str] = ("secrets", "brands", "private-paths"),
    brand_fingerprints: Iterable[str] = (),
    excludes: Sequence[str] = (),
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> list[Finding]:
    snapshots = load_snapshots(
        root,
        excludes=excludes,
        max_file_bytes=max_file_bytes,
    )
    findings: list[Finding] = []
    selected = set(checks)
    if "secrets" in selected:
        findings.extend(scan_secrets(snapshots))
    if "brands" in selected:
        findings.extend(scan_brands(snapshots, brand_fingerprints))
    if "private-paths" in selected:
        findings.extend(scan_private_paths(snapshots))
    return sorted(
        findings,
        key=lambda item: (item.check, item.path, item.line or 0, item.rule),
    )


def render_text(findings: Sequence[Finding]) -> str:
    if not findings:
        return "security scan: clean"
    lines = [f"security scan: {len(findings)} finding(s)"]
    for finding in findings:
        location = finding.path
        if finding.line is not None:
            location += f":{finding.line}"
        fingerprint = finding.fingerprint or "none"
        lines.append(
            f"[{finding.check}] {location} rule={finding.rule} "
            f"fingerprint={fingerprint} detail={finding.detail}"
        )
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run redacted offline secret, brand, and private-path checks."
    )
    parser.add_argument("--root", type=Path, default=Path("."), help="repository root")
    parser.add_argument(
        "--check",
        choices=("all", "secrets", "brands", "private-paths"),
        default="all",
        help="check family to run",
    )
    parser.add_argument(
        "--brand-sha256",
        action="append",
        default=[],
        help="owner-supplied 64-hex SHA-256 fingerprint; cleartext is never stored",
    )
    parser.add_argument(
        "--brand-hash-file",
        type=Path,
        action="append",
        default=[],
        help="file containing one redacted fingerprint per line",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="repository-relative glob to skip; repeatable",
    )
    parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=DEFAULT_MAX_FILE_BYTES,
        help="maximum text file size to inspect",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        dest="output_format",
        help="output format",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        parser.error("--root must name an existing directory")
    if args.max_file_bytes <= 0:
        parser.error("--max-file-bytes must be positive")
    try:
        fingerprints = load_brand_fingerprints(
            args.brand_sha256,
            hash_files=args.brand_hash_file,
        )
        checks = ("secrets", "brands", "private-paths") if args.check == "all" else (args.check,)
        findings = run_checks(
            root,
            checks=checks,
            brand_fingerprints=fingerprints,
            excludes=args.exclude,
            max_file_bytes=args.max_file_bytes,
        )
    except ValueError as exc:
        parser.error(str(exc))
    except OSError as exc:
        print(f"security scan error: {exc.__class__.__name__}", file=sys.stderr)
        return 2
    if args.output_format == "json":
        print(json.dumps({"findings": [item.as_dict() for item in findings]}, ensure_ascii=False, indent=2))
    else:
        print(render_text(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
