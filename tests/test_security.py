#!/usr/bin/env python3
"""Unit tests for the offline, stdlib-only security tooling."""

# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCANNER_PATH = REPOSITORY_ROOT / "scripts" / "security_scan.py"
MODULE_SPEC = importlib.util.spec_from_file_location("security_scan_under_test", SCANNER_PATH)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
SECURITY_SCAN = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = SECURITY_SCAN
MODULE_SPEC.loader.exec_module(SECURITY_SCAN)


class SecurityScannerTests(unittest.TestCase):
    def _snapshot(self, root: Path):
        return SECURITY_SCAN.load_snapshots(root)

    def test_secret_assignment_is_detected_and_redacted(self) -> None:
        synthetic_value = "q" * 24
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "note.txt").write_text(
                "token = \"" + synthetic_value + "\"\n",
                encoding="utf-8",
            )
            findings = SECURITY_SCAN.scan_secrets(self._snapshot(root))
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].rule, "generic-secret-assignment")
            self.assertNotIn(synthetic_value, json.dumps(findings[0].as_dict()))
            self.assertTrue(findings[0].fingerprint.startswith("sha256:"))

    def test_sensitive_filename_is_detected_without_reading_value(self) -> None:
        pem_marker = "-" * 5 + "BEGIN " + "PRIVATE KEY" + "-" * 5
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "opaque.pem").write_text(pem_marker, encoding="utf-8")
            findings = SECURITY_SCAN.scan_secrets(self._snapshot(root))
            rules = {finding.rule for finding in findings}
            self.assertIn("sensitive-file-name", rules)
            self.assertIn("private-key-block", rules)

    def test_placeholder_env_example_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env.example").write_text(
                "EXAMPLE_API_KEY=\nOPENAI_API_KEY=\n",
                encoding="utf-8",
            )
            self.assertEqual(SECURITY_SCAN.scan_secrets(self._snapshot(root)), [])

    def test_openai_env_assignment_and_vendor_prefix_are_detected(self) -> None:
        vendor_value = "sk" + "-" + "proj" + "-" + ("a" * 24)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.txt").write_text(
                "OPENAI_API_KEY=" + vendor_value + "\n",
                encoding="utf-8",
            )
            (root / "note.txt").write_text(vendor_value + "\n", encoding="utf-8")
            findings = SECURITY_SCAN.scan_secrets(self._snapshot(root))
            env_rules = {finding.rule for finding in findings if finding.path == "config.txt"}
            note_rules = {finding.rule for finding in findings if finding.path == "note.txt"}
            self.assertIn("openai-api-key-assignment", env_rules)
            self.assertEqual(note_rules, {"openai-secret-key-shaped"})
            serialized = json.dumps([finding.as_dict() for finding in findings])
            self.assertNotIn(vendor_value, serialized)

    def test_generated_and_private_directories_are_not_scanned(self) -> None:
        synthetic_value = "x" * 24
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("output", "cache", "private", "browser-profile", ".venv"):
                target = root / name
                target.mkdir()
                (target / "credentials.txt").write_text(
                    "token = \"" + synthetic_value + "\"\n", encoding="utf-8"
                )
            self.assertEqual(SECURITY_SCAN.run_checks(root), [])

    def test_brand_scan_uses_only_supplied_fingerprint(self) -> None:
        synthetic_token = "sample" + "_" + "tag"
        fingerprint = SECURITY_SCAN.brand_fingerprint(synthetic_token)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "content.txt").write_text(
                "A note contains " + synthetic_token + " for testing.\n",
                encoding="utf-8",
            )
            no_configuration = SECURITY_SCAN.scan_brands(self._snapshot(root), ())
            configured = SECURITY_SCAN.scan_brands(self._snapshot(root), (fingerprint,))
            self.assertEqual(no_configuration, [])
            self.assertEqual(len(configured), 1)
            self.assertNotIn(synthetic_token, json.dumps(configured[0].as_dict()))

    def test_private_path_is_detected_and_redacted(self) -> None:
        private_path = chr(67) + ":\\" + "Users" + "\\opaque-user\\private.txt"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "note.txt").write_text(private_path, encoding="utf-8")
            findings = SECURITY_SCAN.scan_private_paths(self._snapshot(root))
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].rule, "windows-absolute-path")
            self.assertNotIn(private_path, json.dumps(findings[0].as_dict()))

    # UNC samples are assembled at runtime so this file never carries a literal
    # path that the scanner itself would flag.
    _BS = chr(92)

    def _unc_matches(self, text: str) -> list[str]:
        pattern = dict(SECURITY_SCAN._PRIVATE_PATH_PATTERNS)["unc-path"]
        return [match.group(0) for match in pattern.finditer(text)]

    def test_unc_rule_ignores_escaped_backslash_source_literals(self) -> None:
        bs = self._BS
        samples = (
            'relative.replace("' + bs * 2 + '", "/")',
            "text.replace('" + bs * 4 + "', '/')",
            "pattern = r'" + bs * 2 + "d+/'",
            'split("' + bs * 2 + '", 1)[0] + "/x"',
            "sep = '" + bs * 2 + "' if windows else '/'",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(self._unc_matches(sample), [])

    def test_unc_rule_ignores_canonical_check_upstream_line(self) -> None:
        line = '    for part in relative.replace("' + self._BS * 2 + '", "/").split("/"):\n'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tool.py").write_text(line, encoding="utf-8")
            self.assertEqual(SECURITY_SCAN.scan_private_paths(self._snapshot(root)), [])

    def test_unc_rule_still_detects_real_unc_paths(self) -> None:
        bs = self._BS
        unc = bs * 2
        samples = (
            unc + "fileserver" + bs + "share" + bs + "x",
            unc + "10.0.0.5" + bs + "c$" + bs + "x",
            unc + "srv-01.corp.local" + bs + "home" + bs + "user",
            unc + "nas" + bs + "share",
            unc + "nas/share/x",
            unc + "srv" + bs + "My Share" + bs + "file.txt",
            unc + "[fe80::1]" + bs + "share",
            unc + "fe80--1.ipv6-literal.net" + bs + "share",
            unc + "dav@SSL@443" + bs + "DavWWWRoot" + bs + "x",
            unc + "?" + bs + "UNC" + bs + "server" + bs + "share",
            unc + "?" + bs + "C:" + bs + "x",
            unc + "." + bs + "pipe" + bs + "name",
        )
        for sample in samples:
            for wrapped in (sample, '"' + sample + '"', "'" + sample + "'", "`" + sample + "`",
                            "see (" + sample + ") now"):
                with self.subTest(wrapped=wrapped):
                    self.assertTrue(self._unc_matches(wrapped), wrapped)

    def test_unc_rule_keeps_netbios_legal_host_names(self) -> None:
        bs = self._BS
        hosts = ("_srv", "-srv", "srv~1", "srv!x", "srv#x", "srv&co", "srv(1)",
                 "srv+x", "srv%20x", "srv^x", "srv'x", "srv{x}", "~srv", "#srv")
        for host in hosts:
            sample = bs * 2 + host + bs + "share"
            for wrapped in (sample, '"' + sample + '"', "`" + sample + "`"):
                with self.subTest(wrapped=wrapped):
                    self.assertTrue(self._unc_matches(wrapped), wrapped)

    def test_unc_finding_is_redacted(self) -> None:
        bs = self._BS
        private_path = bs * 2 + "fileserver" + bs + "share" + bs + "opaque.txt"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "note.md").write_text("Copy from `" + private_path + "`.\n", encoding="utf-8")
            findings = SECURITY_SCAN.scan_private_paths(self._snapshot(root))
            self.assertEqual([finding.rule for finding in findings], ["unc-path"])
            self.assertNotIn(private_path, json.dumps(findings[0].as_dict()))

    def test_clean_content_has_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.txt").write_text(
                "Offline staging keeps review local and redacted.\n",
                encoding="utf-8",
            )
            findings = SECURITY_SCAN.run_checks(root)
            self.assertEqual(findings, [])

    def test_cli_returns_nonzero_only_when_findings_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clean = subprocess.run(
                [sys.executable, str(SCANNER_PATH), "--root", str(root), "--format", "json"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(clean.returncode, 0, clean.stderr)
            self.assertEqual(json.loads(clean.stdout), {"findings": []})
            (root / "note.txt").write_text("token = \"" + ("r" * 24) + "\"\n", encoding="utf-8")
            dirty = subprocess.run(
                [sys.executable, str(SCANNER_PATH), "--root", str(root)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(dirty.returncode, 1, dirty.stderr)
            self.assertIn("finding(s)", dirty.stdout)

    def test_quoted_key_forms_are_detected(self) -> None:
        value = "q" * 24
        samples = (
            '{"api_key": "' + value + '"}',
            "{'client_secret': '" + value + "'}",
            '"password" = "' + value + '"',
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, sample in enumerate(samples):
                (root / f"sample{index}.json").write_text(sample + "\n", encoding="utf-8")
            findings = SECURITY_SCAN.scan_secrets(self._snapshot(root))
            flagged = {finding.path for finding in findings}
            self.assertEqual(flagged, {f"sample{i}.json" for i in range(len(samples))})


if __name__ == "__main__":
    unittest.main()
