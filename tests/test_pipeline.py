from __future__ import annotations

import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ai_content_factory.pipeline import (  # noqa: E402
    DEMO_TOPIC,
    PipelineOrchestrator,
    RunStatus,
    Stage,
    inspect_output,
    run_demo,
    validate_output,
)
from ai_content_factory.providers import FixtureProviders, FixtureUnavailableError, PLATFORMS  # noqa: E402
from unittest.mock import patch  # noqa: E402


class _FailingResearchProvider:
    fixture_only = True
    provider_id = "fixture-failing-research"

    def research(self, topic, *, brand=None):
        raise FixtureUnavailableError("synthetic fixture intentionally unavailable")


class _MalformedImageProvider:
    fixture_only = True
    provider_id = "fixture-malformed-image"

    def generate(self, prompt, *, topic=None, brand=None):
        return {"not": "a MediaAsset"}


class PipelineTests(unittest.TestCase):
    def test_pause_resume_writes_required_artifacts_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            paused = run_demo(output, stop_after=Stage.RESEARCH)
            self.assertEqual(paused.state.status, RunStatus.PAUSED)
            self.assertEqual(paused.output_dir.parent, output)
            self.assertEqual(paused.output_dir.name, paused.state.run_id)
            self.assertEqual(inspect_output(output)["next_stage"], Stage.TEXT.value)

            completed = run_demo(output, resume=True)
            self.assertEqual(completed.state.status, RunStatus.SUCCEEDED)
            report = validate_output(output, expected_topic=DEMO_TOPIC)
            self.assertTrue(report.valid, report.to_dict())
            self.assertTrue(report.complete)
            expected_root = {
                "pipeline_state.json",
                "run_log.jsonl",
                "packet_seed.json",
                "content_packet.json",
                "research.json",
                "article.md",
                "short_script.md",
                "storyboard.json",
                "media_manifest.json",
                "qa_scorecard.json",
                "approval.json",
                "publish_manifest.json",
                "demo_preview.html",
                "platform-ready",
            }
            self.assertEqual(
                expected_root,
                {path.name for path in completed.output_dir.iterdir()},
            )
            self.assertEqual(
                {f"{platform}.txt" for platform in PLATFORMS},
                {path.name for path in (completed.output_dir / "platform-ready").iterdir()},
            )
            package = json.loads(
                (completed.output_dir / "publish_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(set(package["platforms"]), set(PLATFORMS))
            self.assertEqual(package["remote_write"], 0)
            self.assertEqual(package["approval_status"], "APPROVED")
            self.assertEqual(package["approval_integrity"], "PASS")
            self.assertEqual(len(package["packet_sha256"]), 64)
            self.assertEqual(package["dedupe_key"], package["package_id"])
            self.assertEqual(set(package["planned_actions"]), set(PLATFORMS))
            self.assertTrue(
                all(action["remote_write"] == 0 for action in package["planned_actions"].values())
            )
            self.assertEqual(package["preview_file"], "demo_preview.html")
            preview = (completed.output_dir / "demo_preview.html").read_text(encoding="utf-8")
            self.assertIn("Offline release-candidate demo", preview)
            self.assertIn("Remote writes: 0", preview)
            self.assertNotIn("https://", preview)
            self.assertNotIn("http://", preview)

            packet = json.loads(
                (completed.output_dir / "content_packet.json").read_text(encoding="utf-8")
            )
            required_packet_fields = {
                "packet_id",
                "schema_version",
                "topic",
                "locale",
                "research",
                "article",
                "short_script",
                "storyboard",
                "media_artifacts",
                "platform_copy",
                "qa",
                "approval_state",
                "provenance",
                "created_at",
            }
            self.assertTrue(required_packet_fields.issubset(packet))
            self.assertEqual(packet["approval_state"], "APPROVED")
            self.assertEqual(packet["metadata"]["remote_write"], 0)
            self.assertTrue(packet["artifacts"])
            self.assertTrue(
                all(
                    {"artifact_id", "artifact_type", "path_or_reference", "sha256", "mime_type", "provenance", "generated_by", "created_at"}.issubset(item)
                    for item in packet["artifacts"]
                )
            )

            qa = json.loads(
                (completed.output_dir / "qa_scorecard.json").read_text(encoding="utf-8")
            )
            self.assertEqual(qa["status"], "PASS")
            self.assertEqual(qa["blocking_reasons"], [])
            self.assertTrue(qa["summary"])
            self.assertTrue(qa["checks"])
            events = [
                json.loads(line)
                for line in (completed.output_dir / "run_log.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertTrue(events)
            self.assertTrue(all("run_id" in event and "status" in event for event in events))

    def test_two_fresh_runs_are_byte_for_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first"
            second = Path(temporary) / "second"
            first_result = run_demo(first)
            second_result = run_demo(second)
            self.assertTrue(first_result.succeeded)
            self.assertTrue(second_result.succeeded)
            first_files = sorted(
                path.relative_to(first_result.output_dir).as_posix()
                for path in first_result.output_dir.rglob("*")
                if path.is_file()
            )
            second_files = sorted(
                path.relative_to(second_result.output_dir).as_posix()
                for path in second_result.output_dir.rglob("*")
                if path.is_file()
            )
            self.assertEqual(first_files, second_files)
            for filename in first_files:
                self.assertEqual(
                    (first_result.output_dir / filename).read_bytes(),
                    (second_result.output_dir / filename).read_bytes(),
                    filename,
                )

    def test_duplicate_run_is_structured_and_does_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            first = run_demo(output)
            self.assertTrue(first.succeeded)
            before = (first.output_dir / "publish_manifest.json").read_bytes()
            duplicate = run_demo(output)
            self.assertEqual(duplicate.state.status, RunStatus.DUPLICATE)
            self.assertEqual(duplicate.failure.code, "DUPLICATE_RUN")
            self.assertEqual((first.output_dir / "publish_manifest.json").read_bytes(), before)

    def test_mutated_preview_is_rejected_on_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            completed = run_demo(output)
            self.assertTrue(completed.succeeded)
            (completed.output_dir / "demo_preview.html").write_text(
                "<!doctype html><title>changed</title>", encoding="utf-8"
            )

            resumed = run_demo(output, resume=True)
            self.assertEqual(resumed.state.status, RunStatus.FAILED)
            self.assertEqual(resumed.failure.code, "DUPLICATE_PACKAGE")

    def test_preview_written_before_manifest_is_safely_replaced_on_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            paused = run_demo(output, stop_after=Stage.APPROVAL)
            self.assertEqual(paused.state.status, RunStatus.PAUSED)
            partial_preview = paused.output_dir / "demo_preview.html"
            partial_preview.write_text("partial", encoding="utf-8")

            resumed = run_demo(output, resume=True)
            self.assertTrue(resumed.succeeded, resumed.summary())
            self.assertTrue((resumed.output_dir / "publish_manifest.json").is_file())
            self.assertIn(
                "Offline release-candidate demo",
                partial_preview.read_text(encoding="utf-8"),
            )

    def test_provider_failure_is_persisted_without_a_private_path(self) -> None:
        providers = FixtureProviders().as_mapping()
        providers["research"] = _FailingResearchProvider()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            result = PipelineOrchestrator(providers).run(
                DEMO_TOPIC,
                output_dir=output,
            )
            self.assertEqual(result.state.status, RunStatus.FAILED)
            self.assertEqual(result.failure.code, "FIXTURE_UNAVAILABLE")
            state_text = (result.output_dir / "pipeline_state.json").read_text(encoding="utf-8")
            self.assertNotIn(str(Path(temporary)), state_text)
            self.assertEqual(inspect_output(output)["failure"]["code"], "FIXTURE_UNAVAILABLE")

    def test_mutated_approved_artifact_blocks_resume_to_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            completed = run_demo(output)
            self.assertTrue(completed.succeeded)
            article = completed.output_dir / "article.md"
            article.write_text(article.read_text(encoding="utf-8") + "\nmutation\n", encoding="utf-8")

            resumed = run_demo(output, resume=True)
            self.assertEqual(resumed.state.status, RunStatus.FAILED)
            self.assertEqual(resumed.failure.code, "APPROVAL_INVALIDATED")
            report = validate_output(output, expected_topic=DEMO_TOPIC)
            self.assertFalse(report.valid)
            self.assertTrue(
                any("CONTENT_PACKET_INTEGRITY" in error for error in report.errors),
                report.to_dict(),
            )

    def test_malformed_provider_output_is_structured_failure(self) -> None:
        providers = FixtureProviders().as_mapping()
        providers["image"] = _MalformedImageProvider()
        with tempfile.TemporaryDirectory() as temporary:
            result = PipelineOrchestrator(providers).run(
                DEMO_TOPIC,
                output_dir=Path(temporary) / "run",
            )
            self.assertEqual(result.state.status, RunStatus.FAILED)
            self.assertEqual(result.failure.code, "PROVIDER_RESULT_INVALID")
            self.assertEqual(result.failure.stage, Stage.MEDIA.value)

    def test_offline_demo_never_attempts_a_network_connection(self) -> None:
        def blocked(*args, **kwargs):
            raise AssertionError("offline demo attempted a network connection")

        with tempfile.TemporaryDirectory() as temporary, patch.object(
            socket.socket, "connect", blocked
        ), patch.object(socket, "create_connection", blocked):
            result = run_demo(Path(temporary) / "run")
            self.assertTrue(result.succeeded, result.summary())


if __name__ == "__main__":
    unittest.main()
