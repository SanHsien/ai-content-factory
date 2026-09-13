"""Experimental, explicit-opt-in GPT Image 2 reference-image provider."""

from __future__ import annotations

import base64
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from ai_content_factory.core.hashing import canonical_json_hash, sha256_hex
from ai_content_factory.media.real_image_qa import evaluate_real_image
from ai_content_factory.providers.contracts import BrandProfile
from ai_content_factory.providers.real_media import (
    CostPolicy,
    GeneratedMediaArtifact,
    ProviderErrorCode,
    RealImageRequest,
    RealProviderError,
    ReviewState,
    _provider_error,
)


PROVIDER_ID = "openai-image"
REGISTRY_FILENAME = "provider_request_registry.json"


class ImageTransport(Protocol):
    def edit_image(self, request: RealImageRequest, *, dedupe_key: str) -> Mapping[str, Any]: ...


def _model_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        result = value.model_dump(mode="json")
        return dict(result) if isinstance(result, Mapping) else {}
    if hasattr(value, "to_dict"):
        result = value.to_dict()
        return dict(result) if isinstance(result, Mapping) else {}
    return {}


class OfficialOpenAISDKTransport:
    """Thin wrapper around the official optional ``openai`` package."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise _provider_error(ProviderErrorCode.AUTH_MISSING, "initialize", "OPENAI_API_KEY is not configured.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise _provider_error(
                ProviderErrorCode.OPTIONAL_DEPENDENCY_MISSING,
                "initialize",
                "Install the optional openai-image dependency before using live mode.",
            ) from exc
        self._client = OpenAI(api_key=api_key, max_retries=0)

    def edit_image(self, request: RealImageRequest, *, dedupe_key: str) -> Mapping[str, Any]:
        with request.reference.path.open("rb") as reference:
            result = self._client.images.edit(
                model=request.model,
                image=reference,
                prompt=request.prompt,
                quality=request.quality,
                size=request.size,
                output_format="png",
                n=1,
                extra_headers={"Idempotency-Key": dedupe_key},
            )
        payload = _model_dict(result)
        request_id = getattr(result, "_request_id", None) or getattr(result, "request_id", None)
        if request_id:
            payload["request_id"] = str(request_id)
        data = payload.get("data")
        if isinstance(data, list) and data:
            item = _model_dict(data[0])
            payload["data"] = [item]
        return payload


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def _load_registry(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": "1.0", "requests": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _provider_error(
            ProviderErrorCode.PROVENANCE_INCOMPLETE,
            "registry",
            "Provider request registry is unreadable.",
            recoverable=False,
        ) from exc
    if not isinstance(value, dict) or not isinstance(value.get("requests"), dict):
        raise _provider_error(
            ProviderErrorCode.PROVENANCE_INCOMPLETE,
            "registry",
            "Provider request registry has an invalid shape.",
            recoverable=False,
        )
    return value


def _safe_registry_child(output_dir: Path, value: Any) -> Path:
    filename = str(value or "")
    candidate = Path(filename)
    if not filename or candidate.is_absolute() or candidate.name != filename:
        raise _provider_error(
            ProviderErrorCode.PROVENANCE_INCOMPLETE,
            "registry",
            "Provider request registry contains an unsafe local artifact reference.",
            recoverable=False,
        )
    resolved = (output_dir / candidate).resolve()
    if resolved.parent != output_dir.resolve():
        raise _provider_error(
            ProviderErrorCode.PROVENANCE_INCOMPLETE,
            "registry",
            "Provider request registry contains an unsafe local artifact reference.",
            recoverable=False,
        )
    return resolved


def _translate_exception(exc: Exception, stage: str) -> RealProviderError:
    status = getattr(exc, "status_code", None)
    code_value = str(getattr(exc, "code", ""))
    name = exc.__class__.__name__.lower()
    if code_value == "moderation_blocked":
        code, retryable = ProviderErrorCode.PROVIDER_REJECTED, False
    elif status in {401, 403}:
        code, retryable = ProviderErrorCode.AUTH_REJECTED, False
    elif status == 429:
        code, retryable = ProviderErrorCode.RATE_LIMITED, True
    elif status is not None and 500 <= int(status) <= 599:
        code, retryable = ProviderErrorCode.PROVIDER_TRANSIENT_FAILURE, True
    elif status is not None and 400 <= int(status) <= 499:
        code, retryable = ProviderErrorCode.INVALID_INPUT, False
    elif "timeout" in name:
        code, retryable = ProviderErrorCode.PROVIDER_TIMEOUT, True
    else:
        code, retryable = ProviderErrorCode.PROVIDER_TRANSIENT_FAILURE, False
    return _provider_error(
        code,
        stage,
        "The provider request failed; secret-bearing response details were omitted.",
        retryable=retryable,
        recoverable=retryable,
        provider=PROVIDER_ID,
    )


def _safe_response_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "background": str(value.get("background", "")),
        "output_format": "png",
        "quality": str(value.get("quality", "")),
        "size": str(value.get("size", "")),
        "usage": value.get("usage") if isinstance(value.get("usage"), Mapping) else None,
    }


class OpenAIImageProvider:
    fixture_only = False
    provider_id = PROVIDER_ID

    def __init__(self, *, transport: ImageTransport | None = None, cost_policy: CostPolicy | None = None) -> None:
        self._transport = transport
        self.cost_policy = cost_policy or CostPolicy()

    def generate(
        self,
        prompt: str,
        *,
        topic: str | None = None,
        brand: BrandProfile | None = None,
        request: RealImageRequest | None = None,
        output_dir: Path | None = None,
        allow_network: bool = False,
        confirm_live_call: bool = False,
        live_call_plan: Path | None = None,
        force_regenerate: bool = False,
    ) -> GeneratedMediaArtifact:
        del topic, brand
        if request is None or output_dir is None or prompt != request.prompt:
            raise _provider_error(
                ProviderErrorCode.INVALID_INPUT,
                "validate",
                "Real image generation requires a matching request and output directory.",
                recoverable=False,
                provider=PROVIDER_ID,
            )
        return self.generate_image(
            request,
            output_dir=output_dir,
            allow_network=allow_network,
            confirm_live_call=confirm_live_call,
            live_call_plan=live_call_plan,
            force_regenerate=force_regenerate,
        )

    def generate_image(
        self,
        request: RealImageRequest,
        *,
        output_dir: Path,
        allow_network: bool,
        confirm_live_call: bool,
        live_call_plan: Path | None,
        force_regenerate: bool = False,
    ) -> GeneratedMediaArtifact:
        try:
            request.validate()
        except ValueError as exc:
            raise _provider_error(
                ProviderErrorCode.INVALID_INPUT,
                "validate",
                str(exc),
                recoverable=False,
                provider=PROVIDER_ID,
            ) from exc
        if not allow_network:
            raise _provider_error(
                ProviderErrorCode.NETWORK_OPT_IN_REQUIRED,
                "authorize",
                "Live provider mode requires --allow-network.",
                provider=PROVIDER_ID,
            )
        if not confirm_live_call:
            raise _provider_error(
                ProviderErrorCode.LIVE_CALL_CONFIRMATION_REQUIRED,
                "authorize",
                "Live provider mode requires --confirm-live-call.",
                provider=PROVIDER_ID,
            )
        if live_call_plan is None or not live_call_plan.is_file():
            raise _provider_error(
                ProviderErrorCode.LIVE_CALL_PLAN_MISSING,
                "authorize",
                "A reviewed LIVE_CALL_PLAN.md is required before any billable call.",
                provider=PROVIDER_ID,
            )

        self.cost_policy.validate(calls=1, retries=0, estimated_cost=request.estimated_cost_usd)
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        registry_path = output_dir / REGISTRY_FILENAME
        registry = _load_registry(registry_path)
        base_key = request.dedupe_key
        dedupe_key = (
            canonical_json_hash({"base": base_key, "force_nonce_ns": time.time_ns()})
            if force_regenerate
            else base_key
        )
        entry = registry["requests"].get(dedupe_key)
        reused = self._reuse_completed(entry, output_dir, request, dedupe_key)
        if reused is not None:
            return reused

        transport = self._transport
        if transport is None:
            credential_value = os.environ.get("OPENAI_API_KEY", "")
            if not credential_value:
                raise _provider_error(
                    ProviderErrorCode.AUTH_MISSING,
                    "initialize",
                    "OPENAI_API_KEY is not configured in the process environment.",
                    provider=PROVIDER_ID,
                )
            transport = OfficialOpenAISDKTransport(credential_value)

        submitted_at = _utc_now()
        registry["requests"][dedupe_key] = {
            "base_dedupe_key": base_key,
            "estimated_cost_usd": request.estimated_cost_usd,
            "prompt_sha256": request.prompt_sha256,
            "reference_sha256": request.reference.sha256,
            "request_timestamp": submitted_at,
            "status": "in_flight",
        }
        _atomic_json(registry_path, registry)
        try:
            response = self._call_with_retries(
                lambda: transport.edit_image(request, dedupe_key=dedupe_key),
                stage="generate",
                estimated_cost_per_call=request.estimated_cost_usd,
            )
        except RealProviderError as exc:
            registry["requests"][dedupe_key].update(
                {
                    "error_code": exc.failure.error_code.value,
                    "retryable": exc.failure.retryable,
                    "status": "failed",
                }
            )
            _atomic_json(registry_path, registry)
            raise
        provider_request_id = str(response.get("request_id", ""))
        if not provider_request_id:
            raise _provider_error(
                ProviderErrorCode.PROVENANCE_INCOMPLETE,
                "provenance",
                "Provider response omitted a request identifier required for provenance.",
                recoverable=False,
                provider=PROVIDER_ID,
            )
        data_items = response.get("data")
        if not isinstance(data_items, list) or not data_items or not isinstance(data_items[0], Mapping):
            raise _provider_error(
                ProviderErrorCode.PROVENANCE_INCOMPLETE,
                "generate",
                "Provider response omitted image result data.",
                recoverable=False,
                provider=PROVIDER_ID,
            )
        encoded = data_items[0].get("b64_json")
        if not isinstance(encoded, str) or not encoded:
            raise _provider_error(
                ProviderErrorCode.PROVENANCE_INCOMPLETE,
                "generate",
                "Provider response omitted base64 image bytes.",
                recoverable=False,
                provider=PROVIDER_ID,
            )
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise _provider_error(
                ProviderErrorCode.OUTPUT_INTEGRITY_FAILED,
                "materialize",
                "Provider returned malformed base64 image bytes.",
                recoverable=False,
                provider=PROVIDER_ID,
            ) from exc

        suffix = dedupe_key[:16]
        artifact_path = output_dir / f"generated_image_{suffix}.png"
        _atomic_bytes(artifact_path, data)
        output_hash = sha256_hex(data)
        width, height = request.output_dimensions
        completed_at = _utc_now()
        provenance = {
            "artifact_id": f"real-image-{output_hash[:16]}",
            "completion_timestamp": completed_at,
            "cost": {
                "currency": "USD",
                "estimated_max": request.estimated_cost_usd,
                "note": "Low-quality output estimate plus conservative input-token allowance.",
            },
            "dimensions": {"height": height, "width": width},
            "input_hashes": {"reference_sha256": request.reference.sha256},
            "local_path": artifact_path.name,
            "mime": "image/png",
            "model": request.model,
            "output_sha256": output_hash,
            "prompt_sha256": request.prompt_sha256,
            "provider": PROVIDER_ID,
            "provider_metadata": _safe_response_metadata(response),
            "provider_request_id": provider_request_id,
            "request_dedupe_key": dedupe_key,
            "request_timestamp": submitted_at,
            "usage_rights_note": "Input rights must be established; output use remains subject to applicable law and provider terms.",
        }
        provenance_path = output_dir / f"artifact_provenance_{suffix}.json"
        _atomic_json(provenance_path, provenance)
        qa = evaluate_real_image(
            artifact_path,
            expected_sha256=output_hash,
            expected_width=width,
            expected_height=height,
        )
        qa_path = output_dir / f"qa_scorecard_{suffix}.json"
        _atomic_json(qa_path, qa)
        if qa["status"] != "PASS":
            raise _provider_error(
                ProviderErrorCode.OUTPUT_INTEGRITY_FAILED,
                "media_qa",
                "Generated artifact failed local image QA.",
                recoverable=False,
                provider=PROVIDER_ID,
            )

        review_dir = output_dir / f"review_package_{suffix}"
        review_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(artifact_path, review_dir / artifact_path.name)
        shutil.copyfile(provenance_path, review_dir / provenance_path.name)
        shutil.copyfile(qa_path, review_dir / qa_path.name)
        _atomic_json(
            review_dir / "review_manifest.json",
            {
                "artifact": artifact_path.name,
                "cost_summary": provenance["cost"],
                "prompt_summary": {"sha256": request.prompt_sha256},
                "provider_summary": {"model": request.model, "provider": PROVIDER_ID},
                "provenance": provenance_path.name,
                "qa": qa_path.name,
                "review_state": ReviewState.MANUAL_REVIEW_REQUIRED.value,
            },
        )
        registry["requests"][dedupe_key] = {
            "artifact_path": artifact_path.name,
            "base_dedupe_key": base_key,
            "completion_timestamp": completed_at,
            "estimated_cost_usd": request.estimated_cost_usd,
            "output_sha256": output_hash,
            "provenance_path": provenance_path.name,
            "provider_request_id": provider_request_id,
            "qa_path": qa_path.name,
            "request_timestamp": submitted_at,
            "status": "completed",
        }
        _atomic_json(registry_path, registry)
        return GeneratedMediaArtifact(
            artifact_id=str(provenance["artifact_id"]),
            path=artifact_path,
            sha256=output_hash,
            mime="image/png",
            provider=PROVIDER_ID,
            provider_request_id=provider_request_id,
            model=request.model,
            width=width,
            height=height,
            request_dedupe_key=dedupe_key,
            provenance_path=provenance_path,
            qa_path=qa_path,
        )

    def _reuse_completed(
        self,
        entry: Any,
        output_dir: Path,
        request: RealImageRequest,
        dedupe_key: str,
    ) -> GeneratedMediaArtifact | None:
        if not isinstance(entry, Mapping):
            return None
        if entry.get("status") != "completed":
            raise _provider_error(
                ProviderErrorCode.PROVENANCE_INCOMPLETE,
                "dedupe",
                "A prior request has a non-completed state; operator review is required before force regeneration.",
                recoverable=False,
                provider=PROVIDER_ID,
            )
        artifact_path = _safe_registry_child(output_dir, entry.get("artifact_path"))
        provenance_path = _safe_registry_child(output_dir, entry.get("provenance_path"))
        qa_path = _safe_registry_child(output_dir, entry.get("qa_path"))
        expected_hash = str(entry.get("output_sha256", ""))
        if (
            not artifact_path.is_file()
            or not provenance_path.is_file()
            or not qa_path.is_file()
            or sha256_hex(artifact_path.read_bytes()) != expected_hash
        ):
            raise _provider_error(
                ProviderErrorCode.OUTPUT_INTEGRITY_FAILED,
                "dedupe",
                "Cached generated artifact failed integrity verification.",
                recoverable=False,
                provider=PROVIDER_ID,
            )
        width, height = request.output_dimensions
        try:
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            qa = json.loads(qa_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise _provider_error(
                ProviderErrorCode.PROVENANCE_INCOMPLETE,
                "dedupe",
                "Cached provenance or QA record is unreadable.",
                recoverable=False,
                provider=PROVIDER_ID,
            ) from exc
        provider_request_id = str(entry.get("provider_request_id", ""))
        if (
            not isinstance(provenance, Mapping)
            or not isinstance(qa, Mapping)
            or provenance.get("output_sha256") != expected_hash
            or provenance.get("request_dedupe_key") != dedupe_key
            or provenance.get("provider") != PROVIDER_ID
            or provenance.get("provider_request_id") != provider_request_id
            or not provider_request_id
            or qa.get("status") != "PASS"
            or evaluate_real_image(
                artifact_path,
                expected_sha256=expected_hash,
                expected_width=width,
                expected_height=height,
            )["status"]
            != "PASS"
        ):
            raise _provider_error(
                ProviderErrorCode.OUTPUT_INTEGRITY_FAILED,
                "dedupe",
                "Cached provenance, QA, or artifact evidence failed integrity verification.",
                recoverable=False,
                provider=PROVIDER_ID,
            )
        return GeneratedMediaArtifact(
            artifact_id=f"real-image-{expected_hash[:16]}",
            path=artifact_path,
            sha256=expected_hash,
            mime="image/png",
            provider=PROVIDER_ID,
            provider_request_id=provider_request_id,
            model=request.model,
            width=width,
            height=height,
            request_dedupe_key=dedupe_key,
            provenance_path=provenance_path,
            qa_path=qa_path,
            reused=True,
        )

    def _call_with_retries(self, operation, *, stage: str, estimated_cost_per_call: float):
        attempts = self.cost_policy.max_retry_count + 1
        for attempt in range(attempts):
            try:
                return operation()
            except RealProviderError:
                raise
            except Exception as exc:
                translated = _translate_exception(exc, stage)
                if not translated.failure.retryable or attempt + 1 >= attempts:
                    raise translated from exc
                self.cost_policy.validate(
                    calls=attempt + 2,
                    retries=attempt + 1,
                    estimated_cost=(attempt + 2) * estimated_cost_per_call,
                )
                time.sleep(min(2**attempt, 4))
        raise AssertionError("unreachable retry loop")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = ["ImageTransport", "OfficialOpenAISDKTransport", "OpenAIImageProvider", "PROVIDER_ID"]
