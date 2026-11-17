"""Linestring Region Boundary geometry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from iptc_iris.models import ValidationIssue

from .base import BoundaryUnit, issue
from .coordinate import CoordinateBoundary, CoordinateShape, convert_coordinate_point, validate_coordinate_point


@dataclass(frozen=True)
class LineStringBoundary(CoordinateBoundary):
    """Linestring Region Boundary geometry."""

    shape: CoordinateShape = "linestring"

    def _validate_coordinates(
        self,
        path: str,
        *,
        unit: Any,
        image_width: float | None,
        image_height: float | None,
    ) -> list[ValidationIssue]:
        """Validate the linestring Boundary Coordinates payload."""

        if not isinstance(self.coordinates, list):
            return [issue("error", "INVALID_BOUNDARY_COORDINATES", path, "linestring rbCoordinates must be an array.")]
        if len(self.coordinates) < 2:
            return [
                issue(
                    "error",
                    "INVALID_BOUNDARY_COORDINATES",
                    path,
                    "linestring rbCoordinates require at least 2 points.",
                )
            ]

        issues: list[ValidationIssue] = []
        for index, point in enumerate(self.coordinates):
            issues.extend(
                validate_coordinate_point(
                    point,
                    f"{path}[{index}]",
                    unit=unit,
                    image_width=image_width,
                    image_height=image_height,
                )
            )
        return issues

    def _convert_coordinates(
        self,
        source_unit: BoundaryUnit,
        target_unit: BoundaryUnit,
        image_width: float | int,
        image_height: float | int,
    ) -> list[list[float]]:
        """Convert linestring Boundary Coordinates to another measuring unit."""

        return [
            convert_coordinate_point(point, source_unit, target_unit, image_width, image_height)
            for point in self.coordinates
        ]
