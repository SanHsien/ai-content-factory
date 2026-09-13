"""Focused unit tests for the stdlib-only core contracts."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_content_factory.core import (  # noqa: E402
    ApprovalError,
    ApprovalState,
    Artifact,
    ContentPacket,
    SchemaValidationError,
    canonical_json,
    canonical_json_hash,
)


class CoreContractTests(unittest.TestCase):
    def make_packet(self) -> ContentPacket:
        artifact = Artifact.from_text("script", "hello world")
        return ContentPacket(
            packet_id="packet-1",
            version=1,
            content={"title": "Hello", "tags": ["demo"]},
            artifacts=[artifact],
            metadata={"owner": "test"},
        )

    def approve_packet(self) -> ContentPacket:
        packet = self.make_packet()
        packet.mark_qa_pending().mark_qa_passed().approve()
        self.assertIs(packet.approval_state, ApprovalState.APPROVED)
        self.assertTrue(packet.validate_integrity().valid)
        return packet

    def test_approval_state_contract_is_versioned_and_complete(self) -> None:
        self.assertEqual(
            [state.value for state in ApprovalState],
            [
                "DRAFT",
                "QA_PENDING",
                "QA_PASSED",
                "APPROVED",
                "REJECTED",
                "APPROVAL_INVALIDATED",
            ],
        )
        packet = ContentPacket("p-1", 3, {"body": "v3"})
        self.assertEqual(packet.version, 3)
        self.assertEqual(packet.schema_version, "1")
        self.assertEqual(packet.approval_state, ApprovalState.DRAFT)

    def test_canonical_json_and_hash_are_deterministic(self) -> None:
        first = {"b": [2, 1], "a": {"z": True, "x": "測試"}}
        second = {"a": {"x": "測試", "z": True}, "b": [2, 1]}
        self.assertEqual(canonical_json(first), canonical_json(second))
        expected = hashlib.sha256(canonical_json(first).encode("utf-8")).hexdigest()
        self.assertEqual(canonical_json_hash(first), expected)
        self.assertEqual(canonical_json(first), '{"a":{"x":"測試","z":true},"b":[2,1]}')

    def test_artifact_sha256_is_raw_content_digest(self) -> None:
        artifact = Artifact.from_bytes("binary", b"abc")
        expected = hashlib.sha256(b"abc").hexdigest()
        self.assertEqual(artifact.sha256, expected)
        self.assertEqual(artifact.computed_sha256, expected)
        self.assertTrue(artifact.validate_schema().valid)

    def test_packet_snapshot_is_valid_and_excludes_lifecycle_fields(self) -> None:
        packet = self.make_packet()
        snapshot = packet.capture_integrity_snapshot()
        self.assertEqual(snapshot.packet_hash, packet.packet_hash())
        self.assertEqual(snapshot.artifact_hashes["script"], packet.artifacts[0].sha256)
        self.assertTrue(packet.validate_integrity().valid)

        before = packet.packet_hash()
        packet.approval_state = ApprovalState.APPROVED
        packet.integrity_snapshot = None
        self.assertEqual(packet.packet_hash(), before)

    def test_approval_workflow_captures_snapshot_and_approves(self) -> None:
        packet = self.make_packet()
        with self.assertRaises(ApprovalError):
            packet.approve()
        packet.mark_qa_pending()
        packet.mark_qa_passed()
        self.assertIsNotNone(packet.integrity_snapshot)
        packet.approve()
        self.assertIs(packet.approval_state, ApprovalState.APPROVED)
        self.assertTrue(packet.approval_is_valid)

    def test_content_mutation_invalidates_approval(self) -> None:
        packet = self.approve_packet()
        packet.content["title"] = "changed"
        result = packet.validate_integrity()
        self.assertFalse(result.valid)
        self.assertIs(packet.approval_state, ApprovalState.APPROVAL_INVALIDATED)
        self.assertIn("INTEGRITY_PACKET_MUTATED", {error.code for error in result})

    def test_missing_artifact_invalidates_approval(self) -> None:
        packet = self.approve_packet()
        packet.artifacts.clear()
        result = packet.validate_integrity()
        self.assertFalse(result.valid)
        self.assertIs(packet.approval_state, ApprovalState.APPROVAL_INVALIDATED)
        self.assertIn("INTEGRITY_ARTIFACT_MISSING", {error.code for error in result})

    def test_replaced_artifact_invalidates_approval(self) -> None:
        packet = self.approve_packet()
        packet.artifacts[0] = Artifact.from_text("script", "replacement")
        result = packet.validate_integrity()
        self.assertFalse(result.valid)
        self.assertIs(packet.approval_state, ApprovalState.APPROVAL_INVALIDATED)
        self.assertIn("INTEGRITY_ARTIFACT_REPLACED", {error.code for error in result})

    def test_malformed_artifact_hash_invalidates_approval(self) -> None:
        packet = self.approve_packet()
        packet.artifacts[0].sha256 = "not-a-sha256"
        result = packet.validate_integrity()
        self.assertFalse(result.valid)
        self.assertIs(packet.approval_state, ApprovalState.APPROVAL_INVALIDATED)
        self.assertIn("INTEGRITY_ARTIFACT_HASH_MALFORMED", {error.code for error in result})

    def test_explicit_mutators_invalidate_approved_packet_immediately(self) -> None:
        packet = self.approve_packet()
        packet.set_content({"title": "new"})
        self.assertIs(packet.approval_state, ApprovalState.APPROVAL_INVALIDATED)

        packet = self.approve_packet()
        packet.remove_artifact("script")
        self.assertIs(packet.approval_state, ApprovalState.APPROVAL_INVALIDATED)

    def test_schema_validation_returns_structured_errors(self) -> None:
        malformed = ContentPacket(
            packet_id="",
            version=0,
            content={"ok": object()},
            artifacts=[Artifact(id="", content=None, sha256="bad", metadata=[])],
            metadata=[],
        )
        result = malformed.validate_schema()
        self.assertFalse(result.valid)
        self.assertGreaterEqual(len(result.errors), 5)
        error_dict = result.errors[0].to_dict()
        self.assertEqual(set(error_dict), {"code", "path", "message"})
        self.assertTrue(all(error.code and error.path and error.message for error in result))

    def test_fail_fast_schema_exception_contains_errors(self) -> None:
        packet = ContentPacket("p", 1, {"ok": object()})
        result = packet.validate_schema()
        with self.assertRaises(SchemaValidationError) as context:
            result.raise_for_errors()
        self.assertEqual(tuple(context.exception.errors), result.errors)

    def test_invalid_snapshot_hash_is_reported_and_invalidates_approval(self) -> None:
        packet = self.approve_packet()
        snapshot = packet.integrity_snapshot
        assert snapshot is not None
        packet.integrity_snapshot = type(snapshot)(
            packet_hash="malformed",
            artifact_hashes=snapshot.artifact_hashes,
        )
        result = packet.validate_integrity()
        self.assertFalse(result.valid)
        self.assertIs(packet.approval_state, ApprovalState.APPROVAL_INVALIDATED)
        self.assertIn("INTEGRITY_PACKET_HASH_MALFORMED", {error.code for error in result})


if __name__ == "__main__":
    unittest.main()
