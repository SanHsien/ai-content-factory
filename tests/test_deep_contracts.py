"""Synthetic, offline regressions from the line-by-line contract review."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_content_factory.core import ApprovalState, Artifact, ContentPacket
from ai_content_factory.media.editorial import (
    EditorialContractError, EditorialPlan, ShotSpec, SourceType, SubtitleEditor,
    evaluate_editorial_quality,
)
from ai_content_factory.media.qa import _is_safe_local_reference
from ai_content_factory.media.video_contracts import (
    VideoArtifact, VideoContractError, VideoRenderRequest,
)
from ai_content_factory.pipeline.approval import validate_approved_packet

SPEC = importlib.util.spec_from_file_location("deep_review_scanner", ROOT / "scripts/security_scan.py")
assert SPEC and SPEC.loader
SCANNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SCANNER
SPEC.loader.exec_module(SCANNER)


class DeepContractTests(unittest.TestCase):
    def test_historical_note_stays_with_its_original_decision(self) -> None:
        text = (ROOT / "docs/DECISIONS.md").read_text(encoding="utf-8")
        old_record = text.index("## 2026-09-30")
        self.assertLess(text.index("**修正**", old_record), text.index("## [DECISION-20261029-001]"))

    def test_packet_import_rejects_non_array_artifacts(self) -> None:
        for artifacts in ("lost-artifact", {"id": "lost-artifact"}, 42, None):
            with self.subTest(artifacts=artifacts):
                with self.assertRaises(TypeError):
                    ContentPacket.from_dict({"packet_id": "p", "artifacts": artifacts})

    def test_integrity_validation_reports_malformed_artifact(self) -> None:
        packet = ContentPacket("p", artifacts=[Artifact.from_text("a", "synthetic")])
        packet.mark_qa_pending().mark_qa_passed().approve()
        packet.artifacts.append("not-an-artifact")
        try:
            result = packet.validate_integrity()
        except Exception as exc:
            self.fail(f"validator crashed instead of reporting malformed input: {type(exc).__name__}")
        self.assertFalse(result.valid)
        self.assertIn("PACKET_ARTIFACT_INVALID", {error.code for error in result})
        self.assertEqual(packet.approval_state, ApprovalState.APPROVAL_INVALIDATED)

    def test_approval_and_qa_reject_same_unsafe_references(self) -> None:
        references = (
            "../../outside/hero.png",
            "a\\..\\..\\hero.png",
            "\\\\host\\share\\hero.png",
            "C:hero.png",
        )
        for reference in references:
            with self.subTest(reference=reference):
                self.assertFalse(
                    _is_safe_local_reference(reference),
                    f"qa should reject unsafe reference: {reference}",
                )
                document = {
                    "artifacts": [
                        {
                            "artifact_id": "test",
                            "path_or_reference": reference,
                        }
                    ]
                }
                valid, errors, _ = validate_approved_packet(ROOT, document=document)
                self.assertFalse(valid)
                self.assertIn("ARTIFACT_REFERENCE_UNSAFE", errors)

                with mock.patch("ai_content_factory.pipeline.approval.Path", PurePosixPath):
                    valid_posix, errors_posix, _ = validate_approved_packet(ROOT, document=document)
                    self.assertFalse(valid_posix)
                    self.assertIn("ARTIFACT_REFERENCE_UNSAFE", errors_posix)

        valid_document = {
            "artifacts": [
                {
                    "artifact_id": "valid",
                    "path_or_reference": "valid_nonexistent.json",
                }
            ]
        }
        self.assertTrue(_is_safe_local_reference("valid_nonexistent.json"))
        _, errors, _ = validate_approved_packet(ROOT, document=valid_document)
        self.assertNotIn("ARTIFACT_REFERENCE_UNSAFE", errors)
        self.assertIn("ARTIFACT_MISSING:valid_nonexistent.json", errors)

    def test_approval_rejects_multi_segment_references(self) -> None:
        for reference in ("sub/hero.png", "a\\b.png"):
            with self.subTest(reference=reference):
                document = {
                    "artifacts": [
                        {
                            "artifact_id": "test",
                            "path_or_reference": reference,
                        }
                    ]
                }
                valid, errors, _ = validate_approved_packet(ROOT, document=document)
                self.assertFalse(valid)
                self.assertIn("ARTIFACT_REFERENCE_UNSAFE", errors)

                with mock.patch("ai_content_factory.pipeline.approval.Path", PurePosixPath):
                    valid_posix, errors_posix, _ = validate_approved_packet(ROOT, document=document)
                    self.assertFalse(valid_posix)
                    self.assertIn("ARTIFACT_REFERENCE_UNSAFE", errors_posix)

    @staticmethod
    def shot(start: float, duration: float, index: int = 0) -> ShotSpec:
        return ShotSpec(
            shot_id=f"s{index}", purpose="synthetic beat", start_time_seconds=start,
            duration_seconds=duration, source_type=SourceType.H3_VIDEO,
            asset_id=f"a{index}", video_prompt="synthetic movement",
            voiceover_segment="synthetic narration",
        )

    def test_infinite_timeline_cannot_pass_editorial_quality(self) -> None:
        shots = [self.shot(0, float("inf"))]
        shots.extend(self.shot(float("inf"), 1, index) for index in range(1, 5))
        plan = EditorialPlan(
            editorial_plan_id="synthetic", target_platform="short",
            target_duration_seconds=float("inf"), fps=30, aspect_ratio="9:16",
            story_arc=("hook",), hook_strategy="synthetic", pace_profile="BALANCED",
            shots=tuple(shots),
        )
        with self.assertRaises(EditorialContractError):
            evaluate_editorial_quality(plan)

    def test_shot_and_subtitle_timings_must_be_finite(self) -> None:
        for number in (float("nan"), float("inf")):
            for field in ("start", "duration"):
                with self.subTest(number=number, field=field):
                    shot = self.shot(number if field == "start" else 0, number if field == "duration" else 1)
                    with self.assertRaises(EditorialContractError):
                        shot.validate()
            with self.subTest(subtitle_end=number):
                with self.assertRaises(EditorialContractError):
                    SubtitleEditor().compile(("synthetic",), 0, number)

    def test_empty_subtitle_animations_are_a_contract_error(self) -> None:
        with self.assertRaises(EditorialContractError):
            SubtitleEditor().compile(("synthetic",), 0, 1, animations=())

    def test_video_request_and_artifact_numbers_must_be_finite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.mp4"
            path.write_bytes(b"synthetic video bytes; no decoding claimed")
            for number in (float("nan"), float("inf")):
                for field in ("duration_seconds", "fps"):
                    with self.subTest(request=field, value=number):
                        request = VideoRenderRequest(request_id="synthetic", **{field: number})
                        with self.assertRaises(VideoContractError):
                            request.validate()
                    values = {"duration_seconds": 1, "fps": 30, field: number}
                    with self.subTest(artifact=field, value=number):
                        with self.assertRaises(VideoContractError):
                            VideoArtifact.from_file(path, width=16, height=16, **values)


class DeepScannerTests(unittest.TestCase):
    def scan_cli(self, root: Path, *arguments: str):
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts/security_scan.py"),
             "--root", str(root), "--format", "json", *arguments],
            capture_output=True, text=True, check=False, timeout=30,
        )
        self.assertTrue(result.stdout.lstrip().startswith("{"), result.stderr)
        return result, json.loads(result.stdout)

    def test_ignored_directories_are_reported_without_reading_private_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = "q" * 24
            for name in ("private", "build", "logs"):
                target = root / "nested" / name
                target.mkdir(parents=True)
                (target / "credentials.txt").write_text('token = "' + value + '"', encoding="utf-8")
            result, payload = self.scan_cli(root)
            self.assertEqual(result.returncode, 0)
            paths = {item["path"] for item in payload.get("unscanned", [])}
            self.assertEqual(paths, {"nested/private/", "nested/build/", "nested/logs/"})
            self.assertNotIn(value, result.stdout)
            self.assertNotIn("credentials.txt", result.stdout)

    def test_size_and_binary_skips_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "large.txt").write_bytes(b"x" * 64)
            (root / "binary.bin").write_bytes(b"synthetic\x00")
            (root / "utf16.txt").write_bytes("synthetic".encode("utf-16"))
            result, payload = self.scan_cli(root, "--max-file-bytes", "32")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(
                {item["path"] for item in payload.get("unscanned", [])},
                {"large.txt", "binary.bin", "utf16.txt"},
            )

    def test_strict_coverage_reports_before_failing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "private").mkdir()
            result, payload = self.scan_cli(root, "--fail-on-unscanned")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(payload["findings"], [])
            self.assertEqual(payload["unscanned"][0]["path"], "private/")

    def test_size_limit_bounds_the_read_itself(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.txt"
            path.write_bytes(b"x" * 64)
            original_open = Path.open
            case = self

            class LimitedReader:
                def __init__(self, handle):
                    self.handle = handle

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    self.handle.close()

                def read(self, size=-1):
                    case.assertGreaterEqual(size, 0, "scanner requested an unbounded read")
                    case.assertLessEqual(size, 9)
                    return self.handle.read(size)

            def guarded_open(path, *args, **kwargs):
                return LimitedReader(original_open(path, *args, **kwargs))

            with mock.patch.object(Path, "open", guarded_open):
                text, reason = SCANNER._read_text(path, 8)
            self.assertIsNone(text)
            self.assertIn("size limit", reason)

    def test_nonpositive_read_limit_cannot_request_an_unbounded_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.txt"
            path.write_text("synthetic", encoding="utf-8")
            with self.assertRaises(ValueError):
                SCANNER._read_text(path, -2)

    def test_unreadable_content_is_reported_without_the_error_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "synthetic.txt"
            path.write_text("synthetic", encoding="utf-8")
            skipped = []
            with mock.patch.object(Path, "open", side_effect=PermissionError("do not disclose this message")):
                SCANNER.run_checks(root, unscanned=skipped)
            self.assertEqual(skipped[0].path, "synthetic.txt")
            self.assertEqual(skipped[0].reason, "unreadable file (PermissionError)")

    def test_coverage_locations_redact_configured_brand(self) -> None:
        marker = "Synthetic" + "AuditMarker"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / marker / "private").mkdir(parents=True)
            result, payload = self.scan_cli(root, "--brand-sha256", SCANNER.brand_fingerprint(marker))
            self.assertEqual(result.returncode, 0)
            self.assertTrue(payload["unscanned"])
            self.assertNotIn(marker, result.stdout)

    def test_python_coverage_collector_redacts_configured_brand(self) -> None:
        marker = "Synthetic" + "AuditMarker"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / marker / "private").mkdir(parents=True)
            collector = []
            SCANNER.run_checks(
                root, brand_fingerprints=(SCANNER.brand_fingerprint(marker),),
                unscanned=collector,
            )
            self.assertTrue(collector)
            self.assertNotIn(marker, json.dumps([item.path for item in collector]))

    def test_worktree_git_file_is_not_repository_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_path = chr(67) + ":/" + "Users/" + "synthetic/worktree"
            (root / ".git").write_text("gitdir: " + private_path, encoding="utf-8")
            self.assertEqual(SCANNER.run_checks(root), [])

    def test_configured_brand_in_locations_is_redacted(self) -> None:
        marker = "Synthetic" + "AuditMarker"
        fingerprint = SCANNER.brand_fingerprint(marker)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / f"{marker}.txt").write_text('token = "' + "q" * 24 + '"', encoding="utf-8")
            snapshots = SCANNER.load_snapshots(root)
            for label, findings in (
                ("brands", SCANNER.scan_brands(snapshots, (fingerprint,))),
                ("all", SCANNER.run_checks(root, brand_fingerprints=(fingerprint,))),
            ):
                with self.subTest(label=label):
                    self.assertTrue(findings)
                    self.assertNotIn(marker, json.dumps([item.as_dict() for item in findings]))


if __name__ == "__main__":
    unittest.main()
