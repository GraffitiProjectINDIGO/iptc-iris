"""Shared geometry boundary types."""

from __future__ import annotations

import math
from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Protocol

from iptc_iris.models import Severity, ValidationIssue
from iptc_iris.spec import ALLOWED_UNITS, BOUNDARY_KEYS

# Keep the static type and runtime validator in sync with spec.ALLOWED_UNITS.
assert ALLOWED_UNITS == {"pixel", "relative"}
BoundaryUnit = Literal["pixel", "relative"]
UNSET = object()


class RegionBoundary(Protocol):
    """Common behavior provided by all parsed boundary objects."""

    @property
    def raw(self) -> Any:
        """Return the original parsed representation when available."""
        ...

    @property
    def valid(self) -> bool:
        """Return whether the boundary has no validation errors."""
        ...

    def as_dict(self) -> Any:
        """Return the canonical JSON-compatible representation."""
        ...

    def raw_dict(self) -> Any:
        """Return the original parsed representation when available."""
        ...

    def _dict_existing(self) -> Any:
        """Return existing boundary fields for diagnostic rendering."""
        ...

    def validate(
        self,
        path: str | None = None,
        *,
        image_width: float | None = None,
        image_height: float | None = None,
        ignore_dimensions: bool = False,
    ) -> list[ValidationIssue]:
        """Return boundary-specific validation issues."""
        ...

    def change_unit(
        self,
        unit: BoundaryUnit,
        *,
        image_width: float | int,
        image_height: float | int,
        allow_malformed: bool = False,
    ) -> RegionBoundary:
        """Return a copy converted to another measuring unit."""
        ...


@dataclass(frozen=True)
class UnknownBoundary:
    """Boundary object used when rbShape is missing or unsupported."""

    raw: dict[str, Any]

    @property
    def valid(self) -> bool:
        """Return false because the boundary shape is unsupported."""

        return False

    def as_dict(self) -> dict[str, Any]:
        """Return the original boundary fields unchanged."""

        return dict(self.raw)

    def raw_dict(self) -> dict[str, Any]:
        """Return the raw boundary object captured during parsing."""

        return dict(self.raw)

    def _dict_existing(self) -> dict[str, Any]:
        """Return the raw boundary object for diagnostic rendering."""

        return dict(self.raw)

    def validate(
        self,
        path: str | None = None,
        *,
        image_width: float | None = None,
        image_height: float | None = None,
        ignore_dimensions: bool = False,
    ) -> list[ValidationIssue]:
        """Return issues for an unsupported boundary shape."""

        path = "UnknownBoundary" if path is None else path
        issues = validate_unknown_fields(self.raw, BOUNDARY_KEYS, path)
        issues.append(
            ValidationIssue(
                "error",
                "INVALID_BOUNDARY_SHAPE",
                f"{path}.rbShape",
                "Boundary Shape must be one of: circle, linestring, multilinestring, "
                "multipoint, multipolygon, point, polygon, rectangle.",
            )
        )
        return issues

    def change_unit(
        self,
        unit: BoundaryUnit,
        *,
        image_width: float | int,
        image_height: float | int,
        allow_malformed: bool = False,
    ) -> UnknownBoundary:
        """Reject unit conversion for an unsupported boundary shape."""

        raise ValueError("Cannot change unit for an unknown Region Boundary shape.")


@dataclass(frozen=True)
class InvalidBoundary:
    """Boundary placeholder for values that are not objects."""

    raw: Any

    @property
    def valid(self) -> bool:
        """Return false because the boundary is not an object."""

        return False

    def as_dict(self) -> Any:
        """Return the invalid raw value for diagnostic rendering."""

        return self.raw

    def raw_dict(self) -> Any:
        """Return the invalid raw boundary value unchanged."""

        return self.raw

    def _dict_existing(self) -> Any:
        """Return the invalid raw boundary value for diagnostic rendering."""

        return self.raw

    def validate(
        self,
        path: str | None = None,
        *,
        image_width: float | None = None,
        image_height: float | None = None,
        ignore_dimensions: bool = False,
    ) -> list[ValidationIssue]:
        """Return the non-object boundary validation error."""

        path = "InvalidBoundary" if path is None else path
        return [ValidationIssue("error", "BOUNDARY_NOT_OBJECT", path, "Region Boundary must be an object.")]

    def change_unit(
        self,
        unit: BoundaryUnit,
        *,
        image_width: float | int,
        image_height: float | int,
        allow_malformed: bool = False,
    ) -> InvalidBoundary:
        """Reject unit conversion for a non-object boundary value."""

        raise ValueError("Cannot change unit for a non-object Region Boundary.")


