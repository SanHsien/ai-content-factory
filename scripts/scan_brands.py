#!/usr/bin/env python3
"""Run only the owner-configured hashed brand scan."""

# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from security_scan import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(["--check", "brands", *sys.argv[1:]]))
