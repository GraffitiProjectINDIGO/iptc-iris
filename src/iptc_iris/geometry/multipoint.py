"""Multipoint Region Boundary geometry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from iptc_iris.models import ValidationIssue

from .base import BoundaryUnit, issue
from .coordinate import (
    CoordinateBoundary,
    CoordinateShape,
    convert_coordinate_point,
    coordinate_point_key,
    validate_coordinate_point,
)


@dataclass(frozen=True)
class MultiPointBoundary(CoordinateBoundary):
    """Multipoint Region Boundary geometry."""

    shape: CoordinateShape = "multipoint"

    def _validate_coordinates(
        self,
        path: str,
        *,
        unit: Any,
        image_width: float | None,
        image_height: float | None,
    ) -> list[ValidationIssue]:
        """Validate the multipoint Boundary Coordinates payload."""

        if not isinstance(self.coordinates, list):
            return [issue("error", "INVALID_BOUNDARY_COORDINATES", path, "multipoint rbCoordinates must be an array.")]
        if len(self.coordinates) < 2:
            return [
                issue(
                    "error",
                    "INVALID_BOUNDARY_COORDINATES",
                    path,
                    "multipoint rbCoordinates require at least 2 points.",
                )
            ]

        issues: list[ValidationIssue] = []
        first_use: dict[tuple[float, float], int] = {}
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
            key = coordinate_point_key(point)
            if key is None:
                continue
            if key in first_use:
                issues.append(
                    issue(
                        "error",
                        "DUPLICATE_MULTIPOINT_POINT",
                        f"{path}[{index}]",
                        f"multipoint must not contain the same point more than once (see {path}[{first_use[key]}]).",
                    )
                )
            else:
                first_use[key] = index
        return issues

    def _convert_coordinates(
        self,
        source_unit: BoundaryUnit,
        target_unit: BoundaryUnit,
        image_width: float | int,
        image_height: float | int,
    ) -> list[list[float]]:
        """Convert multipoint Boundary Coordinates to another measuring unit."""

        return [
            convert_coordinate_point(point, source_unit, target_unit, image_width, image_height)
            for point in self.coordinates
        ]
