"""Rectangle Region Boundary geometry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from iptc_iris.models import ValidationIssue
from iptc_iris.spec import RECTANGLE_SPEC

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
class RectangleBoundary(BoundaryData):
    """Typed rectangle boundary preserving original raw values."""

    unit: BoundaryUnit = "relative"
    x: float | int | None = None
    y: float | int | None = None
    width: float | int | None = None
    height: float | int | None = None

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
            object.__setattr__(self, "width", require_number(self.width, "rbW"))
            object.__setattr__(self, "height", require_number(self.height, "rbH"))
        self._finalize_validation(
            self.validate("regionBoundary", image_width=None, image_height=None, ignore_dimensions=True)
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> RectangleBoundary:
        """Create a strict rectangle boundary from canonical metadata.

        Args:
            raw: Canonical rectangle boundary dictionary.

        Returns:
            A validated rectangle boundary.

        Raises:
            ValueError: If required fields are missing or invalid.
        """

        return cls(
            unit=require_unit(raw.get("rbUnit")),
            x=require_number(raw.get("rbX"), "rbX"),
            y=require_number(raw.get("rbY"), "rbY"),
            width=require_number(raw.get("rbW"), "rbW"),
            height=require_number(raw.get("rbH"), "rbH"),
            allow_malformed=False,
            extra={key: value for key, value in raw.items() if key not in RECTANGLE_SPEC.allowed_keys},
        )

    @classmethod
    def from_raw(cls, raw: dict[str, Any], *, allow_malformed: bool = False) -> RectangleBoundary:
        """Create a rectangle boundary from parsed metadata.

        Args:
            raw: Raw rectangle boundary dictionary.
            allow_malformed: Preserve invalid values instead of raising during
                construction.

        Returns:
            A rectangle boundary that keeps raw fields for diagnostics.

        Raises:
            ValueError: If malformed values are present and `allow_malformed`
                is false.
        """

        return cls(
            unit=cast(BoundaryUnit, raw.get("rbUnit")),
            x=raw_field_number(raw, "rbX"),
            y=raw_field_number(raw, "rbY"),
            width=raw_field_number(raw, "rbW"),
            height=raw_field_number(raw, "rbH"),
            allow_malformed=allow_malformed,
            raw=frozen_raw_mapping(raw),
            extra=frozen_raw_mapping(
                {key: value for key, value in raw.items() if key not in RECTANGLE_SPEC.allowed_keys}
            ),
        )

    def with_values(
        self,
        *,
        unit: BoundaryUnit | object = UNSET,
        x: float | int | object = UNSET,
        y: float | int | object = UNSET,
        width: float | int | object = UNSET,
        height: float | int | object = UNSET,
        allow_malformed: bool | None = None,
    ) -> RectangleBoundary:
        """Return a copy with changed rectangle values after validation."""

        next_unit = self.unit if unit is UNSET else require_unit(unit)
        next_x = self.x if x is UNSET else require_number(x, "rbX")
        next_y = self.y if y is UNSET else require_number(y, "rbY")
        next_width = self.width if width is UNSET else require_number(width, "rbW")
        next_height = self.height if height is UNSET else require_number(height, "rbH")
        return RectangleBoundary(
            unit=next_unit,
            x=next_x,
            y=next_y,
            width=next_width,
            height=next_height,
            allow_malformed=self.allow_malformed if allow_malformed is None else allow_malformed,
            raw=self.raw,
            extra=self.extra,
        )

    def with_position(self, *, x: float | int | object = UNSET, y: float | int | object = UNSET) -> RectangleBoundary:
        """Return a copy with changed top-left coordinates."""

        return self.with_values(x=x, y=y)

    def with_size(
        self, *, width: float | int | object = UNSET, height: float | int | object = UNSET
    ) -> RectangleBoundary:
        """Return a copy with changed width and/or height."""

        return self.with_values(width=width, height=height)

    def with_width(self, width: float | int) -> RectangleBoundary:
        """Return a copy with a changed width."""

        return self.with_values(width=width)

    def with_height(self, height: float | int) -> RectangleBoundary:
        """Return a copy with a changed height."""

        return self.with_values(height=height)

    def with_unit(self, unit: BoundaryUnit) -> RectangleBoundary:
        """Return a copy with a changed measuring unit."""

        return self.with_values(unit=unit)

    def change_unit(
        self,
        unit: BoundaryUnit,
        *,
        image_width: float | int,
        image_height: float | int,
        allow_malformed: bool = False,
    ) -> RectangleBoundary:
        """Return a copy converted to another measuring unit."""

        target_unit = require_unit(unit)
        width_axis = require_image_dimension(image_width, "image_width")
        height_axis = require_image_dimension(image_height, "image_height")
        if target_unit == self.unit:
            return self.with_values(unit=target_unit, allow_malformed=allow_malformed)
        return RectangleBoundary(
            unit=target_unit,
            x=convert_unit_value(require_number(self.x, "rbX"), self.unit, target_unit, width_axis),
            y=convert_unit_value(require_number(self.y, "rbY"), self.unit, target_unit, height_axis),
            width=convert_unit_value(require_number(self.width, "rbW"), self.unit, target_unit, width_axis),
            height=convert_unit_value(require_number(self.height, "rbH"), self.unit, target_unit, height_axis),
            allow_malformed=allow_malformed,
            extra=self.extra,
        )

    def _dict_full(self) -> dict[str, Any]:
        """Return all rectangle fields, including missing fields as None.

        Returns:
            Complete diagnostic rectangle dictionary.
        """

        return {
            "rbShape": "rectangle",
            "rbUnit": self.unit,
            "rbX": json_number(self.x),
            "rbY": json_number(self.y),
            "rbW": json_number(self.width),
            "rbH": json_number(self.height),
            **self.extra,
        }

    def _dict_existing(self) -> dict[str, Any]:
        """Return only rectangle fields that were present or valid extras.

        Returns:
            Rectangle dictionary suitable for diagnostic rendering.
        """

        data = {"rbShape": "rectangle", **self.extra}
        if self.unit is not None:
            data["rbUnit"] = self.unit
        if self.x is not None:
            data["rbX"] = diagnostic_number_value(self.x, self.raw, "rbX")
        if self.y is not None:
            data["rbY"] = diagnostic_number_value(self.y, self.raw, "rbY")
        if self.width is not None:
            data["rbW"] = diagnostic_number_value(self.width, self.raw, "rbW")
        if self.height is not None:
            data["rbH"] = diagnostic_number_value(self.height, self.raw, "rbH")
        return data

    def as_dict(self) -> dict[str, Any]:
        """Return a canonical rectangle boundary dictionary.

        Returns:
            JSON-compatible rectangle boundary.

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
        """Validate rectangle fields, shape constraints, and bounds.

        Args:
            path: JSON-style path prefix for validation issues.
            image_width: Optional image width for pixel bounds.
            image_height: Optional image height for pixel bounds.
            ignore_dimensions: Skip missing image-dimension checks.

        Returns:
            Validation issues found on the rectangle boundary.
        """

        path = "Rectangle" if path is None else path
        issues: list[ValidationIssue] = []
        data = self._dict_full()
        numeric_data = {key: value for key, value in data.items() if value is not None and not invalid_number(value)}
        issues.extend(validate_unknown_fields(data, RECTANGLE_SPEC.allowed_keys | RECTANGLE_SPEC.forbidden_keys, path))
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
                validate_relative_values(numeric_data, RECTANGLE_SPEC.coordinate_keys | RECTANGLE_SPEC.size_keys, path)
            )

        issues.extend(self._validate_number_field(self.height, "rbH", path, size=True))
        issues.extend(self._validate_number_field(self.width, "rbW", path, size=True))
        issues.extend(self._validate_number_field(self.x, "rbX", path, size=False))
        issues.extend(self._validate_number_field(self.y, "rbY", path, size=False))

        for key in sorted(RECTANGLE_SPEC.forbidden_keys):
            if key in data:
                issues.append(
                    issue(
                        "error",
                        "FORBIDDEN_BOUNDARY_FIELD",
                        f"{path}.{key}",
                        f"{key} must not be used with rectangle boundaries.",
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
        """Validate one required rectangle numeric field.

        Args:
            value: Stored field value.
            key: Canonical boundary field name.
            path: JSON-style path prefix.
            size: Whether the field must be greater than zero.

        Returns:
            Validation issues for this field.
        """

        if value is None:
            return [issue("error", "MISSING_BOUNDARY_FIELD", f"{path}.{key}", f"rectangle requires {key}.")]
        if invalid_number(value):
            return [issue("error", "INVALID_NUMBER", f"{path}.{key}", f"{key} must be a number.")]
        parsed = number(value)
        if size and parsed is not None and parsed <= 0:
            return [issue("error", "INVALID_SIZE", f"{path}.{key}", f"{key} must be greater than zero.")]
        return []

    def _validate_bounds(
        self, path: str, *, image_width: float | None, image_height: float | None
    ) -> list[ValidationIssue]:
        """Validate that the rectangle stays within image bounds.

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
        width = number(data.get("rbW"))
        height = number(data.get("rbH"))
        if None in {x, y, width, height}:
            return issues

        assert x is not None and y is not None and width is not None and height is not None

        if self.unit == "relative":
            if x + width > 1:
                issues.append(
                    issue("error", "BOUNDARY_EXCEEDS_IMAGE", f"{path}.rbW", "Relative rectangle exceeds image width.")
                )
            if y + height > 1:
                issues.append(
                    issue("error", "BOUNDARY_EXCEEDS_IMAGE", f"{path}.rbH", "Relative rectangle exceeds image height.")
                )
        elif self.unit == "pixel":
            if image_width is not None and x + width > image_width:
                issues.append(issue("error", "BOUNDARY_EXCEEDS_IMAGE", f"{path}.rbW", "Rectangle exceeds image width."))
            if image_height is not None and y + height > image_height:
                issues.append(issue("error", "BOUNDARY_EXCEEDS_IMAGE", f"{path}.rbH", "Rectangle exceeds image height."))

        return issues
