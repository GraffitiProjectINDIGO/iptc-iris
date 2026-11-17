"""Geometry classes for IPTC Image Region boundaries."""

from .base import BoundaryUnit, InvalidBoundary, MissingBoundary, RegionBoundary, UnknownBoundary
from .circle import CircleBoundary
from .coordinate import (
    CoordinateBoundary,
    MultiboundaryPart,
    join_multiboundary_parts,
    split_multiboundary_parts,
)
from .linestring import LineStringBoundary
from .multilinestring import MultiLineStringBoundary
from .multipoint import MultiPointBoundary
from .multipolygon import MultiPolygonBoundary
from .point import PointBoundary
from .polygon import PolygonBoundary, Vertex
from .rectangle import RectangleBoundary

__all__ = [
    "CircleBoundary",
    "BoundaryUnit",
    "CoordinateBoundary",
    "InvalidBoundary",
    "LineStringBoundary",
    "MissingBoundary",
    "MultiboundaryPart",
    "MultiLineStringBoundary",
    "MultiPointBoundary",
    "MultiPolygonBoundary",
    "PointBoundary",
    "PolygonBoundary",
    "RectangleBoundary",
    "RegionBoundary",
    "UnknownBoundary",
    "Vertex",
    "join_multiboundary_parts",
    "split_multiboundary_parts",
]
