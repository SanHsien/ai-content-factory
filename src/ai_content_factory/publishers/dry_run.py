"""A publisher that produces a local plan and performs no writes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .base import PublishResult, package_parts, remote_write_enabled


class DryRunPublisher:
    mode = "dry-run"

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
        return PublishResult(
            status="DRY_RUN_READY",
            mode=self.mode,
            remote_write=0,
            package_id=package_id,
            platform_files=platform_files,
            manual_action_required=True,
        )


__all__ = ["DryRunPublisher"]
