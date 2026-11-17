"""Multilinestring Region Boundary geometry."""

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
class MultiLineStringBoundary(CoordinateBoundary):
    """Multilinestring Region Boundary geometry."""

    shape: CoordinateShape = "multilinestring"

    def _validate_coordinates(
        self,
        path: str,
        *,
        unit: Any,
        image_width: float | None,
        image_height: float | None,
    ) -> list[ValidationIssue]:
        """Validate the multilinestring Boundary Coordinates payload."""

        if not isinstance(self.coordinates, list):
            return [
                issue("error", "INVALID_BOUNDARY_COORDINATES", path, "multilinestring rbCoordinates must be an array.")
            ]
        if len(self.coordinates) < 2:
            return [
                issue(
                    "error",
                    "INVALID_BOUNDARY_COORDINATES",
                    path,
                    "multilinestring requires at least two linestrings.",
                )
            ]

        issues: list[ValidationIssue] = []
        first_use: dict[tuple[tuple[float, float], ...], int] = {}
        for index, line in enumerate(self.coordinates):
            issues.extend(
                self._validate_linestring(
                    line,
                    f"{path}[{index}]",
                    unit=unit,
                    image_width=image_width,
                    image_height=image_height,
                )
            )
            key = _linestring_key(line)
            if key is None:
                continue
            if key in first_use:
                issues.append(
                    issue(
                        "error",
                        "DUPLICATE_LINESTRING",
                        f"{path}[{index}]",
                        "multilinestring must not contain the same linestring more than once, "
                        f"including in reverse order (see {path}[{first_use[key]}]).",
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
    ) -> list[list[list[float]]]:
        """Convert multilinestring Boundary Coordinates to another measuring unit."""

        return [
            [convert_coordinate_point(point, source_unit, target_unit, image_width, image_height) for point in line]
            for line in self.coordinates
        ]

    @staticmethod
    def _validate_linestring(
        line: Any,
        path: str,
        *,
        unit: Any,
        image_width: float | None,
        image_height: float | None,
    ) -> list[ValidationIssue]:
        """Validate one linestring in a multilinestring."""

        if not isinstance(line, list):
            return [issue("error", "INVALID_BOUNDARY_COORDINATES", path, "linestring rbCoordinates must be an array.")]
        if len(line) < 2:
            return [
                issue(
                    "error",
                    "INVALID_BOUNDARY_COORDINATES",
                    path,
                    "linestring rbCoordinates require at least 2 points.",
                )
            ]

        issues: list[ValidationIssue] = []
        for index, point in enumerate(line):
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


def _linestring_key(line: Any) -> tuple[tuple[float, float], ...] | None:
    """Return a direction-independent key for a valid linestring, else None."""

    if not isinstance(line, list):
        return None
    points = [coordinate_point_key(point) for point in line]
    if not points or any(point is None for point in points):
        return None
    forward = tuple(point for point in points if point is not None)
    return min(forward, forward[::-1])
