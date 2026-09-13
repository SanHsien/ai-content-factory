"""Structured validation and approval errors for the core contracts.

The core package deliberately does not depend on a validation framework.  The
small result/error types in this module are used by schema and integrity
validation so callers can inspect failures without parsing exception strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, slots=True)
class ValidationError:
    """One structured validation failure.

    ``path`` uses a JSON-pointer-like dotted form (for example,
    ``artifacts[0].sha256``).  ``details`` is intentionally a JSON-compatible
    mapping when callers need machine-readable context in addition to the
    stable error code.
    """

    code: str
    path: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code:
            raise ValueError("ValidationError.code must be a non-empty string")
        if not isinstance(self.path, str) or not self.path:
            raise ValueError("ValidationError.path must be a non-empty string")
        if not isinstance(self.message, str) or not self.message:
            raise ValueError("ValidationError.message must be a non-empty string")
        object.__setattr__(self, "details", dict(self.details))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation of the error."""

        result: dict[str, Any] = {
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }
        if self.details:
            result["details"] = dict(self.details)
        return result

    as_dict = to_dict


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Validation outcome that behaves like a read-only error collection."""

    errors: tuple[ValidationError, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "errors", tuple(self.errors))

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def is_valid(self) -> bool:
        """Alias useful at call sites that prefer a predicate-style name."""

        return self.valid

    @property
    def ok(self) -> bool:
        return self.valid

    def __bool__(self) -> bool:
        return self.valid

    def __iter__(self):
        return iter(self.errors)

    def __len__(self) -> int:
        return len(self.errors)

    def __getitem__(self, index):
        return self.errors[index]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [error.to_dict() for error in self.errors],
        }

    as_dict = to_dict

    def raise_for_errors(self, message: str = "Validation failed") -> None:
        if not self.valid:
            raise SchemaValidationError(self.errors, message=message)


class SchemaValidationError(ValueError):
    """Exception raised when a caller requests fail-fast schema validation."""

    def __init__(
        self,
        errors: Iterable[ValidationError],
        *,
        message: str = "Schema validation failed",
    ) -> None:
        self.errors = tuple(errors)
        self.result = ValidationResult(self.errors)
        super().__init__(message)


class ApprovalError(ValueError):
    """Exception raised when an approval operation cannot be completed."""

    def __init__(
        self,
        message: str,
        *,
        errors: Iterable[ValidationError] = (),
    ) -> None:
        self.errors = tuple(errors)
        self.result = ValidationResult(self.errors)
        super().__init__(message)


__all__ = [
    "ApprovalError",
    "SchemaValidationError",
    "ValidationError",
    "ValidationResult",
]