@dataclass(frozen=True)
class MissingBoundary:
    """Boundary placeholder used when a region has no regionBoundary key."""

    raw: None = None

    @property
    def valid(self) -> bool:
        """Return false because the region has no boundary."""

        return False

    def as_dict(self) -> None:
        """Return None for the absent boundary."""

        return None

    def raw_dict(self) -> None:
        """Return None for the absent raw boundary."""

        return None

    def _dict_existing(self) -> None:
        """Return None for diagnostic rendering of an absent boundary."""

        return None

    def validate(
        self,
        path: str | None = None,
        *,
        image_width: float | None = None,
        image_height: float | None = None,
        ignore_dimensions: bool = False,
    ) -> list[ValidationIssue]:
        """Return the missing-boundary validation error."""

        path = "MissingBoundary" if path is None else path
        return [ValidationIssue("error", "MISSING_REGION_BOUNDARY", path, "Region Boundary is mandatory.")]

    def change_unit(
        self,
        unit: BoundaryUnit,
        *,
        image_width: float | int,
        image_height: float | int,
        allow_malformed: bool = False,
    ) -> MissingBoundary:
        """Reject unit conversion when no boundary exists."""

        raise ValueError("Cannot change unit without a Region Boundary.")


@dataclass(frozen=True)
class BoundaryData:
    """Shared raw values used by concrete boundary classes."""

    unit: Any
    allow_malformed: bool = False
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)
    extra: Mapping[str, Any] = field(default_factory=dict, repr=False)
    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple, init=False, repr=False, compare=False)

    @property
    def errors(self) -> list[ValidationIssue]:
        """Return construction-time validation errors."""

        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Return construction-time validation warnings."""

        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def valid(self) -> bool:
        """Return whether construction-time validation found no errors."""

        return not self.errors

    def raw_dict(self) -> Any:
        """Return stored source metadata without using it for validation."""

        return dict(self.raw)

    def _raise_if_invalid_as_dict(self) -> None:
        """Reject public JSON export for invalid geometry."""

        if self.valid:
            return
        first = self.errors[0] if self.errors else self.issues[0]
        raise ValueError(f"{first.path}: {first.message}")

    def _finalize_validation(self, issues: list[ValidationIssue]) -> None:
        """Store construction-time validation state and raise unless malformed input is allowed."""

        object.__setattr__(self, "issues", tuple(issues))
        if self.allow_malformed or not self.errors:
            return
        first = self.errors[0]
        raise ValueError(f"{first.path}: {first.message}")


def frozen_raw_mapping(values: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return an immutable shallow source snapshot."""

    return MappingProxyType(dict(values))


def is_raw_snapshot(values: Any) -> bool:
    """Return whether metadata came from a raw mapping snapshot."""

    return isinstance(values, MappingProxyType)


def number(value: Any) -> float | None:
    """Convert numeric metadata values without accepting booleans as numbers."""

    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def require_number(value: Any, field_name: str) -> float | int:
    """Return a numeric API value or raise a construction error."""

    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{field_name} must be a number.")
    return value


def raw_number(value: Any) -> float | int:
    """Coerce a raw coordinate/dimension into a typed number when possible."""

    if isinstance(value, bool) or value is None:
        return math.nan
    if isinstance(value, (int, float)):
        return value if math.isfinite(float(value)) else math.nan
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return math.nan
        try:
            parsed = int(text) if text.lstrip("+-").isdigit() else float(text)
        except ValueError:
            return math.nan
        return parsed if math.isfinite(float(parsed)) else math.nan
    return math.nan


def raw_field_number(raw: dict[str, Any], key: str) -> float | int | None:
    """Return None for missing raw fields, NaN for present invalid fields, or a parsed number."""

    if key not in raw:
        return None
    return raw_number(raw.get(key))


