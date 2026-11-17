"""Tests for the pinned IPTC Image Region specification metadata."""

from __future__ import annotations

from iptc_iris.spec import (
    ALLOWED_SHAPES,
    ALLOWED_UNITS,
    BOUNDARY_KEYS,
    BOUNDARY_SHAPE_SPECS,
    CIRCLE_SPEC,
    IPTC_IMAGE_REGION_SECTIONS,
    IPTC_PHOTO_METADATA_STANDARD_URL,
    IPTC_PHOTO_METADATA_STANDARD_VERSION,
    LINESTRING_SPEC,
    MULTILINESTRING_SPEC,
    MULTIPOINT_SPEC,
    MULTIPOLYGON_SPEC,
    POINT_SPEC,
    POLYGON_SPEC,
    RECTANGLE_SPEC,
    SIZE_KEYS,
    VERTEX_KEYS,
)


def test_spec_version_is_pinned_to_current_reference():
    assert IPTC_PHOTO_METADATA_STANDARD_VERSION == "2025.1"
    assert IPTC_PHOTO_METADATA_STANDARD_URL.endswith("IPTC-PhotoMetadata-2025.1.html")
    assert IPTC_IMAGE_REGION_SECTIONS == ("11.20", "12.6", "12.7", "12.8")


def test_boundary_shape_specs_define_core_geometry_rules():
    assert ALLOWED_UNITS == frozenset({"pixel", "relative"})
    assert ALLOWED_SHAPES == frozenset(
        {"rectangle", "circle", "point", "multipoint", "linestring", "multilinestring", "polygon", "multipolygon"}
    )
    assert BOUNDARY_SHAPE_SPECS["rectangle"] is RECTANGLE_SPEC
    assert BOUNDARY_SHAPE_SPECS["circle"] is CIRCLE_SPEC
    assert BOUNDARY_SHAPE_SPECS["point"] is POINT_SPEC
    assert BOUNDARY_SHAPE_SPECS["multipoint"] is MULTIPOINT_SPEC
    assert BOUNDARY_SHAPE_SPECS["linestring"] is LINESTRING_SPEC
    assert BOUNDARY_SHAPE_SPECS["multilinestring"] is MULTILINESTRING_SPEC
    assert BOUNDARY_SHAPE_SPECS["polygon"] is POLYGON_SPEC
    assert BOUNDARY_SHAPE_SPECS["multipolygon"] is MULTIPOLYGON_SPEC

    assert RECTANGLE_SPEC.required_keys == frozenset({"rbX", "rbY", "rbW", "rbH"})
    assert RECTANGLE_SPEC.forbidden_keys == frozenset({"rbRx", "rbVertices", "rbCoordinates", "rbMbPartDetails"})
    assert CIRCLE_SPEC.required_keys == frozenset({"rbX", "rbY", "rbRx"})
    assert CIRCLE_SPEC.forbidden_keys == frozenset({"rbW", "rbH", "rbVertices", "rbCoordinates", "rbMbPartDetails"})
    assert POINT_SPEC.required_keys == frozenset({"rbCoordinates"})
    assert LINESTRING_SPEC.required_keys == frozenset({"rbCoordinates"})
    assert MULTIPOLYGON_SPEC.required_keys == frozenset({"rbCoordinates"})
    assert POLYGON_SPEC.required_keys == frozenset()
    assert POLYGON_SPEC.forbidden_keys == frozenset({"rbX", "rbY", "rbW", "rbH", "rbRx"})
    assert VERTEX_KEYS == frozenset({"rbX", "rbY"})
    assert SIZE_KEYS == frozenset({"rbW", "rbH", "rbRx"})


def test_boundary_keys_are_derived_from_shape_specs():
    expected_keys = frozenset().union(*(spec.allowed_keys for spec in BOUNDARY_SHAPE_SPECS.values()))

    assert BOUNDARY_KEYS == expected_keys
