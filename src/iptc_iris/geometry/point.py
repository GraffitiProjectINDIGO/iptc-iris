"""Point Region Boundary geometry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from iptc_iris.models import ValidationIssue

from .base import BoundaryUnit
from .coordinate import CoordinateBoundary, CoordinateShape, convert_coordinate_point, validate_coordinate_point


@dataclass(frozen=True)
class PointBoundary(CoordinateBoundary):
    """Point Region Boundary geometry."""

    shape: CoordinateShape = "point"

    def _validate_coordinates(
        self,
        path: str,
        *,
        unit: Any,
        image_width: float | None,
        image_height: float | None,
    ) -> list[ValidationIssue]:
        """Validate the point Boundary Coordinates payload."""

        return validate_coordinate_point(
            self.coordinates,
            path,
            unit=unit,
            image_width=image_width,
            image_height=image_height,
        )

    def _convert_coordinates(
        self,
        source_unit: BoundaryUnit,
        target_unit: BoundaryUnit,
        image_width: float | int,
        image_height: float | int,
    ) -> list[float]:
        """Convert point Boundary Coordinates to another measuring unit."""

        return convert_coordinate_point(self.coordinates, source_unit, target_unit, image_width, image_height)
