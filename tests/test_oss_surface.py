from __future__ import annotations

import re
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ai_content_factory.cli import build_parser  # noqa: E402
from ai_content_factory.providers import FixtureProviders  # noqa: E402


class OssSurfaceTests(unittest.TestCase):
    def test_readme_has_product_first_quickstart_and_truthful_boundaries(self) -> None:
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        for expected in (
            "# AI Content Factory",
            "## 你會得到什麼",
            "## 快速開始（Windows）",
            "## 需要付費 API 或 GPU 嗎？",
            "## 架構一覽",
            "demo_preview.html",
            "No `pip install`",
        ):
            self.assertIn(expected, readme)
        self.assertNotIn("Offline staging / pre-public OSS core", readme)

    def test_english_readme_keeps_upstream_product_headings(self) -> None:
        readme = (REPOSITORY_ROOT / "README.en.md").read_text(encoding="utf-8")
        for expected in (
            "# AI Content Factory",
            "## What you get",
            "## Quickstart (Windows)",
            "## Do I need a paid API or GPU?",
            "## Architecture at a glance",
            "demo_preview.html",
            "No `pip install`",
        ):
            self.assertIn(expected, readme)

    def test_local_readme_links_resolve(self) -> None:
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        targets = re.findall(r"\[[^]]+\]\(([^)]+)\)", readme)
        self.assertTrue(targets)
        for target in targets:
            if "://" in target or target.startswith("#"):
                continue
            path = REPOSITORY_ROOT / target.split("#", 1)[0]
            self.assertTrue(path.exists(), target)

    def test_cli_help_is_product_facing_and_optional_live_plan_is_explicit(self) -> None:
        parser = build_parser()
        help_text = parser.format_help()
        self.assertIn("provider-neutral contracts", help_text)
        self.assertNotIn("phase-one", help_text)
        args = parser.parse_args(
            [
                "generate-media",
                "--provider",
                "openai-image",
                "--input",
                "request.json",
                "--output",
                "out",
                "--live-call-plan",
                "reviewed-plan.md",
            ]
        )
        self.assertEqual(args.live_call_plan, Path("reviewed-plan.md"))

    def test_quickstart_has_exact_portable_platform_commands(self) -> None:
        quickstart = (REPOSITORY_ROOT / "docs/quickstart.md").read_text(encoding="utf-8")
        for expected in (
            "python3 -m venv .venv",
            ".venv/bin/python -B scripts/bootstrap_offline.py",
            ".venv/bin/ai-content-factory --help",
            ".venv/bin/ai-content-factory demo --output output",
            ".venv/bin/ai-content-factory inspect --output output",
            ".venv/bin/ai-content-factory validate --output output",
            ".venv/bin/python -B scripts/public_ci.py",
            "MACOS_REAL_RUNTIME_VERIFIED=NO",
        ):
            self.assertIn(expected, quickstart)
        self.assertNotIn("python3.11 -m venv .venv", quickstart)
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("py -3 -m venv .venv", readme)
        self.assertNotIn("py -3.11 -m venv .venv", readme)

    def test_default_provider_registry_contains_only_fixtures(self) -> None:
        providers = FixtureProviders().as_mapping()
        self.assertTrue(providers)
        self.assertTrue(all(getattr(provider, "fixture_only", False) for provider in providers.values()))

    def test_required_oss_documents_exist(self) -> None:
        required = (
            "ARCHITECTURE.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
            "docs/quickstart.md",
            "docs/providers.md",
            "docs/image-providers.md",
            "docs/video-providers.md",
            "docs/voice-providers.md",
            "docs/editorial-engine.md",
            "docs/public-private-separation.md",
            "docs/privacy.md",
            "docs/troubleshooting.md",
        )
        self.assertEqual([], [name for name in required if not (REPOSITORY_ROOT / name).is_file()])


if __name__ == "__main__":
    unittest.main()
