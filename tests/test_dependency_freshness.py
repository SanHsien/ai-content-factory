from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import unittest.mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# tools/ is a script directory, not a package, so the checker is loaded by path.
_SPEC = importlib.util.spec_from_file_location(
    "check_dependency_freshness",
    REPOSITORY_ROOT / "tools" / "check_dependency_freshness.py",
)
assert _SPEC and _SPEC.loader
freshness = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(freshness)


class DeclaredPrecisionTests(unittest.TestCase):
    def test_floor_is_compared_at_the_precision_it_states(self) -> None:
        # `>=6` promises "any 6.x", so 6.0.3 is not news; 7.0 is.
        self.assertFalse(freshness.is_newer_version("6.0.3", "6"))
        self.assertTrue(freshness.is_newer_version("7.0.0", "6"))
        self.assertTrue(freshness.is_newer_version("1.27.0", "1.26"))
        self.assertFalse(freshness.is_newer_version("1.26.4", "1.26"))


class HoldTests(unittest.TestCase):
    def test_marker_binds_to_the_package_on_the_same_line(self) -> None:
        holds = freshness.parse_holds(
            'requires = ["setuptools>=61"]  # freshness-hold: 只需要 PEP 621 支援\n'
            'other = ["ruff>=0.16"]\n'
        )
        self.assertEqual(holds, {"setuptools": "只需要 PEP 621 支援"})

    def test_comment_without_the_marker_is_not_a_hold(self) -> None:
        self.assertEqual(freshness.parse_holds('x = ["ruff>=0.16"]  # 一般註解\n'), {})

    def test_repository_build_backend_declares_a_floor_and_a_reason(self) -> None:
        packages = freshness.load_direct_dependencies()
        backend = [p for p in packages if p["name"].lower() == "setuptools"]
        self.assertEqual(len(backend), 1)
        self.assertTrue(backend[0]["minimum"], "build backend must declare a floor")
        self.assertTrue(backend[0]["hold"], "a held floor must say why")


class DeferralTests(unittest.TestCase):
    def _load(self, payload: object) -> dict[str, dict[str, str]]:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "deferrals.json"
            target.write_text(json.dumps(payload), encoding="utf-8")
            return freshness.load_deferrals(target)

    def test_entry_without_a_reviewed_version_is_ignored(self) -> None:
        # Otherwise a deferral becomes a permanently silenced check.
        self.assertEqual(self._load({"deferrals": {"openai": {"reason": "later"}}}), {})

    def test_missing_file_defers_nothing(self) -> None:
        self.assertEqual(freshness.load_deferrals(REPOSITORY_ROOT / "no-such.json"), {})

    def test_deferral_covers_the_reviewed_release_but_not_the_next_one(self) -> None:
        deferrals = {"openai": {"deferredLatest": "3.3.1", "reason": "需要金鑰驗證"}}
        package = {
            "name": "openai",
            "minimum": "2.46.0",
            "requirement": "openai==2.46.0",
            "group": "extra:openai-image",
            "hold": "",
        }
        with unittest.mock.patch.object(freshness, "fetch_pypi_version", return_value="3.3.1"):
            reviewed = freshness.collect_status([package], deferrals)[0]
        with unittest.mock.patch.object(freshness, "fetch_pypi_version", return_value="3.4.0"):
            moved_on = freshness.collect_status([package], deferrals)[0]

        self.assertTrue(reviewed["deferred"])
        self.assertFalse(freshness._needs_review(reviewed))
        self.assertFalse(moved_on["deferred"])
        self.assertTrue(freshness._needs_review(moved_on))

    def test_held_row_does_not_demand_review(self) -> None:
        self.assertFalse(
            freshness._needs_review({"outdated": True, "hold": "policy", "deferred": False})
        )
        self.assertTrue(
            freshness._needs_review({"outdated": True, "hold": "", "deferred": False})
        )

    def test_repository_deferrals_file_is_well_formed(self) -> None:
        for name, entry in freshness.load_deferrals().items():
            self.assertTrue(entry["deferredLatest"], f"{name} needs deferredLatest")
            self.assertTrue(entry["reason"], f"{name} needs a reason")


if __name__ == "__main__":
    unittest.main()
