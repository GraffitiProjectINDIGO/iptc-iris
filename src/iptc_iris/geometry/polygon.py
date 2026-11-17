"""Polygon Region Boundary geometry."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from iptc_iris.models import ValidationIssue
from iptc_iris.spec import POLYGON_SPEC, VERTEX_KEYS

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
from .coordinate import (
    convert_coordinate_point,
    coordinates_to_text,
    parse_coordinates_value,
    validate_coordinate_point,
)

# Tolerance of the geometric predicates below (orientation, on-segment, same point).
_EPSILON = 1e-12


@dataclass(frozen=True)
class Vertex:
    """One polygon vertex preserving original raw values."""

    x: float | int | None = None
    y: float | int | None = None
    allow_malformed: bool = False
    raw: Any = field(default=None, repr=False)
    extra: Mapping[str, Any] = field(default_factory=dict, repr=False)
    source_is_object: bool = field(default=True, repr=False)
    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate direct constructor values and store construction issues.

        Raises:
            ValueError: If direct constructor values are invalid and malformed
                vertices are not allowed.
        """

        if self.raw is None and self.source_is_object:
            object.__setattr__(self, "x", require_number(self.x, "rbX"))
            object.__setattr__(self, "y", require_number(self.y, "rbY"))
        # A vertex does not know whether its parent polygon uses relative or
        # pixel units, so construction validates structure and non-negativity
        # only. Unit-specific range checks happen in PolygonBoundary.validate().
        self._finalize_validation(
            self.validate("vertex", unit="pixel", image_width=None, image_height=None, ignore_dimensions=True)
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Vertex:
        """Create a strict polygon vertex from canonical metadata.

        Args:
            raw: Canonical vertex dictionary.

        Returns:
            A validated polygon vertex.

        Raises:
            ValueError: If required coordinates are missing or invalid.
        """

        return cls(
            x=require_number(raw.get("rbX"), "rbX"),
            y=require_number(raw.get("rbY"), "rbY"),
            allow_malformed=False,
            extra={key: value for key, value in raw.items() if key not in VERTEX_KEYS},
        )

    @classmethod
    def from_raw(cls, raw: Any, *, allow_malformed: bool = False) -> Vertex:
        """Create a polygon vertex from parsed metadata.

        Args:
            raw: Raw vertex value.
            allow_malformed: Preserve invalid values instead of raising during
                construction.

        Returns:
            A vertex object that keeps raw fields for diagnostics.

        Raises:
            ValueError: If malformed values are present and `allow_malformed`
                is false.
        """

        if not isinstance(raw, dict):
            return cls(
                x=0,
                y=0,
                allow_malformed=allow_malformed,
                raw=raw,
                source_is_object=False,
            )
        return cls(
            x=raw_field_number(raw, "rbX"),
            y=raw_field_number(raw, "rbY"),
            allow_malformed=allow_malformed,
            raw=frozen_raw_mapping(raw),
            extra=frozen_raw_mapping({key: value for key, value in raw.items() if key not in VERTEX_KEYS}),
        )

    def with_values(
        self,
        *,
        x: float | int | object = UNSET,
        y: float | int | object = UNSET,
        allow_malformed: bool | None = None,
    ) -> Vertex:
        """Return a copy with changed vertex coordinates after validation."""

        next_x = self.x if x is UNSET else require_number(x, "rbX")
        next_y = self.y if y is UNSET else require_number(y, "rbY")
        return Vertex(
            x=next_x,
            y=next_y,
            allow_malformed=self.allow_malformed if allow_malformed is None else allow_malformed,
            raw=self.raw,
            extra=self.extra,
        )

    def with_position(self, *, x: float | int | object = UNSET, y: float | int | object = UNSET) -> Vertex:
        """Return a copy with changed vertex coordinates."""

        return self.with_values(x=x, y=y)

    def change_unit(
        self,
        source_unit: BoundaryUnit,
        target_unit: BoundaryUnit,
        *,
        image_width: float | int,
        image_height: float | int,
        allow_malformed: bool = False,
    ) -> Vertex:
        """Return a copy with coordinates converted to another measuring unit."""

        source = require_unit(source_unit)
        target = require_unit(target_unit)
        width_axis = require_image_dimension(image_width, "image_width")
        height_axis = require_image_dimension(image_height, "image_height")
        if source == target:
            return self.with_values(allow_malformed=allow_malformed)
        return Vertex(
            x=convert_unit_value(require_number(self.x, "rbX"), source, target, width_axis),
            y=convert_unit_value(require_number(self.y, "rbY"), source, target, height_axis),
            allow_malformed=allow_malformed,
            extra=self.extra,
        )

    def _dict_full(self) -> dict[str, Any]:
        """Return all vertex fields, including missing fields as None.

        Returns:
            Complete diagnostic vertex dictionary.
        """

        return {"rbX": json_number(self.x), "rbY": json_number(self.y), **self.extra}

    def _dict_existing(self) -> dict[str, Any]:
        """Return only vertex fields that were present or valid extras.

        Returns:
            Vertex dictionary suitable for diagnostic rendering.
        """

        data = dict(self.extra)
        if self.x is not None:
            data["rbX"] = diagnostic_number_value(self.x, self.raw, "rbX")
        if self.y is not None:
            data["rbY"] = diagnostic_number_value(self.y, self.raw, "rbY")
        return data

    def as_dict(self) -> Any:
        """Return a canonical vertex dictionary.

        Returns:
            JSON-compatible vertex dictionary.

        Raises:
            ValueError: If the vertex has validation errors.
        """

        if not self.valid:
            first = self.errors[0] if self.errors else self.issues[0]
            raise ValueError(f"{first.path}: {first.message}")
        data = self._dict_full()
        return {key: value for key, value in data.items() if value is not None}

    def raw_dict(self) -> Any:
        """Return the raw vertex value captured during parsing.

        Returns:
            Raw mapping or scalar vertex value.
        """

        return dict(self.raw) if isinstance(self.raw, Mapping) else self.raw

    def validate(
        self,
        path: str | None = None,
        *,
        unit: Any = "relative",
        image_width: float | None = None,
        image_height: float | None = None,
        ignore_dimensions: bool = False,
    ) -> list[ValidationIssue]:
        """Validate vertex coordinates and optional bounds.

        Args:
            path: JSON-style path prefix for validation issues.
            unit: Boundary unit inherited from the polygon.
            image_width: Optional image width for pixel bounds.
            image_height: Optional image height for pixel bounds.
            ignore_dimensions: Skip image-dimension checks.

        Returns:
            Validation issues found on the vertex.
        """

        path = "Vertex" if path is None else path
        issues: list[ValidationIssue] = []
        if not self.source_is_object:
            return [issue("error", "VERTEX_NOT_OBJECT", path, "Polygon vertex must be an object.")]
        data = self._dict_full()
        numeric_data = {key: value for key, value in data.items() if value is not None and not invalid_number(value)}

        for key in sorted(data):
            if key not in VERTEX_KEYS:
                issues.append(
                    issue(
                        "error",
                        "UNKNOWN_VERTEX_FIELD",
                        f"{path}.{key}",
                        f"{key} is not a recognized polygon vertex field.",
                    )
                )
        for key in ("rbX", "rbY"):
            value = self.x if key == "rbX" else self.y
            if value is None:
                issues.append(issue("error", "MISSING_VERTEX_COORDINATE", f"{path}.{key}", f"Vertex requires {key}."))
            elif invalid_number(value):
                issues.append(issue("error", "INVALID_NUMBER", f"{path}.{key}", f"{key} must be a number."))

        vertex_raw = {**numeric_data, "rbUnit": unit}
        issues.extend(
            validate_point(
                vertex_raw,
                path,
                image_width=None if ignore_dimensions else image_width,
                image_height=None if ignore_dimensions else image_height,
            )
        )
        return issues

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

    def _finalize_validation(self, issues: list[ValidationIssue]) -> None:
        """Store construction issues and optionally raise the first error.

        Args:
            issues: Issues collected during construction.

        Raises:
            ValueError: If issues exist and malformed vertices are not allowed.
        """

        object.__setattr__(self, "issues", tuple(issues))
        if self.allow_malformed or not issues:
            return
        first = issues[0]
        raise ValueError(f"{first.path}: {first.message}")


@dataclass(frozen=True)
class PolygonBoundary(BoundaryData):
    """Typed polygon boundary preserving original raw values."""

    unit: BoundaryUnit = "relative"
    vertices: list[Vertex] | Any = None
    coordinates: Any = None

    def __post_init__(self) -> None:
        """Validate direct constructor values and store construction issues.

        Raises:
            ValueError: If direct constructor values are invalid and malformed
                geometry is not allowed.
        """

        if not is_raw_snapshot(self.raw):
            object.__setattr__(self, "unit", require_unit(self.unit))
            if self.coordinates is not None:
                object.__setattr__(self, "coordinates", parse_coordinates_value(self.coordinates))
        self._finalize_validation(
            self.validate("regionBoundary", image_width=None, image_height=None, ignore_dimensions=True)
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PolygonBoundary:
        """Create a strict polygon boundary from canonical metadata.

        Args:
            raw: Canonical polygon boundary dictionary.

        Returns:
            A validated polygon boundary.

        Raises:
            ValueError: If required fields are missing or invalid.
        """

        vertices = raw.get("rbVertices")
        coordinates = raw.get("rbCoordinates")
        if not isinstance(vertices, list):
            if "rbVertices" in raw:
                raise ValueError("rbVertices must be a list.")
            if coordinates is None:
                raise ValueError("polygon requires rbVertices or rbCoordinates.")
            vertices = None
        if vertices is not None and coordinates is not None:
            raise ValueError("polygon must not use rbVertices and rbCoordinates together.")
        if coordinates is not None:
            coordinates = parse_coordinates_value(coordinates)
        return cls(
            unit=require_unit(raw.get("rbUnit")),
            vertices=[Vertex.from_dict(vertex) for vertex in vertices] if vertices is not None else None,
            coordinates=coordinates,
            allow_malformed=False,
            extra={key: value for key, value in raw.items() if key not in POLYGON_SPEC.allowed_keys},
        )

    @classmethod
    def from_raw(cls, raw: dict[str, Any], *, allow_malformed: bool = False) -> PolygonBoundary:
        """Create a polygon boundary from parsed metadata.

        Args:
            raw: Raw polygon boundary dictionary.
            allow_malformed: Preserve invalid values instead of raising during
                construction.

        Returns:
            A polygon boundary that keeps raw fields for diagnostics.

        Raises:
            ValueError: If malformed values are present and `allow_malformed`
                is false.
        """

        vertices = raw.get("rbVertices")
        parsed_vertices = (
            [Vertex.from_raw(vertex, allow_malformed=allow_malformed) for vertex in vertices]
            if isinstance(vertices, list)
            else vertices
        )
        coordinates = raw.get("rbCoordinates")
        if coordinates is not None:
            coordinates = parse_coordinates_value(coordinates)
        return cls(
            unit=cast(BoundaryUnit, raw.get("rbUnit")),
            vertices=parsed_vertices,
            coordinates=coordinates,
            allow_malformed=allow_malformed,
            raw=frozen_raw_mapping(raw),
            extra=frozen_raw_mapping({key: value for key, value in raw.items() if key not in POLYGON_SPEC.allowed_keys}),
        )

    def with_values(
        self,
        *,
        unit: BoundaryUnit | object = UNSET,
        vertices: list[Vertex] | object = UNSET,
        coordinates: Any = UNSET,
        allow_malformed: bool | None = None,
    ) -> PolygonBoundary:
        """Return a copy with changed polygon values after validation."""

        next_unit = self.unit if unit is UNSET else require_unit(unit)
        next_vertices = self.vertices if vertices is UNSET else vertices
        next_coordinates = self.coordinates if coordinates is UNSET else coordinates
        if next_coordinates is not None:
            next_coordinates = parse_coordinates_value(next_coordinates)
        return PolygonBoundary(
            unit=next_unit,
            vertices=next_vertices,
            coordinates=next_coordinates,
            allow_malformed=self.allow_malformed if allow_malformed is None else allow_malformed,
            raw=self.raw,
            extra=self.extra,
        )

    def with_vertices(self, vertices: list[Vertex]) -> PolygonBoundary:
        """Return a copy with changed polygon vertices."""

        return self.with_values(vertices=vertices, coordinates=None)

    def with_coordinates(self, coordinates: Any) -> PolygonBoundary:
        """Return a copy with changed Boundary Coordinates."""

        return self.with_values(vertices=None, coordinates=coordinates)

    def with_unit(self, unit: BoundaryUnit) -> PolygonBoundary:
        """Return a copy with a changed measuring unit."""

        return self.with_values(unit=unit)

    def change_unit(
        self,
        unit: BoundaryUnit,
        *,
        image_width: float | int,
        image_height: float | int,
        allow_malformed: bool = False,
    ) -> PolygonBoundary:
        """Return a copy converted to another measuring unit."""

        target_unit = require_unit(unit)
        require_image_dimension(image_width, "image_width")
        require_image_dimension(image_height, "image_height")
        if self.coordinates is not None:
            if target_unit == self.unit:
                return self.with_values(unit=target_unit, allow_malformed=allow_malformed)

            return PolygonBoundary(
                unit=target_unit,
                coordinates=convert_polygon_coordinates(
                    self.coordinates,
                    self.unit,
                    target_unit,
                    image_width,
                    image_height,
                ),
                allow_malformed=allow_malformed,
                extra=self.extra,
            )
        if not isinstance(self.vertices, list):
            raise ValueError("rbVertices must be a list.")
        if target_unit == self.unit:
            return self.with_values(unit=target_unit, allow_malformed=allow_malformed)
        return PolygonBoundary(
            unit=target_unit,
            vertices=[
                vertex.change_unit(
                    self.unit,
                    target_unit,
                    image_width=image_width,
                    image_height=image_height,
                    allow_malformed=allow_malformed,
                )
                for vertex in self.vertices
            ],
            allow_malformed=allow_malformed,
            extra=self.extra,
        )

    def _dict_full(self) -> dict[str, Any]:
        """Return all polygon fields, including missing fields as None.

        Returns:
            Complete diagnostic polygon dictionary.
        """

        vertices = self.vertices
        if isinstance(vertices, list):
            vertices = [vertex._dict_full() if hasattr(vertex, "_dict_full") else vertex for vertex in vertices]
        data = {
            "rbShape": "polygon",
            "rbUnit": self.unit,
            "rbVertices": vertices,
            **self.extra,
        }
        if self.coordinates is not None:
            data["rbCoordinates"] = coordinates_to_text(self.coordinates)
        return data

    def _dict_existing(self) -> dict[str, Any]:
        """Return only polygon fields that were present or valid extras.

        Returns:
            Polygon dictionary suitable for diagnostic rendering.
        """

        data = {"rbShape": "polygon", **self.extra}
        if self.unit is not None:
            data["rbUnit"] = self.unit
        vertices = self.vertices
        if vertices is not None:
            if isinstance(vertices, list):
                vertices = [
                    vertex._dict_existing() if hasattr(vertex, "_dict_existing") else vertex for vertex in vertices
                ]
            data["rbVertices"] = vertices
        if self.coordinates is not None:
            raw_coordinates = self.raw.get("rbCoordinates") if isinstance(self.raw, Mapping) else None
            data["rbCoordinates"] = (
                raw_coordinates if isinstance(raw_coordinates, str) else coordinates_to_text(self.coordinates)
            )
        return data

    def as_dict(self) -> dict[str, Any]:
        """Return a canonical polygon boundary dictionary.

        Returns:
            JSON-compatible polygon boundary.

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
        """Validate polygon fields, vertices, and shape constraints.

        Args:
            path: JSON-style path prefix for validation issues.
            image_width: Optional image width for pixel bounds.
            image_height: Optional image height for pixel bounds.
            ignore_dimensions: Skip missing image-dimension checks.

        Returns:
            Validation issues found on the polygon boundary.
        """

        path = "Polygon" if path is None else path
        issues: list[ValidationIssue] = []
        data = self._dict_full()
        issues.extend(validate_unknown_fields(data, POLYGON_SPEC.allowed_keys | POLYGON_SPEC.forbidden_keys, path))
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

        if self.vertices is None and self.coordinates is None:
            issues.append(
                issue(
                    "error",
                    "MISSING_BOUNDARY_FIELD",
                    f"{path}.rbVertices",
                    "polygon requires rbVertices or rbCoordinates.",
                )
            )
        if self.vertices is not None and self.coordinates is not None:
            issues.append(
                issue(
                    "error",
                    "FORBIDDEN_BOUNDARY_FIELD",
                    f"{path}.rbCoordinates",
                    "polygon must not use rbVertices and rbCoordinates together.",
                )
            )

        for key in sorted(POLYGON_SPEC.forbidden_keys):
            if key in data:
                issues.append(
                    issue(
                        "error",
                        "FORBIDDEN_BOUNDARY_FIELD",
                        f"{path}.{key}",
                        f"{key} must not be used with polygon boundaries.",
                    )
                )

        issues.extend(
            self._validate_vertices(
                f"{path}.rbVertices",
                image_width=image_width,
                image_height=image_height,
                ignore_dimensions=ignore_dimensions,
            )
        )
        issues.extend(self._validate_self_intersection(f"{path}.rbVertices"))
        issues.extend(self._deprecated_vertices_hint(f"{path}.rbVertices"))
        if self.coordinates is not None:
            issues.extend(
                validate_polygon_coordinates(
                    self.coordinates,
                    f"{path}.rbCoordinates",
                    unit=self.unit,
                    image_width=None if ignore_dimensions else image_width,
                    image_height=None if ignore_dimensions else image_height,
                )
            )
        return issues

    def _validate_vertices(
        self, path: str, *, image_width: float | None, image_height: float | None, ignore_dimensions: bool
    ) -> list[ValidationIssue]:
        """Validate the polygon vertex list and every contained vertex.

        Args:
            path: JSON-style path for the `rbVertices` field.
            image_width: Optional image width for pixel bounds.
            image_height: Optional image height for pixel bounds.
            ignore_dimensions: Skip image-dimension checks.

        Returns:
            Validation issues found on the vertex list.
        """

        if self.vertices is None:
            return []
        if not isinstance(self.vertices, list) or not self.vertices:
            return [issue("error", "INVALID_VERTICES", path, "Polygon boundaries require at least one vertex.")]

        issues: list[ValidationIssue] = []
        if self.unit == "relative":
            for index, vertex in enumerate(self.vertices):
                data = vertex._dict_full() if hasattr(vertex, "_dict_full") else vertex
                if isinstance(data, dict):
                    issues.extend(validate_relative_values(data, {"rbX", "rbY"}, f"{path}[{index}]"))
        for index, vertex in enumerate(self.vertices):
            issues.extend(
                vertex.validate(
                    f"{path}[{index}]",
                    unit=self.unit,
                    image_width=image_width,
                    image_height=image_height,
                    ignore_dimensions=ignore_dimensions,
                )
            )
        return issues

    def _deprecated_vertices_hint(self, path: str) -> list[ValidationIssue]:
        """Return an info hint when the deprecated Polygon Vertices property is used.

        IPTC 2026.1 deprecates rbVertices but still supports it, so this is an
        info issue that never makes the boundary invalid.
        """

        if not isinstance(self.vertices, list) or not self.vertices:
            return []
        replacement = {
            1: "use rbShape point with rbCoordinates [x, y]",
            2: "use rbShape linestring with rbCoordinates [[x1, y1], [x2, y2]]",
        }.get(len(self.vertices), "use rbCoordinates [[[x1, y1], ..., [x1, y1]]]")
        return [
            issue(
                "info",
                "DEPRECATED_POLYGON_VERTICES",
                path,
                f"rbVertices is deprecated since IPTC Photo Metadata 2026.1; {replacement}.",
            )
        ]

    def _validate_self_intersection(self, path: str) -> list[ValidationIssue]:
        """Validate that polygon edges do not cross themselves."""

        if not isinstance(self.vertices, list):
            return []

        points: list[tuple[float, float]] = []
        for vertex in self.vertices:
            x = number(getattr(vertex, "x", None))
            y = number(getattr(vertex, "y", None))
            if x is None or y is None:
                return []
            points.append((x, y))

        if len(points) >= 2 and _same_point(points[0], points[-1]):
            points = points[:-1]

        if len(points) < 3:
            return []

        if polygon_points_self_intersect(points):
            return [
                issue(
                    "error",
                    "SELF_INTERSECTING_POLYGON",
                    path,
                    "Polygon boundary edges must not intersect themselves.",
                )
            ]
        return []


def polygon_points_self_intersect(points: list[tuple[float, float]]) -> bool:
    """Return whether a polygon point sequence contains intersecting edges.

    Non-adjacent edges are compared with the exact ``_segments_intersect`` test, which also
    counts touching and overlapping edges. A sweep over the edges sorted by x skips pairs
    whose bounding boxes cannot overlap, so typical polygons need far fewer than n^2 tests.
    The result is the same as comparing every pair of edges.
    """

    if len(points) >= 2 and _same_point(points[0], points[-1]):
        points = points[:-1]

    if len(points) < 3:
        return False

    edge_count = len(points)
    edges = []
    for index in range(edge_count):
        start, end = points[index], points[(index + 1) % edge_count]
        edges.append(
            (
                min(start[0], end[0]) - _EPSILON,
                max(start[0], end[0]) + _EPSILON,
                min(start[1], end[1]) - _EPSILON,
                max(start[1], end[1]) + _EPSILON,
                index,
            )
        )
    edges.sort()

    active: list[tuple[float, float, float, float, int]] = []
    for min_x, max_x, min_y, max_y, index in edges:
        active = [edge for edge in active if edge[1] >= min_x]
        start, end = points[index], points[(index + 1) % edge_count]
        for _, _, other_min_y, other_max_y, other in active:
            if other_max_y < min_y or other_min_y > max_y:
                continue
            if _adjacent_edges(min(index, other), max(index, other), edge_count):
                continue
            if _segments_intersect(start, end, points[other], points[(other + 1) % edge_count]):
                return True
        active.append((min_x, max_x, min_y, max_y, index))
    return False


def validate_polygon_coordinates(
    coordinates: Any,
    path: str,
    *,
    unit: Any,
    image_width: float | None,
    image_height: float | None,
) -> list[ValidationIssue]:
    """Validate a full-polygon-array Boundary Coordinates value."""

    if not isinstance(coordinates, list):
        return [issue("error", "INVALID_BOUNDARY_COORDINATES", path, "polygon rbCoordinates must be an array.")]
    if not coordinates:
        return [issue("error", "INVALID_BOUNDARY_COORDINATES", path, "polygon rbCoordinates require an outer boundary.")]

    issues: list[ValidationIssue] = []
    for index, ring in enumerate(coordinates):
        issues.extend(
            _validate_polygon_coordinate_ring(
                ring,
                f"{path}[{index}]",
                unit=unit,
                image_width=image_width,
                image_height=image_height,
            )
        )
    issues.extend(_validate_full_polygon_array_relations(coordinates, path))
    return issues


def convert_polygon_coordinates(
    coordinates: Any,
    source_unit: BoundaryUnit,
    target_unit: BoundaryUnit,
    image_width: float | int,
    image_height: float | int,
) -> list[list[list[float]]]:
    """Convert polygon Boundary Coordinates to another measuring unit."""

    return [
        [convert_coordinate_point(point, source_unit, target_unit, image_width, image_height) for point in ring]
        for ring in coordinates
    ]


def _validate_polygon_coordinate_ring(
    ring: Any,
    path: str,
    *,
    unit: Any,
    image_width: float | None,
    image_height: float | None,
) -> list[ValidationIssue]:
    """Validate one closed polygon-array in Boundary Coordinates."""

    if not isinstance(ring, list):
        return [issue("error", "INVALID_BOUNDARY_COORDINATES", path, "polygon boundary must be an array.")]
    if len(ring) < 4:
        return [
            issue(
                "error",
                "INVALID_BOUNDARY_COORDINATES",
                path,
                "polygon boundary rbCoordinates require at least 4 points.",
            )
        ]

    issues: list[ValidationIssue] = []
    points: list[tuple[float, float]] = []
    for index, point in enumerate(ring):
        issues.extend(
            validate_coordinate_point(
                point,
                f"{path}[{index}]",
                unit=unit,
                image_width=image_width,
                image_height=image_height,
            )
        )
        if not isinstance(point, list) or len(point) != 2:
            continue
        x = number(point[0])
        y = number(point[1])
        if x is not None and y is not None:
            points.append((x, y))

    if len(points) != len(ring):
        return issues
    if points[0] != points[-1]:
        issues.append(
            issue(
                "error",
                "UNCLOSED_BOUNDARY_COORDINATES",
                path,
                "Polygon Boundary Coordinates must repeat the first vertex at the end.",
            )
        )
    if len(set(points[:-1])) < 3:
        issues.append(
            issue(
                "error",
                "INVALID_BOUNDARY_COORDINATES",
                path,
                "Polygon Boundary Coordinates require at least three distinct vertices.",
            )
        )
    if polygon_points_self_intersect(points):
        issues.append(
            issue(
                "error",
                "SELF_INTERSECTING_POLYGON",
                path,
                "Polygon boundary edges must not intersect themselves.",
            )
        )
    return issues


def _validate_full_polygon_array_relations(coordinates: Any, path: str) -> list[ValidationIssue]:
    """Validate outer/inner ring relationships inside one full-polygon-array."""

    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return []

    outer = _valid_coordinate_ring_points(coordinates[0])
    if outer is None:
        return []

    issues: list[ValidationIssue] = []
    inner_rings: list[tuple[int, list[tuple[float, float]]]] = []
    for index, ring in enumerate(coordinates[1:], start=1):
        points = _valid_coordinate_ring_points(ring)
        if points is None:
            continue
        inner_rings.append((index, points))
        issues.extend(_validate_inner_ring_against_outer(points, outer, f"{path}[{index}]"))

    for first_position, (first_index, first_ring) in enumerate(inner_rings):
        for second_index, second_ring in inner_rings[first_position + 1 :]:
            issues.extend(
                _validate_inner_ring_pair(
                    first_ring,
                    second_ring,
                    f"{path}[{second_index}]",
                    first_index=first_index,
                )
            )
    return issues


def _validate_inner_ring_against_outer(
    inner: list[tuple[float, float]],
    outer: list[tuple[float, float]],
    path: str,
) -> list[ValidationIssue]:
    """Validate one inner boundary against its outer boundary."""

    issues: list[ValidationIssue] = []
    relation = _ring_boundary_relation(inner, outer)
    if relation == "cross":
        issues.append(
            issue(
                "error",
                "INNER_BOUNDARY_INTERSECTS_OUTER",
                path,
                "Inner boundaries must not intersect the outer boundary.",
            )
        )
    elif relation == "touch":
        issues.append(
            issue(
                "warning",
                "INNER_BOUNDARY_TOUCHES_OUTER",
                path,
                "Inner boundaries should not touch the outer boundary.",
            )
        )

    outside = False
    touches = relation == "touch"
    for point in inner:
        location = _point_ring_location(point, outer)
        if location == "outside":
            outside = True
        elif location == "boundary":
            touches = True

    if outside:
        issues.append(
            issue(
                "error",
                "INNER_BOUNDARY_OUTSIDE_OUTER",
                path,
                "Inner boundaries must not extend outside the outer boundary.",
            )
        )
    elif touches and relation != "touch":
        issues.append(
            issue(
                "warning",
                "INNER_BOUNDARY_TOUCHES_OUTER",
                path,
                "Inner boundaries should not touch the outer boundary.",
            )
        )
    return issues


def _validate_inner_ring_pair(
    first: list[tuple[float, float]],
    second: list[tuple[float, float]],
    path: str,
    *,
    first_index: int,
) -> list[ValidationIssue]:
    """Validate two inner boundaries within the same full-polygon-array."""

    issues: list[ValidationIssue] = []
    relation = _ring_boundary_relation(first, second)
    interiors_overlap = _rings_have_overlapping_interiors(first, second)
    if relation == "cross" or interiors_overlap:
        issues.append(
            issue(
                "error",
                "INNER_BOUNDARIES_INTERSECT",
                path,
                f"Inner boundary {first_index} and this inner boundary must not intersect each other.",
            )
        )
    elif relation == "touch":
        issues.append(
            issue(
                "warning",
                "INNER_BOUNDARIES_TOUCH",
                path,
                f"Inner boundary {first_index} and this inner boundary should not touch each other.",
            )
        )
    return issues


def _valid_coordinate_ring_points(ring: Any) -> list[tuple[float, float]] | None:
    """Return normalized ring points when the ring can support relation checks."""

    if not isinstance(ring, list) or len(ring) < 4:
        return None

    points: list[tuple[float, float]] = []
    for point in ring:
        if not isinstance(point, list) or len(point) != 2:
            return None
        x = number(point[0])
        y = number(point[1])
        if x is None or y is None:
            return None
        points.append((x, y))

    if not _same_point(points[0], points[-1]):
        return None
    points = points[:-1]
    if len(set(points)) < 3 or polygon_points_self_intersect(points):
        return None
    return points


def _rings_have_overlapping_interiors(first: list[tuple[float, float]], second: list[tuple[float, float]]) -> bool:
    """Return whether two simple rings enclose overlapping interior area."""

    if _ring_boundary_relation(first, second) == "cross":
        return True
    # Without crossing edges, the rings are disjoint, touching, or nested. Edge
    # midpoints catch nested rings whose vertices all lie on the other boundary.
    if any(_point_ring_location(point, second) == "inside" for point in _ring_probe_points(first)):
        return True
    if any(_point_ring_location(point, first) == "inside" for point in _ring_probe_points(second)):
        return True
    # Identical areas: every vertex of each ring lies on the other boundary.
    return all(_point_ring_location(point, second) == "boundary" for point in first) and all(
        _point_ring_location(point, first) == "boundary" for point in second
    )


def ring_within_ring(inner: list[tuple[float, float]], container: list[tuple[float, float]]) -> bool:
    """Return whether a simple ring lies inside or on the boundary of another simple ring."""

    if _ring_boundary_relation(inner, container) == "cross":
        return False
    return all(_point_ring_location(point, container) != "outside" for point in _ring_probe_points(inner))


def _ring_probe_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Return ring vertices plus edge midpoints for containment tests."""

    midpoints = [((start[0] + end[0]) / 2, (start[1] + end[1]) / 2) for start, end in _ring_edges(points)]
    return [*points, *midpoints]


def _ring_boundary_relation(first: list[tuple[float, float]], second: list[tuple[float, float]]) -> str:
    """Return whether two ring boundaries cross or only touch."""

    touches = False
    for first_edge in _ring_edges(first):
        for second_edge in _ring_edges(second):
            relation = _segment_intersection_relation(first_edge[0], first_edge[1], second_edge[0], second_edge[1])
            if relation == "cross":
                return "cross"
            if relation == "touch":
                touches = True
    return "touch" if touches else "none"


def _ring_edges(points: list[tuple[float, float]]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Return the closed edge list for a normalized ring."""

    return [(points[index], points[(index + 1) % len(points)]) for index in range(len(points))]


def _point_ring_location(point: tuple[float, float], ring: list[tuple[float, float]]) -> str:
    """Return whether a point is inside, outside, or on a ring boundary."""

    for start, end in _ring_edges(ring):
        if _orientation(start, end, point) == 0 and _on_segment(start, point, end):
            return "boundary"

    inside = False
    x, y = point
    for start, end in _ring_edges(ring):
        y1 = start[1]
        y2 = end[1]
        if (y1 > y) == (y2 > y):
            continue
        x_intersection = (end[0] - start[0]) * (y - y1) / (y2 - y1) + start[0]
        if x_intersection > x:
            inside = not inside
    return "inside" if inside else "outside"


def _adjacent_edges(first_index: int, second_index: int, edge_count: int) -> bool:
    """Return whether two closed polygon edges share an endpoint."""

    if abs(first_index - second_index) == 1:
        return True
    return {first_index, second_index} == {0, edge_count - 1}


def _segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    """Return whether two line segments intersect, including overlaps."""

    o1 = _orientation(a, b, c)
    o2 = _orientation(a, b, d)
    o3 = _orientation(c, d, a)
    o4 = _orientation(c, d, b)

    if o1 == 0 and _on_segment(a, c, b):
        return True
    if o2 == 0 and _on_segment(a, d, b):
        return True
    if o3 == 0 and _on_segment(c, a, d):
        return True
    if o4 == 0 and _on_segment(c, b, d):
        return True
    return o1 != o2 and o3 != o4


def _segment_intersection_relation(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> str:
    """Classify a segment intersection as crossing, touching, or none."""

    o1 = _orientation(a, b, c)
    o2 = _orientation(a, b, d)
    o3 = _orientation(c, d, a)
    o4 = _orientation(c, d, b)

    if not _segments_intersect(a, b, c, d):
        return "none"
    if o1 == o2 == o3 == o4 == 0:
        return "touch"
    if o1 == 0 and _on_segment(a, c, b):
        return "touch"
    if o2 == 0 and _on_segment(a, d, b):
        return "touch"
    if o3 == 0 and _on_segment(c, a, d):
        return "touch"
    if o4 == 0 and _on_segment(c, b, d):
        return "touch"
    return "cross"


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> int:
    """Return segment orientation for three points."""

    value = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])
    if abs(value) < 1e-12:
        return 0
    return 1 if value > 0 else 2


def _on_segment(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> bool:
    """Return whether point b lies on segment ac."""

    return (
        min(a[0], c[0]) - 1e-12 <= b[0] <= max(a[0], c[0]) + 1e-12
        and min(a[1], c[1]) - 1e-12 <= b[1] <= max(a[1], c[1]) + 1e-12
    )


def _same_point(a: tuple[float, float], b: tuple[float, float]) -> bool:
    """Return whether two points are equivalent for polygon closure."""

    return abs(a[0] - b[0]) < 1e-12 and abs(a[1] - b[1]) < 1e-12
