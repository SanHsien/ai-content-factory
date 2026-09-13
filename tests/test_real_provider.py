"""Offline contract tests for the opt-in real image provider.

These tests never use the official SDK transport.  They inject a small local
transport and generate a deterministic 1024x1024 PNG with the Python standard
library so the provider's materialization, hashing, QA, provenance, cache,
retry, and review boundaries can be exercised without network access.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ai_content_factory.core.hashing import sha256_hex  # noqa: E402
from ai_content_factory.providers import FixtureProviders  # noqa: E402
from ai_content_factory.providers.openai_image import (  # noqa: E402
    REGISTRY_FILENAME,
    OpenAIImageProvider,
)
from ai_content_factory.providers.real_media import (  # noqa: E402
    CostPolicy,
    ProviderErrorCode,
    RealImageRequest,
    RealProviderError,
    ReferenceAsset,
    ReviewState,
    UsageRightsStatus,
)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return (
        struct.pack(">I", len(data))
        + body
        + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    )


def deterministic_png(width: int = 1024, height: int = 1024) -> bytes:
    """Return a deterministic, valid RGBA PNG without Pillow."""

    row = b"\x00" + bytes((32, 96, 160, 255)) * width
    raw = row * height
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


def _recorded_response(image: bytes | None = None, *, request_id: str = "request_test") -> dict:
    payload = deterministic_png() if image is None else image
    return {
        "background": "opaque",
        "data": [{"b64_json": base64.b64encode(payload).decode("ascii")}],
        "output_format": "png",
        "quality": "low",
        "request_id": request_id,
        "size": "1024x1024",
        "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
    }


class _RecordingTransport:
    def __init__(self, *events: object) -> None:
        self.events = list(events)
        self.calls: list[dict[str, str]] = []

    def edit_image(self, request: RealImageRequest, *, dedupe_key: str) -> dict:
        self.calls.append({"packet_id": request.packet_id, "dedupe_key": dedupe_key})
        event = self.events.pop(0) if self.events else _recorded_response()
        if isinstance(event, Exception):
            raise event
        if not isinstance(event, dict):
            raise TypeError("test transport event must be a mapping or exception")
        return dict(event)


class _StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"synthetic status {status_code}")


class RealProviderOfflineContractTests(unittest.TestCase):
    def test_offline_cli_import_does_not_load_live_provider_modules(self) -> None:
        probe = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                (
                    "import sys; "
                    f"sys.path.insert(0, {str(SOURCE_ROOT)!r}); "
                    "import ai_content_factory.cli; "
                    "print(int('ai_content_factory.providers.openai_image' in sys.modules)); "
                    "print(int('ai_content_factory.providers.real_media' in sys.modules)); "
                    "print(int('openai' in sys.modules))"
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertEqual(probe.stdout.splitlines(), ["0", "0", "0"])

    def _reference(self, root: Path, *, rights: UsageRightsStatus = UsageRightsStatus.SYNTHETIC) -> ReferenceAsset:
        path = root / "synthetic_reference.png"
        data = deterministic_png()
        path.write_bytes(data)
        return ReferenceAsset(
            artifact_id="reference-test",
            path=path,
            sha256=sha256_hex(data),
            mime="image/png",
            width=1024,
            height=1024,
            source_type="synthetic-test",
            usage_rights_status=rights,
            provenance="runtime-generated-test",
            consent_or_ownership_status="synthetic-test-owned",
        )

    def _request(self, root: Path, *, rights: UsageRightsStatus = UsageRightsStatus.SYNTHETIC) -> RealImageRequest:
        return RealImageRequest(
            packet_id="packet-test",
            prompt="A neutral synthetic image edit for contract validation.",
            reference=self._reference(root, rights=rights),
        )

    def _plan(self, root: Path) -> Path:
        plan = root / "LIVE_CALL_PLAN.md"
        plan.write_text("synthetic local test plan\n", encoding="utf-8")
        return plan

    def _generate(
        self,
        provider: OpenAIImageProvider,
        request: RealImageRequest,
        root: Path,
        *,
        force_regenerate: bool = False,
    ):
        return provider.generate_image(
            request,
            output_dir=root / "output",
            allow_network=True,
            confirm_live_call=True,
            live_call_plan=self._plan(root),
            force_regenerate=force_regenerate,
        )

    def _assert_provider_error(self, code: ProviderErrorCode, operation) -> RealProviderError:
        with self.assertRaises(RealProviderError) as context:
            operation()
        self.assertEqual(context.exception.failure.error_code, code)
        return context.exception

    def test_missing_auth_fails_closed_without_transport_or_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = self._request(root)
            output = root / "output"
            provider = OpenAIImageProvider()
            with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
                failure = self._assert_provider_error(
                    ProviderErrorCode.AUTH_MISSING,
                    lambda: provider.generate_image(
                        request,
                        output_dir=output,
                        allow_network=True,
                        confirm_live_call=True,
                        live_call_plan=self._plan(root),
                    ),
                )
            self.assertEqual(failure.failure.stage, "initialize")
            self.assertTrue(output.is_dir())
            self.assertEqual(list(output.iterdir()), [])

    def test_network_opt_in_gate_runs_before_transport(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transport = _RecordingTransport(_recorded_response())
            provider = OpenAIImageProvider(transport=transport)
            self._assert_provider_error(
                ProviderErrorCode.NETWORK_OPT_IN_REQUIRED,
                lambda: provider.generate_image(
                    self._request(root),
                    output_dir=root / "output",
                    allow_network=False,
                    confirm_live_call=True,
                    live_call_plan=self._plan(root),
                ),
            )
            self.assertEqual(transport.calls, [])
            self.assertFalse((root / "output").exists())

    def test_confirmation_gate_runs_before_transport(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transport = _RecordingTransport(_recorded_response())
            provider = OpenAIImageProvider(transport=transport)
            self._assert_provider_error(
                ProviderErrorCode.LIVE_CALL_CONFIRMATION_REQUIRED,
                lambda: provider.generate_image(
                    self._request(root),
                    output_dir=root / "output",
                    allow_network=True,
                    confirm_live_call=False,
                    live_call_plan=self._plan(root),
                ),
            )
            self.assertEqual(transport.calls, [])

    def test_live_call_plan_gate_runs_before_transport(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transport = _RecordingTransport(_recorded_response())
            provider = OpenAIImageProvider(transport=transport)
            self._assert_provider_error(
                ProviderErrorCode.LIVE_CALL_PLAN_MISSING,
                lambda: provider.generate_image(
                    self._request(root),
                    output_dir=root / "output",
                    allow_network=True,
                    confirm_live_call=True,
                    live_call_plan=root / "missing-plan.md",
                ),
            )
            self.assertEqual(transport.calls, [])

    def test_unknown_reference_rights_are_rejected_before_transport(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transport = _RecordingTransport(_recorded_response())
            provider = OpenAIImageProvider(transport=transport)
            failure = self._assert_provider_error(
                ProviderErrorCode.INVALID_INPUT,
                lambda: provider.generate_image(
                    self._request(root, rights=UsageRightsStatus.UNKNOWN),
                    output_dir=root / "output",
                    allow_network=True,
                    confirm_live_call=True,
                    live_call_plan=self._plan(root),
                ),
            )
            self.assertIn("UNKNOWN", failure.failure.sanitized_message)
            self.assertEqual(transport.calls, [])

    def test_cost_guard_rejects_call_count_and_estimated_cost(self) -> None:
        policies = (
            CostPolicy(max_calls_per_run=0, max_retry_count=0, max_estimated_cost_per_run=0.03),
            CostPolicy(max_calls_per_run=1, max_retry_count=0, max_estimated_cost_per_run=0.02),
        )
        for policy in policies:
            with self.subTest(policy=policy.to_dict()), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                transport = _RecordingTransport(_recorded_response())
                provider = OpenAIImageProvider(transport=transport, cost_policy=policy)
                self._assert_provider_error(
                    ProviderErrorCode.COST_LIMIT_EXCEEDED,
                    lambda: self._generate(provider, self._request(root), root),
                )
                self.assertEqual(transport.calls, [])
                self.assertFalse((root / "output").exists())

    def test_success_materializes_hashes_qa_provenance_and_manual_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            response = _recorded_response(request_id="request_synthetic_success")
            transport = _RecordingTransport(response)
            provider = OpenAIImageProvider(transport=transport)
            request = self._request(root)

            artifact = self._generate(provider, request, root)

            self.assertEqual(len(transport.calls), 1)
            self.assertEqual(artifact.mime, "image/png")
            self.assertEqual((artifact.width, artifact.height), (1024, 1024))
            self.assertEqual(artifact.sha256, sha256_hex(deterministic_png()))
            self.assertEqual(artifact.path.read_bytes(), deterministic_png())
            self.assertEqual(artifact.request_dedupe_key, request.dedupe_key)
            self.assertEqual(artifact.review_state, ReviewState.MANUAL_REVIEW_REQUIRED)
            self.assertFalse(artifact.reused)
            self.assertEqual(artifact.provider_request_id, "request_synthetic_success")

            provenance = json.loads(artifact.provenance_path.read_text(encoding="utf-8"))
            self.assertEqual(provenance["output_sha256"], artifact.sha256)
            self.assertEqual(provenance["input_hashes"]["reference_sha256"], request.reference.sha256)
            self.assertEqual(provenance["local_path"], artifact.path.name)
            self.assertEqual(provenance["provider"], "openai-image")
            provenance_text = json.dumps(provenance, sort_keys=True)
            self.assertNotIn("b64_json", provenance_text)
            self.assertNotIn("OPENAI_API_KEY", provenance_text)

            qa = json.loads(artifact.qa_path.read_text(encoding="utf-8"))
            self.assertEqual(qa["status"], "PASS")
            self.assertEqual(qa["blocking_reasons"], [])
            self.assertEqual(qa["decoded_dimensions"], {"height": 1024, "width": 1024})

            review_dirs = sorted(root.glob("output/review_package_*/"))
            self.assertEqual(len(review_dirs), 1)
            review = json.loads((review_dirs[0] / "review_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(review["review_state"], "MANUAL_REVIEW_REQUIRED")
            self.assertEqual(review["artifact"], artifact.path.name)
            self.assertEqual(review["provenance"], artifact.provenance_path.name)
            self.assertEqual(review["qa"], artifact.qa_path.name)

            registry = json.loads((root / "output" / REGISTRY_FILENAME).read_text(encoding="utf-8"))
            entry = registry["requests"][request.dedupe_key]
            self.assertEqual(entry["status"], "completed")
            self.assertEqual(entry["output_sha256"], artifact.sha256)

    def test_missing_provider_request_id_blocks_provenance_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            response = _recorded_response()
            response.pop("request_id")
            transport = _RecordingTransport(response)
            request = self._request(root)

            failure = self._assert_provider_error(
                ProviderErrorCode.PROVENANCE_INCOMPLETE,
                lambda: self._generate(OpenAIImageProvider(transport=transport), request, root),
            )

            self.assertEqual(failure.failure.stage, "provenance")
            registry = json.loads((root / "output" / REGISTRY_FILENAME).read_text(encoding="utf-8"))
            self.assertEqual(registry["requests"][request.dedupe_key]["status"], "in_flight")
            self.assertEqual(list((root / "output").glob("generated_image_*.png")), [])
            self.assertEqual(list((root / "output").glob("artifact_provenance_*.json")), [])
            self.assertEqual(list((root / "output").glob("review_package_*")), [])

    def test_generate_wrapper_requires_matching_request_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transport = _RecordingTransport(_recorded_response())
            provider = OpenAIImageProvider(transport=transport)
            request = self._request(root)
            failure = self._assert_provider_error(
                ProviderErrorCode.INVALID_INPUT,
                lambda: provider.generate(
                    "different prompt",
                    request=request,
                    output_dir=root / "output",
                ),
            )
            self.assertEqual(failure.failure.stage, "validate")
            self.assertEqual(transport.calls, [])

    def test_dedupe_reuses_completed_cache_and_force_changes_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transport = _RecordingTransport(
                _recorded_response(request_id="request_first"),
                _recorded_response(request_id="request_forced"),
            )
            provider = OpenAIImageProvider(transport=transport)
            request = self._request(root)

            first = self._generate(provider, request, root)
            reused = self._generate(provider, request, root)
            with patch("ai_content_factory.providers.openai_image.time.time_ns", return_value=123456):
                forced = self._generate(provider, request, root, force_regenerate=True)

            self.assertFalse(first.reused)
            self.assertTrue(reused.reused)
            self.assertFalse(forced.reused)
            self.assertEqual(len(transport.calls), 2)
            self.assertEqual(first.request_dedupe_key, reused.request_dedupe_key)
            self.assertNotEqual(first.request_dedupe_key, forced.request_dedupe_key)
            self.assertEqual(first.path, reused.path)
            self.assertNotEqual(first.path, forced.path)

            registry = json.loads((root / "output" / REGISTRY_FILENAME).read_text(encoding="utf-8"))
            self.assertEqual(len(registry["requests"]), 2)
            forced_entry = registry["requests"][forced.request_dedupe_key]
            self.assertEqual(forced_entry["base_dedupe_key"], request.dedupe_key)

    def test_incomplete_prior_dedupe_state_blocks_repeat_billable_call(self) -> None:
        for prior_status in ("in_flight", "failed"):
            with self.subTest(prior_status=prior_status), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                request = self._request(root)
                output = root / "output"
                output.mkdir()
                registry_path = output / REGISTRY_FILENAME
                registry_path.write_text(
                    json.dumps(
                        {
                            "schema_version": "1.0",
                            "requests": {
                                request.dedupe_key: {
                                    "base_dedupe_key": request.dedupe_key,
                                    "reference_sha256": request.reference.sha256,
                                    "status": prior_status,
                                }
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                transport = _RecordingTransport(_recorded_response())
                provider = OpenAIImageProvider(transport=transport)

                failure = self._assert_provider_error(
                    ProviderErrorCode.PROVENANCE_INCOMPLETE,
                    lambda: self._generate(provider, request, root),
                )

                self.assertEqual(failure.failure.stage, "dedupe")
                self.assertFalse(failure.failure.retryable)
                self.assertEqual(transport.calls, [])
                persisted_registry = json.loads(registry_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    persisted_registry["requests"][request.dedupe_key]["status"],
                    prior_status,
                )

    def test_malformed_base64_is_non_retryable_and_does_not_materialize(self) -> None:
        malformed = _recorded_response()
        malformed["data"][0]["b64_json"] = "not-valid-base64"
        transport = _RecordingTransport(malformed)
        policy = CostPolicy(max_calls_per_run=4, max_retry_count=3, max_estimated_cost_per_run=0.12)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = OpenAIImageProvider(transport=transport, cost_policy=policy)
            self._assert_provider_error(
                ProviderErrorCode.OUTPUT_INTEGRITY_FAILED,
                lambda: self._generate(provider, self._request(root), root),
            )
            self.assertEqual(len(transport.calls), 1)
            self.assertEqual(list((root / "output").glob("generated_image_*.png")), [])

    def test_client_error_is_not_retried(self) -> None:
        transport = _RecordingTransport(_StatusError(400))
        policy = CostPolicy(max_calls_per_run=4, max_retry_count=3, max_estimated_cost_per_run=0.12)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = OpenAIImageProvider(transport=transport, cost_policy=policy)
            with patch("ai_content_factory.providers.openai_image.time.sleep") as sleep:
                self._assert_provider_error(
                    ProviderErrorCode.INVALID_INPUT,
                    lambda: self._generate(provider, self._request(root), root),
                )
            self.assertEqual(len(transport.calls), 1)
            sleep.assert_not_called()

    def test_auth_rejection_is_not_retried(self) -> None:
        for status_code in (401, 403):
            with self.subTest(status_code=status_code), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                transport = _RecordingTransport(_StatusError(status_code))
                policy = CostPolicy(max_calls_per_run=4, max_retry_count=3, max_estimated_cost_per_run=0.12)
                with patch("ai_content_factory.providers.openai_image.time.sleep") as sleep:
                    self._assert_provider_error(
                        ProviderErrorCode.AUTH_REJECTED,
                        lambda: self._generate(
                            OpenAIImageProvider(transport=transport, cost_policy=policy),
                            self._request(root),
                            root,
                        ),
                    )
                self.assertEqual(len(transport.calls), 1)
                sleep.assert_not_called()

    def test_timeout_is_bounded_and_classified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transport = _RecordingTransport(TimeoutError("synthetic timeout"))
            provider = OpenAIImageProvider(transport=transport)
            failure = self._assert_provider_error(
                ProviderErrorCode.PROVIDER_TIMEOUT,
                lambda: self._generate(provider, self._request(root), root),
            )
            self.assertTrue(failure.failure.retryable)
            self.assertEqual(len(transport.calls), 1)

    def test_missing_response_fields_are_not_retried(self) -> None:
        missing_data = _recorded_response()
        missing_data.pop("data")
        missing_bytes = _recorded_response()
        missing_bytes["data"] = [{}]
        for response in (missing_data, missing_bytes):
            with self.subTest(keys=sorted(response)), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                transport = _RecordingTransport(response)
                failure = self._assert_provider_error(
                    ProviderErrorCode.PROVENANCE_INCOMPLETE,
                    lambda: self._generate(OpenAIImageProvider(transport=transport), self._request(root), root),
                )
                self.assertEqual(failure.failure.stage, "generate")
                self.assertEqual(len(transport.calls), 1)

    def test_wrong_image_dimensions_fail_qa_without_review_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transport = _RecordingTransport(_recorded_response(deterministic_png(512, 512)))
            failure = self._assert_provider_error(
                ProviderErrorCode.OUTPUT_INTEGRITY_FAILED,
                lambda: self._generate(OpenAIImageProvider(transport=transport), self._request(root), root),
            )
            self.assertEqual(failure.failure.stage, "media_qa")
            qa_files = list((root / "output").glob("qa_scorecard_*.json"))
            self.assertEqual(len(qa_files), 1)
            self.assertEqual(json.loads(qa_files[0].read_text(encoding="utf-8"))["status"], "FAIL")
            self.assertEqual(list((root / "output").glob("review_package_*")), [])

    def test_transient_failure_retries_once_with_bounded_cost(self) -> None:
        transport = _RecordingTransport(_StatusError(500), _recorded_response())
        policy = CostPolicy(max_calls_per_run=2, max_retry_count=1, max_estimated_cost_per_run=0.06)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = OpenAIImageProvider(transport=transport, cost_policy=policy)
            with patch("ai_content_factory.providers.openai_image.time.sleep") as sleep:
                artifact = self._generate(provider, self._request(root), root)
            self.assertTrue(artifact.path.is_file())
            self.assertEqual(len(transport.calls), 2)
            sleep.assert_called_once_with(1)

    def test_transient_failure_stops_after_retry_limit(self) -> None:
        transport = _RecordingTransport(_StatusError(500), _StatusError(500))
        policy = CostPolicy(max_calls_per_run=2, max_retry_count=1, max_estimated_cost_per_run=0.06)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = OpenAIImageProvider(transport=transport, cost_policy=policy)
            with patch("ai_content_factory.providers.openai_image.time.sleep") as sleep:
                failure = self._assert_provider_error(
                    ProviderErrorCode.PROVIDER_TRANSIENT_FAILURE,
                    lambda: self._generate(provider, self._request(root), root),
                )
            self.assertTrue(failure.failure.retryable)
            self.assertEqual(len(transport.calls), 2)
            sleep.assert_called_once_with(1)

    def test_retry_cost_guard_stops_before_second_billable_attempt(self) -> None:
        transport = _RecordingTransport(_StatusError(500), _recorded_response())
        policy = CostPolicy(max_calls_per_run=1, max_retry_count=3, max_estimated_cost_per_run=0.03)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = OpenAIImageProvider(transport=transport, cost_policy=policy)
            with patch("ai_content_factory.providers.openai_image.time.sleep") as sleep:
                self._assert_provider_error(
                    ProviderErrorCode.COST_LIMIT_EXCEEDED,
                    lambda: self._generate(provider, self._request(root), root),
                )
            self.assertEqual(len(transport.calls), 1)
            sleep.assert_not_called()

    def test_corrupt_cached_artifact_fails_closed_without_transport(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_transport = _RecordingTransport(_recorded_response())
            first_provider = OpenAIImageProvider(transport=first_transport)
            request = self._request(root)
            first = self._generate(first_provider, request, root)
            first.path.write_bytes(b"corrupt synthetic cache")

            second_transport = _RecordingTransport(_recorded_response())
            second_provider = OpenAIImageProvider(transport=second_transport)
            self._assert_provider_error(
                ProviderErrorCode.OUTPUT_INTEGRITY_FAILED,
                lambda: self._generate(second_provider, request, root),
            )
            self.assertEqual(second_transport.calls, [])

    def test_corrupt_registry_fails_closed_without_transport(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_transport = _RecordingTransport(_recorded_response())
            first_provider = OpenAIImageProvider(transport=first_transport)
            request = self._request(root)
            self._generate(first_provider, request, root)
            (root / "output" / REGISTRY_FILENAME).write_text("{not-json", encoding="utf-8")

            second_transport = _RecordingTransport(_recorded_response())
            second_provider = OpenAIImageProvider(transport=second_transport)
            self._assert_provider_error(
                ProviderErrorCode.PROVENANCE_INCOMPLETE,
                lambda: self._generate(second_provider, request, root),
            )
            self.assertEqual(second_transport.calls, [])

    def test_registry_path_escape_is_rejected_without_transport(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = self._request(root)
            self._generate(OpenAIImageProvider(transport=_RecordingTransport(_recorded_response())), request, root)
            registry_path = root / "output" / REGISTRY_FILENAME
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["requests"][request.dedupe_key]["artifact_path"] = "../outside.png"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            transport = _RecordingTransport(_recorded_response())
            failure = self._assert_provider_error(
                ProviderErrorCode.PROVENANCE_INCOMPLETE,
                lambda: self._generate(OpenAIImageProvider(transport=transport), request, root),
            )
            self.assertEqual(failure.failure.stage, "registry")
            self.assertEqual(transport.calls, [])

    def test_cached_provenance_tampering_is_rejected_without_transport(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = self._request(root)
            artifact = self._generate(
                OpenAIImageProvider(transport=_RecordingTransport(_recorded_response())),
                request,
                root,
            )
            provenance = json.loads(artifact.provenance_path.read_text(encoding="utf-8"))
            provenance["provider"] = "tampered-provider"
            artifact.provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
            transport = _RecordingTransport(_recorded_response())
            self._assert_provider_error(
                ProviderErrorCode.OUTPUT_INTEGRITY_FAILED,
                lambda: self._generate(OpenAIImageProvider(transport=transport), request, root),
            )
            self.assertEqual(transport.calls, [])

    def test_offline_fixture_registry_excludes_live_provider(self) -> None:
        providers = FixtureProviders().as_mapping()
        self.assertEqual(
            set(providers),
            {"research", "text", "image", "video", "voice"},
        )
        self.assertNotIn("openai-image", {getattr(value, "provider_id", "") for value in providers.values()})
        self.assertNotIsInstance(providers["image"], OpenAIImageProvider)
        self.assertTrue(all(getattr(value, "fixture_only", False) for value in providers.values()))

    def test_recorded_fixture_is_sanitized_and_not_materializable(self) -> None:
        fixture_path = REPOSITORY_ROOT / "fixtures" / "recorded" / "openai_image" / "success.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        encoded = payload["data"][0]["b64_json"]
        self.assertEqual(encoded, "SANITIZED_BINARY_OMITTED")
        fixture_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        for forbidden in ("OPENAI_API_KEY", "Authorization", "signed_url", "https://"):
            self.assertNotIn(forbidden, fixture_text)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transport = _RecordingTransport(payload)
            provider = OpenAIImageProvider(transport=transport)
            self._assert_provider_error(
                ProviderErrorCode.OUTPUT_INTEGRITY_FAILED,
                lambda: self._generate(provider, self._request(root), root),
            )
            self.assertEqual(len(transport.calls), 1)
            self.assertEqual(list((root / "output").glob("generated_image_*.png")), [])


if __name__ == "__main__":
    unittest.main()
