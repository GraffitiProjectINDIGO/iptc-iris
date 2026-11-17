"""Circle Region Boundary geometry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from iptc_iris.models import ValidationIssue
from iptc_iris.spec import CIRCLE_SPEC

from .base import (
    UNSET,
    BoundaryData,
    BoundaryUnit,
    convert_unit_value,
    diagnostic_number_value,
    frozen_raw_mapping,
    invalid_number,
    is_raw_snapshot,
    issue,
    json_number,
    number,
    raw_field_number,
    require_image_dimension,
    require_number,
    require_unit,
    validate_image_dimensions,
    validate_point,
    validate_relative_values,
    validate_unit,
    validate_unknown_fields,
)


@dataclass(frozen=True)
class CircleBoundary(BoundaryData):
    """Typed circle boundary preserving original raw values."""

    unit: BoundaryUnit = "relative"
    x: float | int | None = None
    y: float | int | None = None
    radius: float | int | None = None

    def __post_init__(self) -> None:
        """Validate direct constructor values and store construction issues.

        Raises:
            ValueError: If direct constructor values are invalid and malformed
                geometry is not allowed.
        """

        if not is_raw_snapshot(self.raw):
            object.__setattr__(self, "unit", require_unit(self.unit))
            object.__setattr__(self, "x", require_number(self.x, "rbX"))
            object.__setattr__(self, "y", require_number(self.y, "rbY"))
            object.__setattr__(self, "radius", require_number(self.radius, "rbRx"))
        self._finalize_validation(
            self.validate("regionBoundary", image_width=None, image_height=None, ignore_dimensions=True)
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CircleBoundary:
        """Create a strict circle boundary from canonical metadata.

        Args:
            raw: Canonical circle boundary dictionary.

        Returns:
            A validated circle boundary.

        Raises:
            ValueError: If required fields are missing or invalid.
        """

        return cls(
            unit=require_unit(raw.get("rbUnit")),
            x=require_number(raw.get("rbX"), "rbX"),
            y=require_number(raw.get("rbY"), "rbY"),
            radius=require_number(raw.get("rbRx"), "rbRx"),
            allow_malformed=False,
            extra={key: value for key, value in raw.items() if key not in CIRCLE_SPEC.allowed_keys},
        )

    @classmethod
    def from_raw(cls, raw: dict[str, Any], *, allow_malformed: bool = False) -> CircleBoundary:
        """Create a circle boundary from parsed metadata.

        Args:
            raw: Raw circle boundary dictionary.
            allow_malformed: Preserve invalid values instead of raising during
                construction.

        Returns:
            A circle boundary that keeps raw fields for diagnostics.

        Raises:
            ValueError: If malformed values are present and `allow_malformed`
                is false.
        """

        return cls(
            unit=cast(BoundaryUnit, raw.get("rbUnit")),
            x=raw_field_number(raw, "rbX"),
            y=raw_field_number(raw, "rbY"),
            radius=raw_field_number(raw, "rbRx"),
            allow_malformed=allow_malformed,
            raw=frozen_raw_mapping(raw),
            extra=frozen_raw_mapping({key: value for key, value in raw.items() if key not in CIRCLE_SPEC.allowed_keys}),
        )

    def with_values(
        self,
        *,
        unit: BoundaryUnit | object = UNSET,
        x: float | int | object = UNSET,
        y: float | int | object = UNSET,
        radius: float | int | object = UNSET,
        allow_malformed: bool | None = None,
    ) -> CircleBoundary:
        """Return a copy with changed circle values after validation."""

        next_unit = self.unit if unit is UNSET else require_unit(unit)
        next_x = self.x if x is UNSET else require_number(x, "rbX")
        next_y = self.y if y is UNSET else require_number(y, "rbY")
        next_radius = self.radius if radius is UNSET else require_number(radius, "rbRx")
        return CircleBoundary(
            unit=next_unit,
            x=next_x,
            y=next_y,
            radius=next_radius,
            allow_malformed=self.allow_malformed if allow_malformed is None else allow_malformed,
            raw=self.raw,
            extra=self.extra,
        )

    def with_position(self, *, x: float | int | object = UNSET, y: float | int | object = UNSET) -> CircleBoundary:
        """Return a copy with changed center coordinates."""

        return self.with_values(x=x, y=y)

    def with_radius(self, radius: float | int) -> CircleBoundary:
        """Return a copy with a changed radius."""

        return self.with_values(radius=radius)

    def with_unit(self, unit: BoundaryUnit) -> CircleBoundary:
        """Return a copy with a changed measuring unit."""

        return self.with_values(unit=unit)

    def change_unit(
        self,
        unit: BoundaryUnit,
        *,
        image_width: float | int,
        image_height: float | int,
        allow_malformed: bool = False,
    ) -> CircleBoundary:
        """Return a copy converted to another measuring unit."""

        target_unit = require_unit(unit)
        width_axis = require_image_dimension(image_width, "image_width")
        height_axis = require_image_dimension(image_height, "image_height")
        if target_unit == self.unit:
            return self.with_values(unit=target_unit, allow_malformed=allow_malformed)
        return CircleBoundary(
            unit=target_unit,
            x=convert_unit_value(require_number(self.x, "rbX"), self.unit, target_unit, width_axis),
            y=convert_unit_value(require_number(self.y, "rbY"), self.unit, target_unit, height_axis),
            radius=convert_unit_value(require_number(self.radius, "rbRx"), self.unit, target_unit, width_axis),
            allow_malformed=allow_malformed,
            extra=self.extra,
        )

    def _dict_full(self) -> dict[str, Any]:
        """Return all circle fields, including missing fields as None.

        Returns:
            Complete diagnostic circle dictionary.
        """

        return {
            "rbShape": "circle",
            "rbUnit": self.unit,
            "rbX": json_number(self.x),
            "rbY": json_number(self.y),
            "rbRx": json_number(self.radius),
            **self.extra,
        }

    def _dict_existing(self) -> dict[str, Any]:
        """Return only circle fields that were present or valid extras.

        Returns:
            Circle dictionary suitable for diagnostic rendering.
        """

        data = {"rbShape": "circle", **self.extra}
        if self.unit is not None:
            data["rbUnit"] = self.unit
        if self.x is not None:
            data["rbX"] = diagnostic_number_value(self.x, self.raw, "rbX")
        if self.y is not None:
            data["rbY"] = diagnostic_number_value(self.y, self.raw, "rbY")
        if self.radius is not None:
            data["rbRx"] = diagnostic_number_value(self.radius, self.raw, "rbRx")
        return data

    def as_dict(self) -> dict[str, Any]:
        """Return a canonical circle boundary dictionary.

        Returns:
            JSON-compatible circle boundary.

        Raises:
            ValueError: If the boundary has validation errors.
        """

        self._raise_if_invalid_as_dict()
        data = self._dict_full()
        return {key: value for key, value in data.items() if value is not None}

    def validate(
        self,
        path: str | None = None,
        *,
        image_width: float | None = None,
        image_height: float | None = None,
        ignore_dimensions: bool = False,
    ) -> list[ValidationIssue]:
        """Validate circle fields, shape constraints, and bounds.

        Args:
            path: JSON-style path prefix for validation issues.
            image_width: Optional image width for pixel bounds.
            image_height: Optional image height for pixel bounds.
            ignore_dimensions: Skip missing image-dimension checks.

        Returns:
            Validation issues found on the circle boundary.
        """

        path = "Circle" if path is None else path
        issues: list[ValidationIssue] = []
        data = self._dict_full()
        numeric_data = {key: value for key, value in data.items() if value is not None and not invalid_number(value)}

        issues.extend(validate_unknown_fields(data, CIRCLE_SPEC.allowed_keys | CIRCLE_SPEC.forbidden_keys, path))

        issues.extend(validate_unit(self.unit, path))
        issues.extend(
            validate_image_dimensions(
                self.unit,
                path,
                image_width=image_width,
                image_height=image_height,
                ignore_dimensions=ignore_dimensions,
            )
        )

        if self.unit == "relative":
            issues.extend(
                validate_relative_values(numeric_data, CIRCLE_SPEC.coordinate_keys | CIRCLE_SPEC.size_keys, path)
            )

        issues.extend(self._validate_number_field(self.radius, "rbRx", path, size=True))
        issues.extend(self._validate_number_field(self.x, "rbX", path, size=False))
        issues.extend(self._validate_number_field(self.y, "rbY", path, size=False))

        for key in sorted(CIRCLE_SPEC.forbidden_keys):
            if key in data:
                issues.append(
                    issue(
                        "error",
                        "FORBIDDEN_BOUNDARY_FIELD",
                        f"{path}.{key}",
                        f"{key} must not be used with circle boundaries.",
                    )
                )

        issues.extend(
            validate_point(
                numeric_data,
                path,
                image_width=None if ignore_dimensions else image_width,
                image_height=None if ignore_dimensions else image_height,
            )
        )
        issues.extend(
            self._validate_bounds(
                path,
                image_width=None if ignore_dimensions else image_width,
                image_height=None if ignore_dimensions else image_height,
            )
        )
        return issues

    def _validate_number_field(self, value: Any, key: str, path: str, *, size: bool) -> list[ValidationIssue]:
        """Validate one required circle numeric field.

        Args:
            value: Stored field value.
            key: Canonical boundary field name.
            path: JSON-style path prefix.
            size: Whether the field must be greater than zero.

        Returns:
            Validation issues for this field.
        """

        if value is None:
            return [issue("error", "MISSING_BOUNDARY_FIELD", f"{path}.{key}", f"circle requires {key}.")]
        if invalid_number(value):
            return [issue("error", "INVALID_NUMBER", f"{path}.{key}", f"{key} must be a number.")]
        parsed = number(value)
        if size and parsed is not None and parsed <= 0:
            return [issue("error", "INVALID_SIZE", f"{path}.{key}", f"{key} must be greater than zero.")]
        return []

    def _validate_bounds(
        self, path: str, *, image_width: float | None, image_height: float | None
    ) -> list[ValidationIssue]:
        """Validate that the circle stays within image bounds.

        Args:
            path: JSON-style path prefix.
            image_width: Optional image width for pixel units.
            image_height: Optional image height for pixel units.

        Returns:
            Boundary overflow validation issues.
        """

        issues: list[ValidationIssue] = []
        data = {key: value for key, value in self._dict_full().items() if value is not None and not invalid_number(value)}
        x = number(data.get("rbX"))
        y = number(data.get("rbY"))
        radius = number(data.get("rbRx"))
        if None in {x, y, radius}:
            return issues

        assert x is not None and y is not None and radius is not None

        if self.unit == "relative":
            if x - radius < 0:
                issues.append(
                    issue(
                        "error",
                        "BOUNDARY_EXCEEDS_IMAGE",
                        f"{path}.rbRx",
                        "Relative circle extends before the image left edge.",
                    )
                )
            if x + radius > 1:
                issues.append(
                    issue(
                        "error",
                        "BOUNDARY_EXCEEDS_IMAGE",
                        f"{path}.rbRx",
                        "Relative circle extends past the image right edge.",
                    )
                )
            if y - radius < 0:
                issues.append(
                    issue(
                        "error",
                        "BOUNDARY_EXCEEDS_IMAGE",
                        f"{path}.rbRx",
                        "Relative circle extends before the image top edge.",
                    )
                )
            if y + radius > 1:
                issues.append(
                    issue(
                        "error",
                        "BOUNDARY_EXCEEDS_IMAGE",
                        f"{path}.rbRx",
                        "Relative circle extends past the image bottom edge.",
                    )
                )
        elif self.unit == "pixel":
            if x - radius < 0:
                issues.append(
                    issue(
                        "error",
                        "BOUNDARY_EXCEEDS_IMAGE",
                        f"{path}.rbRx",
                        "Circle extends before the image left edge.",
                    )
                )
            if image_width is not None and x + radius > image_width:
                issues.append(
                    issue(
                        "error",
                        "BOUNDARY_EXCEEDS_IMAGE",
                        f"{path}.rbRx",
                        "Circle extends past the image right edge.",
                    )
                )
            if y - radius < 0:
                issues.append(
                    issue(
                        "error",
                        "BOUNDARY_EXCEEDS_IMAGE",
                        f"{path}.rbRx",
                        "Circle extends before the image top edge.",
                    )
                )
            if image_height is not None and y + radius > image_height:
                issues.append(
                    issue(
                        "error",
                        "BOUNDARY_EXCEEDS_IMAGE",
                        f"{path}.rbRx",
                        "Circle extends past the image bottom edge.",
                    )
                )

        return issues
