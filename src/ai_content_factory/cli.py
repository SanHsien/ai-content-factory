"""Command-line entry points for AI Content Factory."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

if __package__ in (None, ""):
    # Support ``python src/ai_content_factory/cli.py demo`` without requiring
    # an editable install or a project-level configuration file.
    _src_root = Path(__file__).resolve().parents[1]
    if str(_src_root) not in sys.path:
        sys.path.insert(0, str(_src_root))

from ai_content_factory.pipeline import (
    DEMO_TOPIC,
    PipelineOrchestrator,
    Stage,
    inspect_output,
    run_demo,
    validate_output,
)
from ai_content_factory.pipeline.models import BrandProfile, PipelineResult, canonical_json
from ai_content_factory.publishers import DryRunPublisher
if TYPE_CHECKING:
    from ai_content_factory.providers.real_media import RealImageRequest


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_demo_output() -> Path:
    return repository_root() / "output"


def _load_brand(path: str | Path | None) -> BrandProfile:
    if path is None:
        return BrandProfile()
    candidate = Path(path)
    try:
        with candidate.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Brand file could not be read as local JSON.") from exc
    if not isinstance(value, Mapping):
        raise ValueError("Brand file must contain a JSON object.")
    return BrandProfile.from_dict(value)


def _print_json(value: Mapping[str, Any]) -> None:
    print(canonical_json(value))


def _result_exit(result: PipelineResult) -> int:
    _print_json(result.summary())
    return 0 if result.succeeded else 1


def _stage_argument(value: str | None) -> Stage | None:
    if value is None:
        return None
    try:
        return Stage(value.upper())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Unknown stage: {value}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-content-factory",
        description="Build a deterministic content package with provider-neutral contracts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="Run the public-safe offline demo.")
    demo.add_argument("--output", type=Path, default=default_demo_output())
    demo.add_argument("--resume", action="store_true")
    demo.add_argument("--stop-after", type=_stage_argument)

    run = subparsers.add_parser("run", help="Run a local topic through the pipeline.")
    run.add_argument("--topic", required=True)
    run.add_argument("--brand", type=Path)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--stop-after", type=_stage_argument)

    resume = subparsers.add_parser("resume", help="Resume a paused or failed local run.")
    resume.add_argument("--output", type=Path, required=True)
    resume.add_argument("--stop-after", type=_stage_argument)

    inspect = subparsers.add_parser("inspect", help="Inspect persisted state without writing.")
    inspect.add_argument("--output", type=Path, required=True)

    validate = subparsers.add_parser("validate", help="Validate local artifacts without writing.")
    validate.add_argument("--output", type=Path, required=True)
    validate.add_argument("--topic")

    generate = subparsers.add_parser(
        "generate-media",
        help="Run one experimental real-media request with explicit network and cost consent.",
    )
    generate.add_argument("--provider", choices=("openai-image",), required=True)
    generate.add_argument("--input", type=Path, required=True)
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument(
        "--live-call-plan",
        type=Path,
        required=True,
        help="Explicit reviewed plan; no provider plan is bundled with the public RC.",
    )
    generate.add_argument("--allow-network", action="store_true")
    generate.add_argument("--confirm-live-call", action="store_true")
    generate.add_argument("--force-regenerate", action="store_true")

    render_video = subparsers.add_parser(
        "render-video",
        help="Render one local hero image into an offline vertical motion video.",
    )
    render_video.add_argument("--image", type=Path, required=True)
    render_video.add_argument("--output", type=Path, required=True)
    render_video.add_argument("--output-name", default="public_demo.mp4")
    render_video.add_argument(
        "--preset",
        default="GENTLE_PUSH_IN",
        choices=("GENTLE_PUSH_IN", "SLOW_PAN", "EDITORIAL_SHORT", "WARM_MEMORY"),
    )
    render_video.add_argument("--duration", type=float, default=8.0)
    render_video.add_argument("--hook", default="")
    render_video.add_argument("--subtitle", default="")
    render_video.add_argument("--cta", default="")
    render_video.add_argument("--brand-config", type=Path)
    render_video.add_argument("--qa", type=Path)
    render_video.add_argument("--no-network", action="store_true")
    render_video.add_argument(
        "--provenance",
        choices=("CHATGPT_HANDOFF", "CODEX_NATIVE", "SYNTHETIC", "PRIVATE_OWNED"),
    )
    return parser


def _package_from_output(output_dir: Path) -> Mapping[str, Any]:
    with (output_dir / "publish_manifest.json").open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping):
        raise ValueError("publish_package.json must contain an object")
    return value


def _load_real_image_request(path: Path) -> "RealImageRequest":
    from ai_content_factory.providers.real_media import (
        RealImageRequest,
        ReferenceAsset,
        UsageRightsStatus,
    )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Real-media input could not be read as JSON.") from exc
    if not isinstance(value, Mapping) or not isinstance(value.get("reference"), Mapping):
        raise ValueError("Real-media input must contain a reference object.")
    reference_value = value["reference"]
    reference_path = Path(str(reference_value.get("path", "")))
    if not reference_path.is_absolute():
        reference_path = (path.parent / reference_path).resolve()
    dimensions = reference_value.get("dimensions", {})
    dimensions = dimensions if isinstance(dimensions, Mapping) else {}
    try:
        rights = UsageRightsStatus(str(reference_value.get("usage_rights_status", "UNKNOWN")))
    except ValueError as exc:
        raise ValueError("Unknown reference usage_rights_status.") from exc
    reference = ReferenceAsset(
        artifact_id=str(reference_value.get("artifact_id", "")),
        path=reference_path,
        sha256=str(reference_value.get("sha256", "")),
        mime=str(reference_value.get("mime", "")),
        width=int(dimensions.get("width", 0)),
        height=int(dimensions.get("height", 0)),
        source_type=str(reference_value.get("source_type", "")),
        usage_rights_status=rights,
        provenance=str(reference_value.get("provenance", "")),
        consent_or_ownership_status=str(reference_value.get("consent_or_ownership_status", "")),
    )
    metadata = value.get("metadata", {})
    return RealImageRequest(
        packet_id=str(value.get("packet_id", "")),
        prompt=str(value.get("prompt", "")),
        reference=reference,
        model=str(value.get("model", "gpt-image-2")),
        quality=str(value.get("quality", "low")),
        size=str(value.get("size", "1024x1024")),
        metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
    )


def _run_generate_media(args: argparse.Namespace) -> int:
    from ai_content_factory.providers.openai_image import OpenAIImageProvider
    from ai_content_factory.providers.real_media import RealProviderError

    try:
        request = _load_real_image_request(args.input)
        artifact = OpenAIImageProvider().generate_image(
            request,
            output_dir=args.output,
            allow_network=args.allow_network,
            confirm_live_call=args.confirm_live_call,
            live_call_plan=args.live_call_plan,
            force_regenerate=args.force_regenerate,
        )
        _print_json({"artifact": artifact.to_dict(), "status": "MANUAL_REVIEW_REQUIRED"})
        return 0
    except RealProviderError as exc:
        _print_json({"failure": exc.failure.to_dict(), "status": "FAILED"})
        return 3


def _run_render_video(args: argparse.Namespace) -> int:
    from ai_content_factory.media.image_sources import (
        HeroImageArtifact,
        ImageProvenance,
    )
    from ai_content_factory.media.motion_render import (
        MotionRenderError,
        MotionRenderVideoProvider,
    )
    from ai_content_factory.media.video_contracts import (
        VideoGenerationMode,
        VideoRenderRequest,
    )

    try:
        if args.brand_config is not None and not args.brand_config.is_file():
            raise ValueError("Private brand config is unavailable.")
        provenance_name = args.provenance
        if provenance_name is None:
            provenance_name = "PRIVATE_OWNED" if args.brand_config else "CHATGPT_HANDOFF"
        provenance = ImageProvenance(provenance_name)
        hero = HeroImageArtifact.from_file(
            args.image,
            artifact_id=f"hero-{args.image.stem}",
            provenance=provenance,
            source=provenance.value,
        )
        request = VideoRenderRequest(
            request_id=f"motion-{hero.sha256[:20]}",
            generation_mode=VideoGenerationMode.MOTION_RENDER,
            prompt=args.hook or args.subtitle or "Local deterministic motion render.",
            hero_image=hero,
            source_image_artifact_id=hero.artifact_id,
            aspect_ratio="9:16",
            motion_preset=args.preset,
            caption_mode="OPTIONAL_TEXT",
            voice_mode="NONE",
            brand_config_reference=args.brand_config,
            output_format="mp4",
            width=1080,
            height=1920,
            duration_seconds=args.duration,
            fps=30,
            provenance=provenance,
            metadata={
                "cta": args.cta,
                "hook": args.hook,
                "output_name": args.output_name,
                "subtitle": args.subtitle,
            },
        )
        artifact = MotionRenderVideoProvider().render_contract(
            request,
            output_dir=args.output,
        )
        manifest_path = artifact.path.parent / "video_artifact.json"
        manifest_path.write_text(canonical_json(artifact.to_dict()), encoding="utf-8")
        copied_qa: list[str] = []
        if args.qa is not None:
            args.qa.mkdir(parents=True, exist_ok=True)
            for name in ("video_qa.json", "video_provenance.json", "video_artifact.json"):
                source = artifact.path.parent / name
                if source.is_file():
                    destination = args.qa / f"{artifact.artifact_id}-{name}"
                    shutil.copy2(source, destination)
                    copied_qa.append(destination.name)
        _print_json(
            {
                "artifact": artifact.to_dict(),
                "generation_mode": VideoGenerationMode.MOTION_RENDER.value,
                "network": "DISABLED",
                "qa_copies": copied_qa,
                "status": "MANUAL_REVIEW_REQUIRED",
            }
        )
        return 0
    except MotionRenderError as exc:
        _print_json({"failure": exc.to_dict(), "status": "FAILED"})
        return 4


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = run_demo(
                args.output,
                resume=args.resume,
                stop_after=args.stop_after,
            )
            summary = result.summary()
            if result.succeeded and (result.output_dir / "publish_manifest.json").is_file():
                dry_run = DryRunPublisher().publish(_package_from_output(result.output_dir))
                summary["publisher"] = dry_run.to_dict()
                summary["visible_artifact"] = str(result.output_dir / "demo_preview.html")
            _print_json(summary)
            return 0 if result.succeeded else 1

        if args.command == "run":
            result = PipelineOrchestrator().run(
                args.topic,
                brand=_load_brand(args.brand),
                output_dir=args.output,
                resume=args.resume,
                stop_after=args.stop_after,
            )
            return _result_exit(result)

        if args.command == "resume":
            result = PipelineOrchestrator().resume(
                args.output,
                stop_after=args.stop_after,
            )
            return _result_exit(result)

        if args.command == "inspect":
            _print_json(inspect_output(args.output))
            return 0

        if args.command == "validate":
            report = validate_output(args.output, expected_topic=args.topic)
            _print_json(report.to_dict())
            return 0 if report.valid else 1

        if args.command == "generate-media":
            return _run_generate_media(args)
        if args.command == "render-video":
            return _run_render_video(args)
    except (OSError, ValueError, KeyError):
        _print_json(
            {
                "status": "FAILED",
                "failure": {
                    "code": "CLI_INPUT_ERROR",
                    "message": "CLI input or local filesystem validation failed; private path details were omitted.",
                },
            }
        )
        return 2
    return 2


__all__ = [
    "DEMO_TOPIC",
    "build_parser",
    "default_demo_output",
    "main",
    "repository_root",
    "_load_real_image_request",
    "_run_render_video",
]


if __name__ == "__main__":
    raise SystemExit(main())
