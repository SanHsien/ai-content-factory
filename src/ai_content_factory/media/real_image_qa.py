"""Local, standard-library QA for materialized PNG provider artifacts."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from ai_content_factory.core.hashing import sha256_hex


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def _check(check_id: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"detail": detail, "id": check_id, "passed": bool(passed)}


def evaluate_real_image(
    path: Path,
    *,
    expected_sha256: str,
    expected_width: int,
    expected_height: int,
    mime: str = "image/png",
) -> dict[str, Any]:
    exists = path.is_file()
    data = path.read_bytes() if exists else b""
    dimensions = png_dimensions(data)
    checks = [
        _check("artifact_exists", exists, "Generated artifact must exist locally."),
        _check("artifact_non_zero", bool(data), "Generated artifact must contain bytes."),
        _check("mime", mime == "image/png", "Phase two provider output must be image/png."),
        _check("extension", path.suffix.lower() == ".png", "File extension must match MIME."),
        _check("checksum", bool(data) and sha256_hex(data) == expected_sha256, "SHA-256 must match bytes."),
        _check("png_decode", dimensions is not None, "PNG signature and IHDR must be readable."),
        _check(
            "dimensions",
            dimensions == (expected_width, expected_height),
            "Decoded dimensions must match the requested output size.",
        ),
    ]
    blocking = [item["id"] for item in checks if not item["passed"]]
    return {
        "blocking_reasons": blocking,
        "checks": checks,
        "decoded_dimensions": (
            {"height": dimensions[1], "width": dimensions[0]} if dimensions is not None else None
        ),
        "status": "PASS" if not blocking else "FAIL",
        "summary": f"{len(checks) - len(blocking)}/{len(checks)} real-image checks passed.",
    }


__all__ = ["PNG_SIGNATURE", "evaluate_real_image", "png_dimensions"]
