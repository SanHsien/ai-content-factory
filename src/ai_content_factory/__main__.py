"""Allow ``python -m ai_content_factory`` to run the local CLI."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    _src_root = Path(__file__).resolve().parents[1]
    if str(_src_root) not in sys.path:
        sys.path.insert(0, str(_src_root))
    from ai_content_factory.cli import main
else:
    from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
