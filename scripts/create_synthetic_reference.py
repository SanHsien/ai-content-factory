"""Create the deterministic neutral PNG used by Phase 2 tests and examples."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


WIDTH = 256
HEIGHT = 256


def _pixel(x: int, y: int) -> tuple[int, int, int]:
    background = (224, 238, 246)
    face = (176, 126, 80)
    ear = (125, 82, 53)
    dark = (34, 42, 48)
    white = (247, 246, 239)
    if (x - 128) ** 2 + (y - 134) ** 2 <= 76**2:
        color = face
    else:
        color = background
    if (x - 70) ** 2 + (y - 119) ** 2 <= 43**2 or (x - 186) ** 2 + (y - 119) ** 2 <= 43**2:
        color = ear
    if (x - 102) ** 2 + (y - 124) ** 2 <= 11**2 or (x - 154) ** 2 + (y - 124) ** 2 <= 11**2:
        color = dark
    if (x - 99) ** 2 + (y - 121) ** 2 <= 3**2 or (x - 151) ** 2 + (y - 121) ** 2 <= 3**2:
        color = white
    if (x - 128) ** 2 + (y - 155) ** 2 <= 13**2:
        color = dark
    if 104 <= x <= 152 and 174 <= y <= 181 and (x - 128) ** 2 + (y - 174) ** 2 <= 24**2:
        color = dark
    return color


def png_bytes() -> bytes:
    rows = bytearray()
    for y in range(HEIGHT):
        rows.append(0)
        for x in range(WIDTH):
            rows.extend(_pixel(x, y))

    def chunk(name: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", zlib.crc32(name + payload) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b"")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    destination = root / "fixtures" / "synthetic" / "reference_pet.png"
    destination.write_bytes(png_bytes())
    print(destination.relative_to(root).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
