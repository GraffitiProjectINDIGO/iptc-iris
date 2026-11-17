"""Shared Region Boundary support for rbCoordinates-backed shapes."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from iptc_iris.models import ValidationIssue
from iptc_iris.spec import BOUNDARY_SHAPE_SPECS

from .base import (
    UNSET,
    BoundaryData,
    BoundaryUnit,
    convert_unit_value,
    frozen_raw_mapping,
    is_raw_snapshot,
    issue,
    number,
    require_image_dimension,
    require_unit,
    validate_image_dimensions,
    validate_unit,
    validate_unknown_fields,
)

CoordinateShape = Literal["point", "multipoint", "linestring", "multilinestring", "multipolygon"]
_MULTIBOUNDARY_SHAPES = {"multipoint", "multilinestring", "multipolygon"}
PART_INDEX_KEY = "rbMbPdPartIndex"
PART_TEXT_KEYS = ("rbMbPdPartId", "rbMbPdPartName", "rbMbPdPartDescription")
PART_DETAIL_KEYS = frozenset({PART_INDEX_KEY, *PART_TEXT_KEYS})


@dataclass(frozen=True)
class MultiboundaryPart:
    """One constituent part of a multipoint, multilinestring, or multipolygon.

    Keeps a part's coordinates together with its documentary details, as the
    IPTC implementation notes recommend. `CoordinateBoundary.with_parts()`
    assigns Part Index values from the order of the parts.

    Attributes:
        coordinates: Part geometry: a point for multipoint, a linestring for
            multilinestring, or a full-polygon-array for multipolygon.
        part_id: Optional Part Id (`rbMbPdPartId`).
        part_name: Optional Part Name (`rbMbPdPartName`).
        part_description: Optional Part Description (`rbMbPdPartDescription`).
    """

    coordinates: Any
    part_id: str | None = None
    part_name: str | None = None
    part_description: str | None = None

    def has_details(self) -> bool:
        """Return whether this part carries any documentary information."""

        return any(value is not None for value in (self.part_id, self.part_name, self.part_description))


@dataclass(frozen=True)
class CoordinateBoundary(BoundaryData):
    """Boundary shape represented by the 2026.1 rbCoordinates property."""

    shape: CoordinateShape = "point"
    unit: BoundaryUnit = "relative"
    coordinates: Any = None
    part_details: Any = None

    def __post_init__(self) -> None:
        """Validate direct constructor values and store construction issues."""

        if not is_raw_snapshot(self.raw):
            object.__setattr__(self, "unit", require_unit(self.unit))
            object.__setattr__(self, "coordinates", _parse_coordinates(self.coordinates))
        self._finalize_validation(
            self.validate("regionBoundary", image_width=None, image_height=None, ignore_dimensions=True)
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CoordinateBoundary:
        """Create a strict coordinate-array boundary from canonical metadata."""

        shape = _shape_from_raw(raw)
        boundary_class = _class_for_shape(shape)
        return boundary_class(
            unit=require_unit(raw.get("rbUnit")),
            coordinates=_parse_coordinates(raw.get("rbCoordinates")),
            part_details=raw.get("rbMbPartDetails"),
            allow_malformed=False,
            extra={key: value for key, value in raw.items() if key not in BOUNDARY_SHAPE_SPECS[shape].allowed_keys},
        )

    @classmethod
    def from_raw(cls, raw: dict[str, Any], *, allow_malformed: bool = False) -> CoordinateBoundary:
        """Create a coordinate-array boundary from parsed metadata."""

        shape = _shape_from_raw(raw)
        boundary_class = _class_for_shape(shape)
        return boundary_class(
            unit=cast(BoundaryUnit, raw.get("rbUnit")),
            coordinates=_parse_coordinates(raw.get("rbCoordinates")),
            part_details=raw.get("rbMbPartDetails"),
            allow_malformed=allow_malformed,
            raw=frozen_raw_mapping(raw),
            extra=frozen_raw_mapping(
                {key: value for key, value in raw.items() if key not in BOUNDARY_SHAPE_SPECS[shape].allowed_keys}
            ),
        )

    def with_values(
        self,
        *,
        unit: BoundaryUnit | object = UNSET,
        coordinates: Any = UNSET,
        part_details: Any = UNSET,
        allow_malformed: bool | None = None,
    ) -> CoordinateBoundary:
        """Return a copy with changed coordinate-boundary values."""

        next_unit = self.unit if unit is UNSET else require_unit(unit)
        next_coordinates = self.coordinates if coordinates is UNSET else _parse_coordinates(coordinates)
        next_part_details = self.part_details if part_details is UNSET else part_details
        return type(self)(
            unit=next_unit,
            coordinates=next_coordinates,
            part_details=next_part_details,
            allow_malformed=self.allow_malformed if allow_malformed is None else allow_malformed,
            raw=self.raw,
            extra=self.extra,
        )

    def with_coordinates(self, coordinates: Any) -> CoordinateBoundary:
        """Return a copy with changed Boundary Coordinates."""

        return self.with_values(coordinates=coordinates)

    def with_unit(self, unit: BoundaryUnit) -> CoordinateBoundary:
        """Return a copy with a changed measuring unit."""

        return self.with_values(unit=unit)

    def change_unit(
        self,
        unit: BoundaryUnit,
        *,
        image_width: float | int,
        image_height: float | int,
        allow_malformed: bool = False,
    ) -> CoordinateBoundary:
        """Return a copy converted to another measuring unit."""

        target_unit = require_unit(unit)
        width_axis = require_image_dimension(image_width, "image_width")
        height_axis = require_image_dimension(image_height, "image_height")
        if target_unit == self.unit:
            return self.with_values(unit=target_unit, allow_malformed=allow_malformed)
        converted = self._convert_coordinates(self.unit, target_unit, width_axis, height_axis)
        return type(self)(
            unit=target_unit,
            coordinates=converted,
            part_details=self.part_details,
            allow_malformed=allow_malformed,
            extra=self.extra,
        )

    def _dict_full(self) -> dict[str, Any]:
        """Return all coordinate boundary fields, including missing fields as None."""

        data = {
            "rbShape": self.shape,
            "rbUnit": self.unit,
            "rbCoordinates": coordinates_to_text(self.coordinates),
            **self.extra,
        }
        if self.part_details is not None:
            data["rbMbPartDetails"] = self.part_details
        return data

    def _dict_existing(self) -> dict[str, Any]:
        """Return only coordinate boundary fields that were present or valid extras."""

        data = {"rbShape": self.shape, **self.extra}
        if self.unit is not None:
            data["rbUnit"] = self.unit
        if self.coordinates is not None:
            raw_coordinates = self.raw.get("rbCoordinates") if isinstance(self.raw, Mapping) else None
            data["rbCoordinates"] = (
                raw_coordinates if isinstance(raw_coordinates, str) else coordinates_to_text(self.coordinates)
            )
        if self.part_details is not None:
            data["rbMbPartDetails"] = self.part_details
        return data

    def as_dict(self) -> dict[str, Any]:
        """Return a canonical coordinate boundary dictionary."""

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
        """Validate coordinate-array fields, shape constraints, and bounds."""

        path = self.shape if path is None else path
        spec = BOUNDARY_SHAPE_SPECS[self.shape]
        data = self._dict_full()
        issues: list[ValidationIssue] = []
        issues.extend(validate_unknown_fields(data, spec.allowed_keys | spec.forbidden_keys, path))
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
        if self.coordinates is None:
            issues.append(
                issue(
                    "error",
                    "MISSING_BOUNDARY_FIELD",
                    f"{path}.rbCoordinates",
                    f"{self.shape} requires rbCoordinates.",
                )
            )
        else:
            issues.extend(
                self._validate_coordinates(
                    f"{path}.rbCoordinates",
                    unit=self.unit,
                    image_width=None if ignore_dimensions else image_width,
                    image_height=None if ignore_dimensions else image_height,
                )
            )

        for key in sorted(spec.forbidden_keys):
            if key in data:
                issues.append(
                    issue(
                        "error",
                        "FORBIDDEN_BOUNDARY_FIELD",
                        f"{path}.{key}",
                        f"{key} must not be used with {self.shape} boundaries.",
                    )
                )

        if self.part_details is not None and self.shape not in _MULTIBOUNDARY_SHAPES:
            issues.append(
                issue(
                    "error",
                    "FORBIDDEN_BOUNDARY_FIELD",
                    f"{path}.rbMbPartDetails",
                    f"rbMbPartDetails must not be used with {self.shape} boundaries.",
                )
            )
        elif self.part_details is not None:
            issues.extend(validate_part_details(self.part_details, self.coordinates, f"{path}.rbMbPartDetails"))
        return issues

    def parts(self) -> list[MultiboundaryPart]:
        """Return the constituent parts with their associated part details.

        Part details are matched to parts by Part Index. Entries with a
        missing, invalid, duplicate, or out-of-range index are not associated;
        use `validate()` to report them.

        Raises:
            ValueError: If the shape is not multipoint, multilinestring, or
                multipolygon, or the coordinates are not an array.
        """

        if self.shape not in _MULTIBOUNDARY_SHAPES:
            raise ValueError(f"{self.shape} boundaries have no Multiboundary Part Details.")
        return split_multiboundary_parts(self.coordinates, self.part_details)

    def with_parts(self, parts: Sequence[MultiboundaryPart]) -> CoordinateBoundary:
        """Return a copy built from parts, renumbering every Part Index.

        Coordinates are written in the order of `parts`, and each Part Index is
        set to the part's zero-based position. Parts without documentary
        details get no details entry. Use this after inserting, removing, or
        reordering parts so the Part Index values stay correct.

        Raises:
            ValueError: If the shape is not multipoint, multilinestring, or
                multipolygon.
        """

        if self.shape not in _MULTIBOUNDARY_SHAPES:
            raise ValueError(f"{self.shape} boundaries have no Multiboundary Part Details.")
        coordinates, details = join_multiboundary_parts(parts)
        return self.with_values(coordinates=coordinates, part_details=details)

    def _validate_coordinates(
        self,
        path: str,
        *,
        unit: Any,
        image_width: float | None,
        image_height: float | None,
    ) -> list[ValidationIssue]:
        """Validate the parsed rbCoordinates shape payload."""

        return [
            issue(
                "error",
                "INVALID_BOUNDARY_COORDINATES",
                path,
                f"{self.shape} rbCoordinates validation is not implemented.",
            )
        ]

    def _convert_coordinates(
        self,
        source_unit: BoundaryUnit,
        target_unit: BoundaryUnit,
        image_width: float | int,
        image_height: float | int,
    ) -> Any:
        """Convert parsed rbCoordinates to another measuring unit."""

        raise ValueError(f"Cannot convert {self.shape} Boundary Coordinates.")


def split_multiboundary_parts(coordinates: Any, part_details: Any) -> list[MultiboundaryPart]:
    """Pair each top-level Boundary Coordinates entry with its Multiboundary Part Details.

    Details are matched by Part Index. Entries with a missing, invalid,
    duplicate, or out-of-range index are not associated; validation reports
    them. Works on plain canonical data, so applications that keep regions as
    JSON can couple parts while editing them.

    Args:
        coordinates: Parsed `rbCoordinates` of a multipoint, multilinestring,
            or multipolygon, or its JSON string.
        part_details: The `rbMbPartDetails` value, or None.

    Raises:
        ValueError: If the coordinates are not an array.
    """

    coordinates = _parse_coordinates(coordinates)
    if not isinstance(coordinates, list):
        raise ValueError("rbCoordinates must be an array of parts.")
    details_by_index: dict[int, Mapping[str, Any]] = {}
    if isinstance(part_details, list):
        for detail in part_details:
            if not isinstance(detail, Mapping):
                continue
            index = part_index_value(detail.get(PART_INDEX_KEY))
            if index is not None and index < len(coordinates) and index not in details_by_index:
                details_by_index[index] = detail
    parts: list[MultiboundaryPart] = []
    for index, part_coordinates in enumerate(coordinates):
        detail = details_by_index.get(index, {})
        parts.append(
            MultiboundaryPart(
                coordinates=part_coordinates,
                part_id=detail.get("rbMbPdPartId"),
                part_name=detail.get("rbMbPdPartName"),
                part_description=detail.get("rbMbPdPartDescription"),
            )
        )
    return parts


def join_multiboundary_parts(parts: Sequence[MultiboundaryPart]) -> tuple[list[Any], list[dict[str, Any]] | None]:
    """Return Boundary Coordinates and Multiboundary Part Details for ordered parts.

    Each Part Index is the part's zero-based position in `parts`, as the IPTC
    implementation notes recommend for writing. Parts without documentary
    details get no details entry.

    Returns:
        The coordinate array and the part details list, or None when no part
        has details.
    """

    coordinates: list[Any] = []
    details: list[dict[str, Any]] = []
    for part in parts:
        coordinates.append(part.coordinates)
        if not part.has_details():
            continue
        detail: dict[str, Any] = {PART_INDEX_KEY: len(coordinates) - 1}
        values = (part.part_id, part.part_name, part.part_description)
        for key, value in zip(PART_TEXT_KEYS, values, strict=True):
            if value is not None:
                detail[key] = value
        details.append(detail)
    return coordinates, details or None


def coordinate_point_key(point: Any) -> tuple[float, float] | None:
    """Return a comparable (x, y) tuple for a valid [x, y] pair, else None."""

    if not isinstance(point, list) or len(point) != 2:
        return None
    x = number(point[0])
    y = number(point[1])
    if x is None or y is None:
        return None
    return (x, y)


def part_index_value(value: Any) -> int | None:
    """Return a Part Index as a non-negative integer, or None when invalid."""

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def validate_part_details(details: Any, coordinates: Any, path: str) -> list[ValidationIssue]:
    """Validate Multiboundary Part Details against the parsed Boundary Coordinates."""

    if not isinstance(details, list):
        return [
            issue(
                "error",
                "INVALID_PART_DETAILS",
                path,
                "rbMbPartDetails must be an array of Multiboundary Part Details structures.",
            )
        ]

    part_count = len(coordinates) if isinstance(coordinates, list) else None
    first_use: dict[int, int] = {}
    issues: list[ValidationIssue] = []
    for position, detail in enumerate(details):
        detail_path = f"{path}[{position}]"
        if not isinstance(detail, Mapping):
            issues.append(
                issue("error", "INVALID_PART_DETAILS", detail_path, "Multiboundary Part Details entry must be an object.")
            )
            continue
        for key in sorted(str(key) for key in detail):
            if key not in PART_DETAIL_KEYS:
                issues.append(
                    issue(
                        "error",
                        "UNKNOWN_PART_DETAIL_FIELD",
                        f"{detail_path}.{key}",
                        f"{key} is not a recognized Multiboundary Part Details field.",
                    )
                )
        for key in PART_TEXT_KEYS:
            if key in detail and not isinstance(detail[key], str):
                issues.append(
                    issue("error", "INVALID_PART_DETAIL_VALUE", f"{detail_path}.{key}", f"{key} must be a string.")
                )

        index_path = f"{detail_path}.{PART_INDEX_KEY}"
        if PART_INDEX_KEY not in detail:
            issues.append(
                issue(
                    "error",
                    "MISSING_PART_INDEX",
                    index_path,
                    "Each Multiboundary Part Details entry must contain rbMbPdPartIndex.",
                )
            )
            continue
        index = part_index_value(detail[PART_INDEX_KEY])
        if index is None:
            issues.append(
                issue("error", "INVALID_PART_INDEX", index_path, "rbMbPdPartIndex must be a non-negative integer.")
            )
            continue
        if part_count is not None and index >= part_count:
            issues.append(
                issue(
                    "error",
                    "PART_INDEX_OUT_OF_RANGE",
                    index_path,
                    f"rbMbPdPartIndex {index} does not identify a part; rbCoordinates has {part_count} part(s).",
                )
            )
        if index in first_use:
            issues.append(
                issue(
                    "error",
                    "DUPLICATE_PART_INDEX",
                    index_path,
                    f"rbMbPdPartIndex {index} is already used by {path}[{first_use[index]}].",
                )
            )
        else:
            first_use[index] = position
    return issues


def parse_coordinates_value(value: Any) -> Any:
    """Return a parsed rbCoordinates value."""

    return _parse_coordinates(value)


def coordinates_to_text(value: Any) -> str | None:
    """Serialize parsed Boundary Coordinates to the IPTC JSON string value."""

    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return None


def validate_coordinate_point(
    point: Any,
    path: str,
    *,
    unit: Any,
    image_width: float | None,
    image_height: float | None,
) -> list[ValidationIssue]:
    """Validate one [x, y] coordinate pair."""

    if not isinstance(point, list) or len(point) != 2:
        return [issue("error", "INVALID_BOUNDARY_COORDINATES", path, "Boundary Coordinates point must be [x, y].")]
    issues: list[ValidationIssue] = []
    for index, key, axis_size in ((0, "x", image_width), (1, "y", image_height)):
        value = point[index]
        parsed = number(value)
        value_path = f"{path}[{index}]"
        if parsed is None:
            issues.append(
                issue("error", "INVALID_NUMBER", value_path, f"Boundary Coordinates {key} value must be a number.")
            )
            continue
        if parsed < 0:
            issues.append(issue("error", "NEGATIVE_COORDINATE", value_path, "Coordinates must not be negative."))
        if unit == "relative" and parsed > 1:
            issues.append(
                issue("error", "RELATIVE_OUT_OF_RANGE", value_path, "Relative coordinates must be within 0..1.")
            )
        if unit == "pixel" and axis_size is not None and parsed > axis_size:
            issues.append(
                issue("error", "PIXEL_OUT_OF_RANGE", value_path, f"Pixel coordinate exceeds image size {axis_size:g}.")
            )
    return issues


def _shape_from_raw(raw: Mapping[str, Any]) -> CoordinateShape:
    """Return the coordinate-array shape from raw boundary data."""

    shape = raw.get("rbShape")
    if shape not in {"point", "multipoint", "linestring", "multilinestring", "multipolygon"}:
        raise ValueError("rbShape must be one of: point, multipoint, linestring, multilinestring, multipolygon.")
    return cast(CoordinateShape, shape)


def _class_for_shape(shape: CoordinateShape) -> type[CoordinateBoundary]:
    """Return the concrete coordinate boundary class for a shape name."""

    from .linestring import LineStringBoundary
    from .multilinestring import MultiLineStringBoundary
    from .multipoint import MultiPointBoundary
    from .multipolygon import MultiPolygonBoundary
    from .point import PointBoundary

    return {
        "point": PointBoundary,
        "multipoint": MultiPointBoundary,
        "linestring": LineStringBoundary,
        "multilinestring": MultiLineStringBoundary,
        "multipolygon": MultiPolygonBoundary,
    }[shape]


def _parse_coordinates(value: Any) -> Any:
    """Parse the serialized rbCoordinates JSON value when needed."""

    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def convert_coordinate_point(
    point: Any,
    source_unit: BoundaryUnit,
    target_unit: BoundaryUnit,
    image_width: float | int,
    image_height: float | int,
) -> list[float]:
    """Convert one [x, y] point."""

    if not isinstance(point, list) or len(point) != 2:
        raise ValueError("Boundary Coordinates point must be [x, y].")
    x = number(point[0])
    y = number(point[1])
    if x is None or y is None:
        raise ValueError("Boundary Coordinates values must be numbers.")
    return [
        convert_unit_value(x, source_unit, target_unit, image_width),
        convert_unit_value(y, source_unit, target_unit, image_height),
    ]
