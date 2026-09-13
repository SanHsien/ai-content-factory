"""Integrity primitives exposed as a focused module."""

from .models import (
    ContentPacket,
    IntegritySnapshot,
    IntegrityValidationResult,
)


def capture_integrity_snapshot(packet: ContentPacket) -> IntegritySnapshot:
    return packet.capture_integrity_snapshot()


def validate_packet_integrity(packet: ContentPacket, snapshot=None) -> IntegrityValidationResult:
    return packet.validate_integrity(snapshot)


__all__ = [
    "ContentPacket",
    "IntegritySnapshot",
    "IntegrityValidationResult",
    "capture_integrity_snapshot",
    "validate_packet_integrity",
]
