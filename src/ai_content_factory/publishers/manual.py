"""Human-handoff publisher with a local-only duplicate guard."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .base import (
    DuplicateGuard,
    PublishResult,
    _write_local_manifest,
    package_parts,
    remote_write_enabled,
)


class ManualPublisher:
    mode = "manual"

    def publish(
        self,
        package: Mapping[str, Any],
        *,
        output_dir: str | Path | None = None,
    ) -> PublishResult:
        package_id, platform_files, failure = package_parts(package)
        if failure is not None:
            return PublishResult(
                status="FAILED",
                mode=self.mode,
                remote_write=1 if remote_write_enabled() else 0,
                failure=failure,
            )

        manifest_file = None
        if output_dir is not None:
            root = Path(output_dir)
            marker = root / "manual_handoff.json"
            duplicate = DuplicateGuard.existing_marker_failure(marker, package_id or "")
            if duplicate is not None:
                return PublishResult(
                    status="DUPLICATE_PACKAGE",
                    mode=self.mode,
                    remote_write=0,
                    package_id=package_id,
                    platform_files=platform_files,
                    manifest_file=marker.name,
                    failure=duplicate,
                )
            _write_local_manifest(
                marker,
                {
                    "instructions": "Human review and publication are required; no remote write was performed.",
                    "mode": self.mode,
                    "package_id": package_id,
                    "platform_files": platform_files,
                    "remote_write": 0,
                    "status": "MANUAL_HANDOFF_READY",
                },
            )
            manifest_file = marker.name

        return PublishResult(
            status="MANUAL_HANDOFF_READY",
            mode=self.mode,
            remote_write=0,
            package_id=package_id,
            platform_files=platform_files,
            manifest_file=manifest_file,
            manual_action_required=True,
        )


__all__ = ["ManualPublisher"]
