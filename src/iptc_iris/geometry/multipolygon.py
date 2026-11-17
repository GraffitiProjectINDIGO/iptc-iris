"""Multipolygon Region Boundary geometry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from iptc_iris.models import ValidationIssue

from .base import BoundaryUnit, issue
from .coordinate import CoordinateBoundary, CoordinateShape
from .polygon import (
    _rings_have_overlapping_interiors,
    _valid_coordinate_ring_points,
    convert_polygon_coordinates,
    ring_within_ring,
    validate_polygon_coordinates,
)


@dataclass(frozen=True)
class MultiPolygonBoundary(CoordinateBoundary):
    """Multipolygon Region Boundary geometry."""

    shape: CoordinateShape = "multipolygon"

    def _validate_coordinates(
        self,
        path: str,
        *,
        unit: Any,
        image_width: float | None,
        image_height: float | None,
    ) -> list[ValidationIssue]:
        """Validate the multipolygon Boundary Coordinates payload."""

        if not isinstance(self.coordinates, list):
            return [issue("error", "INVALID_BOUNDARY_COORDINATES", path, "multipolygon rbCoordinates must be an array.")]
        if len(self.coordinates) < 2:
            return [issue("error", "INVALID_BOUNDARY_COORDINATES", path, "multipolygon requires at least two polygons.")]

        issues: list[ValidationIssue] = []
        for index, polygon in enumerate(self.coordinates):
            issues.extend(
                validate_polygon_coordinates(
                    polygon,
                    f"{path}[{index}]",
                    unit=unit,
                    image_width=image_width,
                    image_height=image_height,
                )
            )
        issues.extend(validate_multipolygon_outer_boundaries(self.coordinates, path))
        return issues

    def _convert_coordinates(
        self,
        source_unit: BoundaryUnit,
        target_unit: BoundaryUnit,
        image_width: float | int,
        image_height: float | int,
    ) -> list[list[list[list[float]]]]:
        """Convert multipolygon Boundary Coordinates to another measuring unit."""

        return [
            convert_polygon_coordinates(polygon, source_unit, target_unit, image_width, image_height)
            for polygon in self.coordinates
        ]


def validate_multipolygon_outer_boundaries(
    coordinates: Any,
    path: str,
) -> list[ValidationIssue]:
    """Validate that the polygons of a multipolygon do not share interior area.

    Inner boundaries (holes) are excluded from a polygon's area, so a polygon
    lying completely inside a hole of another polygon does not overlap it.
    """

    if not isinstance(coordinates, list):
        return []

    polygons: list[tuple[int, list[tuple[float, float]], list[list[tuple[float, float]]]]] = []
    for index, polygon in enumerate(coordinates):
        if not isinstance(polygon, list) or not polygon:
            continue
        outer = _valid_coordinate_ring_points(polygon[0])
        if outer is None:
            continue
        holes = [ring for ring in (_valid_coordinate_ring_points(item) for item in polygon[1:]) if ring is not None]
        polygons.append((index, outer, holes))

    issues: list[ValidationIssue] = []
    for first_position, (_first_index, first_outer, first_holes) in enumerate(polygons):
        for second_index, second_outer, second_holes in polygons[first_position + 1 :]:
            if _polygons_have_overlapping_interiors(first_outer, first_holes, second_outer, second_holes):
                issues.append(
                    issue(
                        "error",
                        "OVERLAPPING_MULTIPOLYGON_BOUNDARIES",
                        f"{path}[{second_index}][0]",
                        "Multipolygon polygons must not have overlapping interior areas.",
                    )
                )
    return issues


def _polygons_have_overlapping_interiors(
    first_outer: list[tuple[float, float]],
    first_holes: list[list[tuple[float, float]]],
    second_outer: list[tuple[float, float]],
    second_holes: list[list[tuple[float, float]]],
) -> bool:
    """Return whether two polygons with optional holes share interior area."""

    if not _rings_have_overlapping_interiors(first_outer, second_outer):
        return False
    # Outer areas overlap. This is only allowed when one polygon lies entirely
    # inside a hole of the other one.
    if ring_within_ring(second_outer, first_outer):
        return not any(ring_within_ring(second_outer, hole) for hole in first_holes)
    if ring_within_ring(first_outer, second_outer):
        return not any(ring_within_ring(first_outer, hole) for hole in second_holes)
    return True