def json_number(value: Any) -> float | int | None:
    """Return a finite JSON number, or None when it cannot be represented."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(float(value)) else None


def invalid_number(value: Any) -> bool:
    """Return whether a stored numeric field represents a present but invalid raw value."""

    return isinstance(value, float) and math.isnan(value)


def diagnostic_number_value(value: Any, raw: Any, key: str) -> Any:
    """Render invalid raw numeric input as entered instead of as JSON null."""

    if invalid_number(value) and isinstance(raw, Mapping) and key in raw:
        return raw[key]
    return json_number(value)


def require_unit(value: Any) -> BoundaryUnit:
    """Return a valid unit value or raise a construction error."""

    if value not in ALLOWED_UNITS:
        raise ValueError("rbUnit must be one of: pixel, relative.")
    return value


def require_image_dimension(value: Any, field_name: str) -> float | int:
    """Return a positive image dimension or raise a construction error."""

    value = require_number(value, field_name)
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")
    return value


def convert_unit_value(value: float | int, source_unit: Any, target_unit: BoundaryUnit, axis_size: float | int) -> float:
    """Convert one coordinate or size value between pixel and relative units."""

    if source_unit == target_unit:
        return float(value)
    if source_unit == "relative" and target_unit == "pixel":
        return float(value) * float(axis_size)
    if source_unit == "pixel" and target_unit == "relative":
        return float(value) / float(axis_size)
    raise ValueError("Cannot convert value with invalid source or target unit.")


def issue(severity: Severity, code: str, path: str, message: str) -> ValidationIssue:
    """Create a validation issue close to geometry validation code."""

    return ValidationIssue(severity, code, path, message)


def validate_unit(unit: Any, path: str) -> list[ValidationIssue]:
    """Validate a boundary unit value."""

    if unit in ALLOWED_UNITS:
        return []
    return [
        issue(
            "error",
            "INVALID_BOUNDARY_UNIT",
            f"{path}.rbUnit",
            "Boundary Measuring Unit must be one of: pixel, relative.",
        )
    ]


def validate_unknown_fields(raw: dict[str, Any], allowed: AbstractSet[str], path: str) -> list[ValidationIssue]:
    """Reject unrecognized geometry fields."""

    return [
        issue("error", "UNKNOWN_BOUNDARY_FIELD", f"{path}.{key}", f"{key} is not a recognized Region Boundary field.")
        for key in sorted(raw)
        if key not in allowed
    ]


def validate_relative_values(raw: dict[str, Any], keys: AbstractSet[str], path: str) -> list[ValidationIssue]:
    """Validate present relative coordinates and dimensions against 0..1."""

    issues: list[ValidationIssue] = []
    for key in keys:
        value = raw.get(key)
        parsed = number(value)
        if parsed is not None and not 0 <= parsed <= 1:
            issues.append(issue("error", "RELATIVE_OUT_OF_RANGE", f"{path}.{key}", f"{key} must be within 0..1."))
    return issues


def validate_point(
    raw: dict[str, Any], path: str, *, image_width: float | None, image_height: float | None
) -> list[ValidationIssue]:
    """Validate present rbX/rbY values on a boundary or vertex."""

    issues: list[ValidationIssue] = []
    x = number(raw.get("rbX"))
    y = number(raw.get("rbY"))
    if "rbX" in raw and x is None:
        issues.append(issue("error", "INVALID_NUMBER", f"{path}.rbX", "rbX must be a number."))
    if "rbY" in raw and y is None:
        issues.append(issue("error", "INVALID_NUMBER", f"{path}.rbY", "rbY must be a number."))
    if x is not None:
        issues.extend(validate_coordinate(x, f"{path}.rbX", axis_size=image_width, unit=raw.get("rbUnit")))
    if y is not None:
        issues.extend(validate_coordinate(y, f"{path}.rbY", axis_size=image_height, unit=raw.get("rbUnit")))
    return issues


def validate_coordinate(value: float, path: str, *, axis_size: float | None, unit: Any) -> list[ValidationIssue]:
    """Validate one numeric coordinate against unit and optional image size."""

    issues: list[ValidationIssue] = []
    if value < 0:
        issues.append(issue("error", "NEGATIVE_COORDINATE", path, "Coordinates must not be negative."))
    if unit == "relative" and value > 1:
        issues.append(issue("error", "RELATIVE_OUT_OF_RANGE", path, "Relative coordinates must be within 0..1."))
    if unit == "pixel" and axis_size is not None and value > axis_size:
        issues.append(issue("error", "PIXEL_OUT_OF_RANGE", path, f"Pixel coordinate exceeds image size {axis_size:g}."))
    return issues


def validate_size(raw: dict[str, Any], key: str, path: str) -> list[ValidationIssue]:
    """Validate size/radius fields only when the field exists."""

    if key not in raw:
        return []
    parsed = number(raw.get(key))
    if parsed is None:
        return [issue("error", "INVALID_NUMBER", f"{path}.{key}", f"{key} must be a number.")]
    if parsed <= 0:
        return [issue("error", "INVALID_SIZE", f"{path}.{key}", f"{key} must be greater than zero.")]
    return []


def validate_image_dimensions(
    unit: Any,
    path: str,
    *,
    image_width: float | None,
    image_height: float | None,
    ignore_dimensions: bool,
) -> list[ValidationIssue]:
    """Require image dimensions for complete pixel boundary validation."""

    if unit != "pixel" or ignore_dimensions:
        return []

    issues: list[ValidationIssue] = []
    if image_width is None:
        issues.append(
            issue(
                "error",
                "MISSING_IMAGE_DIMENSION",
                f"{path}.imageWidth",
                "image_width is required for pixel boundary validation.",
            )
        )
    if image_height is None:
        issues.append(
            issue(
                "error",
                "MISSING_IMAGE_DIMENSION",
                f"{path}.imageHeight",
                "image_height is required for pixel boundary validation.",
            )
        )
    return issues
