"""Pinned IPTC Image Region vocabulary and validation rule metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

IPTC_PHOTO_METADATA_STANDARD_VERSION = "2025.1"
IPTC_PHOTO_METADATA_STANDARD_URL = "https://www.iptc.org/std/photometadata/specification/IPTC-PhotoMetadata-2025.1.html"
IPTC_IMAGE_REGION_SECTIONS = ("11.20", "12.6", "12.7", "12.8")

BoundaryShapeName = Literal[
    "rectangle",
    "circle",
    "point",
    "multipoint",
    "linestring",
    "multilinestring",
    "polygon",
    "multipolygon",
]
BoundaryUnitName = Literal["pixel", "relative"]

# Validation profiles. "2025.1" is the published IPTC Photo Metadata Standard;
# "2026.1-draft" adds the Extended Image Region Boundaries draft submission.
Standard = Literal["2025.1", "2026.1-draft"]
IPTC_STANDARDS: tuple[Standard, ...] = ("2025.1", "2026.1-draft")
DEFAULT_STANDARD: Standard = "2025.1"
DRAFT_STANDARD: Standard = "2026.1-draft"
SHAPES_2025_1 = frozenset({"rectangle", "circle", "polygon"})


def require_standard(value: object) -> Standard:
    """Return a supported standard profile name or raise ValueError."""

    if value not in IPTC_STANDARDS:
        raise ValueError(f"standard must be one of: {', '.join(IPTC_STANDARDS)}.")
    return value  # type: ignore[return-value]


@dataclass(frozen=True)
class BoundaryShapeSpec:
    """Formal validation vocabulary for one IPTC Region Boundary shape.

    Attributes:
        name: Shape identifier used by `rbShape`.
        allowed_keys: Boundary keys that are native to this shape.
        required_keys: Shape-specific keys that must be present.
        forbidden_keys: Boundary keys that belong to other shapes.
        coordinate_keys: Coordinate fields used by this shape.
        size_keys: Positive dimension/radius fields used by this shape.
    """

    name: BoundaryShapeName
    allowed_keys: frozenset[str]
    required_keys: frozenset[str]
    forbidden_keys: frozenset[str]
    coordinate_keys: frozenset[str]
    size_keys: frozenset[str]


ALLOWED_UNITS = frozenset[BoundaryUnitName]({"pixel", "relative"})
VERTEX_KEYS = frozenset({"rbX", "rbY"})
ENTITY_ARRAY_KEYS = frozenset({"rCtype", "rRole"})
REGION_KEYS = frozenset({"rId", "name", "regionBoundary", "rCtype", "rRole", "rMemberOf"})

RECTANGLE_SPEC = BoundaryShapeSpec(
    name="rectangle",
    allowed_keys=frozenset({"rbShape", "rbUnit", "rbX", "rbY", "rbW", "rbH"}),
    required_keys=frozenset({"rbX", "rbY", "rbW", "rbH"}),
    forbidden_keys=frozenset({"rbRx", "rbVertices", "rbCoordinates", "rbMbPartDetails"}),
    coordinate_keys=frozenset({"rbX", "rbY"}),
    size_keys=frozenset({"rbW", "rbH"}),
)
CIRCLE_SPEC = BoundaryShapeSpec(
    name="circle",
    allowed_keys=frozenset({"rbShape", "rbUnit", "rbX", "rbY", "rbRx"}),
    required_keys=frozenset({"rbX", "rbY", "rbRx"}),
    forbidden_keys=frozenset({"rbW", "rbH", "rbVertices", "rbCoordinates", "rbMbPartDetails"}),
    coordinate_keys=frozenset({"rbX", "rbY"}),
    size_keys=frozenset({"rbRx"}),
)
POINT_SPEC = BoundaryShapeSpec(
    name="point",
    allowed_keys=frozenset({"rbShape", "rbUnit", "rbCoordinates"}),
    required_keys=frozenset({"rbCoordinates"}),
    forbidden_keys=frozenset({"rbX", "rbY", "rbW", "rbH", "rbRx", "rbVertices", "rbMbPartDetails"}),
    coordinate_keys=frozenset({"rbCoordinates"}),
    size_keys=frozenset(),
)
MULTIPOINT_SPEC = BoundaryShapeSpec(
    name="multipoint",
    allowed_keys=frozenset({"rbShape", "rbUnit", "rbCoordinates", "rbMbPartDetails"}),
    required_keys=frozenset({"rbCoordinates"}),
    forbidden_keys=frozenset({"rbX", "rbY", "rbW", "rbH", "rbRx", "rbVertices"}),
    coordinate_keys=frozenset({"rbCoordinates"}),
    size_keys=frozenset(),
)
LINESTRING_SPEC = BoundaryShapeSpec(
    name="linestring",
    allowed_keys=frozenset({"rbShape", "rbUnit", "rbCoordinates"}),
    required_keys=frozenset({"rbCoordinates"}),
    forbidden_keys=frozenset({"rbX", "rbY", "rbW", "rbH", "rbRx", "rbVertices", "rbMbPartDetails"}),
    coordinate_keys=frozenset({"rbCoordinates"}),
    size_keys=frozenset(),
)
MULTILINESTRING_SPEC = BoundaryShapeSpec(
    name="multilinestring",
    allowed_keys=frozenset({"rbShape", "rbUnit", "rbCoordinates", "rbMbPartDetails"}),
    required_keys=frozenset({"rbCoordinates"}),
    forbidden_keys=frozenset({"rbX", "rbY", "rbW", "rbH", "rbRx", "rbVertices"}),
    coordinate_keys=frozenset({"rbCoordinates"}),
    size_keys=frozenset(),
)
POLYGON_SPEC = BoundaryShapeSpec(
    name="polygon",
    allowed_keys=frozenset({"rbShape", "rbUnit", "rbVertices", "rbCoordinates"}),
    required_keys=frozenset(),
    forbidden_keys=frozenset({"rbX", "rbY", "rbW", "rbH", "rbRx"}),
    coordinate_keys=frozenset({"rbCoordinates"}),
    size_keys=frozenset(),
)
MULTIPOLYGON_SPEC = BoundaryShapeSpec(
    name="multipolygon",
    allowed_keys=frozenset({"rbShape", "rbUnit", "rbCoordinates", "rbMbPartDetails"}),
    required_keys=frozenset({"rbCoordinates"}),
    forbidden_keys=frozenset({"rbX", "rbY", "rbW", "rbH", "rbRx", "rbVertices"}),
    coordinate_keys=frozenset({"rbCoordinates"}),
    size_keys=frozenset(),
)

BOUNDARY_SHAPE_SPECS: dict[BoundaryShapeName, BoundaryShapeSpec] = {
    "rectangle": RECTANGLE_SPEC,
    "circle": CIRCLE_SPEC,
    "point": POINT_SPEC,
    "multipoint": MULTIPOINT_SPEC,
    "linestring": LINESTRING_SPEC,
    "multilinestring": MULTILINESTRING_SPEC,
    "polygon": POLYGON_SPEC,
    "multipolygon": MULTIPOLYGON_SPEC,
}
ALLOWED_SHAPES = frozenset(BOUNDARY_SHAPE_SPECS)
BOUNDARY_KEYS = frozenset().union(*(spec.allowed_keys for spec in BOUNDARY_SHAPE_SPECS.values()))
POINT_KEYS = frozenset({"rbX", "rbY"})
SIZE_KEYS = frozenset().union(*(spec.size_keys for spec in BOUNDARY_SHAPE_SPECS.values()))
