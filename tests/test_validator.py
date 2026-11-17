"""Tests for IPTC Image Region validation rules and reported issues."""

import math

import pytest

from iptc_iris import (
    DRAFT_STANDARD,
    FixAction,
    FixResult,
    ImageRegion,
    ImageRegionList,
    LineStringBoundary,
    MultiPolygonBoundary,
    PointBoundary,
    RectangleBoundary,
    normalize_metadata,
    safe_fix_metadata,
)
from iptc_iris.geometry import CircleBoundary, PolygonBoundary, Vertex


def test_valid_rectangle_region():
    result = normalize_metadata(
        {
            "imageWidth": 1000,
            "imageHeight": 500,
            "imageRegion": [
                {
                    "rId": "region-1",
                    "regionBoundary": {
                        "rbShape": "rectangle",
                        "rbUnit": "pixel",
                        "rbX": 10,
                        "rbY": 20,
                        "rbW": 300,
                        "rbH": 100,
                    },
                    "rCtype": [
                        {
                            "identifiers": ["http://cv.iptc.org/newscodes/imageregiontype/human"],
                            "name": {"x-default": "human"},
                        }
                    ],
                }
            ],
        }
    ).validation_result()

    assert result.valid
    assert result.issues == []


def test_safe_fix_metadata_public_api_removes_fixable_fields():
    metadata = normalize_metadata(
        {
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "rectangle",
                        "rbUnit": "relative",
                        "rbX": 0.1,
                        "rbY": 0.2,
                        "rbW": 0.3,
                        "rbH": 0.4,
                        "rbE": "remove me",
                    }
                }
            ]
        }
    )

    result = safe_fix_metadata(metadata)

    assert isinstance(result, FixResult)
    assert result.fixed
    assert result.metadata is not None
    assert result.original_validation.errors[0].code == "UNKNOWN_BOUNDARY_FIELD"
    assert result.fixed_validation is not None
    assert result.fixed_validation.valid
    assert isinstance(result.fixes[0], FixAction)
    assert "rbE" not in result.metadata.as_dict()["imageRegion"][0]["regionBoundary"]


def test_safe_fix_metadata_public_api_returns_valid_metadata_without_changes():
    metadata = normalize_metadata(
        {
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "rectangle",
                        "rbUnit": "relative",
                        "rbX": 0.1,
                        "rbY": 0.2,
                        "rbW": 0.3,
                        "rbH": 0.4,
                    }
                }
            ]
        }
    )

    result = safe_fix_metadata(metadata)

    assert not result.fixed
    assert result.metadata is metadata
    assert result.fixes == []
    assert result.original_validation.valid
    assert result.fixed_validation is result.original_validation


def test_normalized_metadata_returns_typed_metadata_and_issues():
    metadata = normalize_metadata(
        {
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "rectangle",
                        "rbUnit": "relative",
                        "rbX": 0.1,
                        "rbY": 0.2,
                        "rbW": 0.3,
                        "rbH": 0.4,
                    }
                }
            ]
        }
    )

    assert metadata.valid
    assert isinstance(metadata.image_regions[0].boundary, RectangleBoundary)


def test_created_rectangle_boundary_does_not_require_raw_data():
    metadata = normalize_metadata(
        {
            "imageRegion": ImageRegionList(
                ImageRegion(boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4))
            )
        }
    )

    assert metadata.valid
    assert metadata.as_dict()["imageRegion"][0]["regionBoundary"] == {
        "rbShape": "rectangle",
        "rbUnit": "relative",
        "rbX": 0.1,
        "rbY": 0.2,
        "rbW": 0.3,
        "rbH": 0.4,
    }


def test_image_region_list_manages_regions_by_id():
    first = ImageRegion(
        r_id="first",
        boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4),
    )
    second = ImageRegion(
        r_id="second",
        boundary=RectangleBoundary(unit="relative", x=0.2, y=0.2, width=0.3, height=0.4),
    )
    regions = ImageRegionList(first)

    regions.add_region(second)

    assert len(regions) == 2
    assert regions.get_region("second") is second
    assert regions.delete_region("first")
    assert regions.get_region("first") is None


def test_image_region_valid_errors_and_warnings_properties():
    valid_region = ImageRegion(
        boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4),
    )
    invalid_region = ImageRegion.from_raw(
        {"rId": 123, "regionBoundary": {"rbShape": "circle", "rbUnit": "relative"}},
        allow_malformed=True,
    )
    warning_region = ImageRegion(
        r_id="",
        boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4),
    )

    assert valid_region.valid
    assert valid_region.errors == []
    assert not invalid_region.valid
    assert {issue.code for issue in invalid_region.errors} >= {"REGION_ID_NOT_STRING", "MISSING_BOUNDARY_FIELD"}
    assert warning_region.valid
    assert warning_region.warnings[0].code == "EMPTY_REGION_ID"


def test_diagnostic_export_preserves_malformed_boundary_fields():
    metadata = normalize_metadata(
        {
            "imageRegion": [
                {
                    "rId": "bad-rectangle",
                    "regionBoundary": {
                        "rbShape": "rectangle",
                        "rbUnit": "relative",
                        "rbY": 0.2,
                        "rbW": 0.3,
                        "rbH": 0.4,
                    },
                }
            ]
        }
    )

    with pytest.raises(ValueError, match="rectangle requires rbX"):
        metadata.as_dict()

    assert metadata.as_diagnostic_dict()["imageRegion"][0] == {
        "rId": "bad-rectangle",
        "regionBoundary": {
            "rbShape": "rectangle",
            "rbUnit": "relative",
            "rbY": 0.2,
            "rbW": 0.3,
            "rbH": 0.4,
        },
    }
    assert metadata.image_regions.as_diagnostic_dict_list() == metadata.as_diagnostic_dict()["imageRegion"]


def test_image_region_creation_requires_dimensions_for_pixel_boundaries():
    with pytest.raises(ValueError, match="image_width and image_height are required"):
        ImageRegion(
            boundary=RectangleBoundary(unit="pixel", x=10, y=20, width=30, height=40),
        )

    deferred_region = ImageRegion(
        boundary=RectangleBoundary(unit="pixel", x=10, y=20, width=30, height=40),
        defer_dimensions=True,
    )
    region = ImageRegion(
        boundary=RectangleBoundary(unit="pixel", x=10, y=20, width=30, height=40),
        image_width=100,
        image_height=100,
    )

    with pytest.raises(ValueError, match="image_width and image_height are required"):
        _ = deferred_region.valid
    assert region.valid
    assert region.errors == []
    assert region.validate(ignore_dimensions=True) == []
    assert region.validate() == []


def test_image_region_with_dimensions_completes_deferred_pixel_region():
    region = ImageRegion(
        boundary=RectangleBoundary(unit="pixel", x=10, y=20, width=30, height=40),
        defer_dimensions=True,
    )

    completed = region.with_dimensions(image_width=100, image_height=100)

    assert completed.valid
    assert completed.image_width == 100
    assert completed.image_height == 100
    assert not completed.defer_dimensions


def test_image_region_change_unit_converts_rectangle_values():
    region = ImageRegion(
        r_id="rect",
        boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4),
    )

    changed = region.change_unit("pixel", image_width=1000, image_height=500)

    assert region.boundary.unit == "relative"
    assert isinstance(changed.boundary, RectangleBoundary)
    assert changed.r_id == "rect"
    assert changed.boundary.as_dict() == {
        "rbShape": "rectangle",
        "rbUnit": "pixel",
        "rbX": 100.0,
        "rbY": 100.0,
        "rbW": 300.0,
        "rbH": 200.0,
    }


def test_circle_change_unit_converts_radius_against_image_width():
    boundary = CircleBoundary(unit="relative", x=0.5, y=0.25, radius=0.1)

    changed = boundary.change_unit("pixel", image_width=1000, image_height=400)

    assert changed.as_dict() == {
        "rbShape": "circle",
        "rbUnit": "pixel",
        "rbX": 500.0,
        "rbY": 100.0,
        "rbRx": 100.0,
    }


def test_polygon_change_unit_converts_vertices():
    boundary = PolygonBoundary(
        unit="pixel",
        vertices=[
            Vertex(x=100, y=50, allow_malformed=True),
            Vertex(x=500, y=250, allow_malformed=True),
            Vertex(x=100, y=250, allow_malformed=True),
        ],
    )

    changed = boundary.change_unit("relative", image_width=1000, image_height=500)

    assert changed.as_dict() == {
        "rbShape": "polygon",
        "rbUnit": "relative",
        "rbVertices": [
            {"rbX": 0.1, "rbY": 0.1},
            {"rbX": 0.5, "rbY": 0.5},
            {"rbX": 0.1, "rbY": 0.5},
        ],
    }


def test_point_boundary_uses_serialized_boundary_coordinates():
    metadata = normalize_metadata(
        {
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "point",
                        "rbUnit": "relative",
                        "rbCoordinates": "[0.25,0.75]",
                    }
                }
            ]
        },
        standard=DRAFT_STANDARD,
    )

    boundary = metadata.image_regions[0].boundary

    assert isinstance(boundary, PointBoundary)
    assert metadata.valid
    assert not metadata.validation_result(standard="2025.1").valid
    assert boundary.as_dict() == {
        "rbShape": "point",
        "rbUnit": "relative",
        "rbCoordinates": "[0.25,0.75]",
    }


def test_linestring_boundary_change_unit_converts_boundary_coordinates():
    boundary = LineStringBoundary(unit="relative", coordinates=[[0.1, 0.2], [0.3, 0.4]])

    changed = boundary.change_unit("pixel", image_width=1000, image_height=500)

    assert changed.as_dict() == {
        "rbShape": "linestring",
        "rbUnit": "pixel",
        "rbCoordinates": "[[100.0,100.0],[300.0,200.0]]",
    }


def test_polygon_can_use_boundary_coordinates_for_closed_outer_boundary():
    boundary = PolygonBoundary(unit="relative", coordinates=[[[0.1, 0.1], [0.4, 0.1], [0.1, 0.4], [0.1, 0.1]]])

    assert boundary.valid
    assert boundary.as_dict() == {
        "rbShape": "polygon",
        "rbUnit": "relative",
        "rbCoordinates": "[[[0.1,0.1],[0.4,0.1],[0.1,0.4],[0.1,0.1]]]",
    }


def test_polygon_rejects_vertices_and_boundary_coordinates_together():
    result = normalize_metadata(
        {
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "polygon",
                        "rbUnit": "relative",
                        "rbVertices": [{"rbX": 0.1, "rbY": 0.1}],
                        "rbCoordinates": "[[[0.1,0.1],[0.4,0.1],[0.1,0.4],[0.1,0.1]]]",
                    }
                }
            ]
        }
    ).validation_result()

    assert ("FORBIDDEN_BOUNDARY_FIELD", "imageRegion[0].regionBoundary.rbCoordinates") in {
        (issue.code, issue.path) for issue in result.errors
    }


def test_multipolygon_boundary_requires_two_polygons():
    boundary = MultiPolygonBoundary(
        unit="relative",
        coordinates=[
            [[[0.1, 0.1], [0.4, 0.1], [0.1, 0.4], [0.1, 0.1]]],
        ],
        allow_malformed=True,
    )

    issues = boundary.validate("imageRegion[0].regionBoundary")

    assert ("INVALID_BOUNDARY_COORDINATES", "imageRegion[0].regionBoundary.rbCoordinates") in {
        (issue.code, issue.path) for issue in issues
    }


def test_polygon_boundary_coordinates_reject_inner_boundary_outside_outer():
    result = normalize_metadata(
        {
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "polygon",
                        "rbUnit": "relative",
                        "rbCoordinates": (
                            "[[[0.1,0.1],[0.7,0.1],[0.7,0.7],[0.1,0.7],[0.1,0.1]],"
                            "[[0.8,0.8],[0.9,0.8],[0.9,0.9],[0.8,0.9],[0.8,0.8]]]"
                        ),
                    }
                }
            ]
        }
    ).validation_result()

    assert ("INNER_BOUNDARY_OUTSIDE_OUTER", "imageRegion[0].regionBoundary.rbCoordinates[1]") in {
        (issue.code, issue.path) for issue in result.errors
    }


def test_polygon_boundary_coordinates_reject_inner_boundary_intersecting_outer():
    result = normalize_metadata(
        {
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "polygon",
                        "rbUnit": "relative",
                        "rbCoordinates": (
                            "[[[0.1,0.1],[0.7,0.1],[0.7,0.7],[0.1,0.7],[0.1,0.1]],"
                            "[[0.5,0.5],[0.8,0.5],[0.8,0.8],[0.5,0.8],[0.5,0.5]]]"
                        ),
                    }
                }
            ]
        }
    ).validation_result()

    assert ("INNER_BOUNDARY_INTERSECTS_OUTER", "imageRegion[0].regionBoundary.rbCoordinates[1]") in {
        (issue.code, issue.path) for issue in result.errors
    }


def test_polygon_boundary_coordinates_warn_when_inner_boundary_touches_outer():
    result = normalize_metadata(
        {
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "polygon",
                        "rbUnit": "relative",
                        "rbCoordinates": (
                            "[[[0.1,0.1],[0.7,0.1],[0.7,0.7],[0.1,0.7],[0.1,0.1]],"
                            "[[0.3,0.1],[0.5,0.1],[0.5,0.3],[0.3,0.3],[0.3,0.1]]]"
                        ),
                    }
                }
            ]
        }
    ).validation_result(standard=DRAFT_STANDARD)

    assert result.valid
    assert ("INNER_BOUNDARY_TOUCHES_OUTER", "imageRegion[0].regionBoundary.rbCoordinates[1]") in {
        (issue.code, issue.path) for issue in result.warnings
    }


def test_polygon_boundary_coordinates_reject_intersecting_inner_boundaries():
    result = normalize_metadata(
        {
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "polygon",
                        "rbUnit": "relative",
                        "rbCoordinates": (
                            "[[[0.1,0.1],[0.9,0.1],[0.9,0.9],[0.1,0.9],[0.1,0.1]],"
                            "[[0.2,0.2],[0.5,0.2],[0.5,0.5],[0.2,0.5],[0.2,0.2]],"
                            "[[0.4,0.4],[0.7,0.4],[0.7,0.7],[0.4,0.7],[0.4,0.4]]]"
                        ),
                    }
                }
            ]
        }
    ).validation_result()

    assert ("INNER_BOUNDARIES_INTERSECT", "imageRegion[0].regionBoundary.rbCoordinates[2]") in {
        (issue.code, issue.path) for issue in result.errors
    }


def test_polygon_boundary_coordinates_warn_when_inner_boundaries_touch():
    result = normalize_metadata(
        {
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "polygon",
                        "rbUnit": "relative",
                        "rbCoordinates": (
                            "[[[0.1,0.1],[0.9,0.1],[0.9,0.9],[0.1,0.9],[0.1,0.1]],"
                            "[[0.2,0.2],[0.4,0.2],[0.4,0.4],[0.2,0.4],[0.2,0.2]],"
                            "[[0.4,0.2],[0.6,0.2],[0.6,0.4],[0.4,0.4],[0.4,0.2]]]"
                        ),
                    }
                }
            ]
        }
    ).validation_result(standard=DRAFT_STANDARD)

    assert result.valid
    assert ("INNER_BOUNDARIES_TOUCH", "imageRegion[0].regionBoundary.rbCoordinates[2]") in {
        (issue.code, issue.path) for issue in result.warnings
    }


def test_multipolygon_boundary_rejects_overlapping_outer_interiors():
    boundary = MultiPolygonBoundary(
        unit="relative",
        coordinates=[
            [[[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5], [0.1, 0.1]]],
            [[[0.3, 0.3], [0.7, 0.3], [0.7, 0.7], [0.3, 0.7], [0.3, 0.3]]],
        ],
        allow_malformed=True,
    )

    issues = boundary.validate("imageRegion[0].regionBoundary")

    assert ("OVERLAPPING_MULTIPOLYGON_BOUNDARIES", "imageRegion[0].regionBoundary.rbCoordinates[1][0]") in {
        (issue.code, issue.path) for issue in issues
    }


def test_multipolygon_boundary_allows_outer_boundaries_to_share_edges():
    boundary = MultiPolygonBoundary(
        unit="relative",
        coordinates=[
            [[[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.1, 0.4], [0.1, 0.1]]],
            [[[0.4, 0.1], [0.7, 0.1], [0.7, 0.4], [0.4, 0.4], [0.4, 0.1]]],
        ],
    )

    assert boundary.valid
    assert boundary.validate("imageRegion[0].regionBoundary") == []


def test_change_unit_allow_malformed_converts_out_of_range_relative_values():
    region = ImageRegion(
        r_id="outside",
        boundary=RectangleBoundary(unit="pixel", x=120, y=20, width=30, height=10),
        image_width=100,
        image_height=50,
        allow_malformed=True,
    )

    with pytest.raises(ValueError, match="rbX must be within 0..1"):
        region.change_unit("relative", image_width=100, image_height=50)

    changed = region.change_unit("relative", image_width=100, image_height=50, allow_malformed=True)

    assert changed.as_diagnostic_dict()["regionBoundary"] == {
        "rbShape": "rectangle",
        "rbUnit": "relative",
        "rbX": 1.2,
        "rbY": 0.4,
        "rbW": 0.3,
        "rbH": 0.2,
    }
    assert any(issue.code == "RELATIVE_OUT_OF_RANGE" for issue in changed.validate("imageRegion[0]"))


def test_image_region_list_change_unit_allow_malformed_converts_out_of_range_values():
    region = ImageRegion(
        r_id="outside",
        boundary=RectangleBoundary(unit="pixel", x=120, y=20, width=30, height=10),
        image_width=100,
        image_height=50,
        allow_malformed=True,
    )
    regions = ImageRegionList([region], image_width=100, image_height=50, validate=False)

    with pytest.raises(ValueError, match="rbX must be within 0..1"):
        regions.change_unit("relative")

    changed = regions.change_unit("relative", allow_malformed=True)

    assert changed.as_diagnostic_dict_list()[0]["regionBoundary"]["rbX"] == 1.2
    assert any(issue.code == "RELATIVE_OUT_OF_RANGE" for issue in changed.validate())


def test_change_unit_allow_malformed_converts_self_intersecting_polygon():
    region = ImageRegion(
        r_id="bowtie",
        boundary=PolygonBoundary(
            unit="relative",
            vertices=[
                Vertex(x=0.1, y=0.1),
                Vertex(x=0.9, y=0.9),
                Vertex(x=0.1, y=0.9),
                Vertex(x=0.9, y=0.1),
            ],
            allow_malformed=True,
        ),
        allow_malformed=True,
    )

    with pytest.raises(ValueError, match="intersect themselves"):
        region.change_unit("pixel", image_width=100, image_height=100)

    changed = region.change_unit("pixel", image_width=100, image_height=100, allow_malformed=True)

    assert changed.as_diagnostic_dict()["regionBoundary"] == {
        "rbShape": "polygon",
        "rbUnit": "pixel",
        "rbVertices": [
            {"rbX": 10.0, "rbY": 10.0},
            {"rbX": 90.0, "rbY": 90.0},
            {"rbX": 10.0, "rbY": 90.0},
            {"rbX": 90.0, "rbY": 10.0},
        ],
    }
    assert any(issue.code == "SELF_INTERSECTING_POLYGON" for issue in changed.validate("imageRegion[0]"))


def test_image_region_list_rejects_duplicate_ids_on_add():
    region = ImageRegion(
        r_id="same",
        boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4),
    )
    regions = ImageRegionList(region)

    with pytest.raises(ValueError, match="Region identifier 'same' is used by multiple"):
        regions.add_region(region)


def test_image_region_validate_checks_known_non_boundary_fields():
    region = ImageRegion(
        r_id=123,
        name={"x-default": 7},
        r_ctype={"identifiers": ["http://cv.iptc.org/newscodes/imageregiontype/human"]},
        r_role=[{"identifiers": "not-a-list"}],
        boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4),
    )

    issues = region.validate("imageRegion[0]", image_width=None, image_height=None)
    issue_codes_by_path = {(issue.code, issue.path) for issue in issues}

    assert ("REGION_ID_NOT_STRING", "imageRegion[0].rId") in issue_codes_by_path
    assert ("REGION_NAME_VALUE_INVALID", "imageRegion[0].name.x-default") in issue_codes_by_path
    assert ("ENTITY_ARRAY_EXPECTED", "imageRegion[0].rCtype") in issue_codes_by_path
    assert ("IDENTIFIERS_NOT_ARRAY", "imageRegion[0].rRole[0].identifiers") in issue_codes_by_path


def test_image_region_from_raw_preserves_raw_extra_and_malformed_fields():
    region = ImageRegion.from_raw(
        {
            "rId": 123,
            "name": {"x-default": "Face"},
            "customField": "kept",
            "regionBoundary": {
                "rbShape": "rectangle",
                "rbUnit": "relative",
                "rbX": "0.1",
                "rbY": "0.2",
                "rbW": "0.3",
                "rbH": "0.4",
            },
        },
        allow_malformed=True,
    )

    assert isinstance(region.boundary, RectangleBoundary)
    assert region.r_id == 123
    assert region.extra["customField"] == "kept"
    assert region.as_dict()["customField"] == "kept"
    assert region.validate("imageRegion[0]", image_width=None, image_height=None)[0].code == "REGION_ID_NOT_STRING"
    with pytest.raises(TypeError):
        region.raw["rId"] = "region-1"
    with pytest.raises(TypeError):
        region.extra["customField"] = "changed"


def test_image_region_from_raw_rejects_invalid_region_by_default():
    with pytest.raises(ValueError, match=r"ImgRegion\.rId: rId must be a string\."):
        ImageRegion.from_raw(
            {
                "rId": 123,
                "regionBoundary": {
                    "rbShape": "rectangle",
                    "rbUnit": "relative",
                    "rbX": 0.1,
                    "rbY": 0.2,
                    "rbW": 0.3,
                    "rbH": 0.4,
                },
            }
        )


def test_image_region_list_from_raw_builds_and_validates_collection():
    raw = [
        {
            "rId": "same",
            "regionBoundary": {
                "rbShape": "rectangle",
                "rbUnit": "relative",
                "rbX": 0.1,
                "rbY": 0.2,
                "rbW": 0.3,
                "rbH": 0.4,
            },
        },
        {
            "rId": "same",
            "regionBoundary": {
                "rbShape": "circle",
                "rbUnit": "relative",
                "rbX": 0.5,
                "rbY": 0.5,
                "rbRx": 0.1,
            },
        },
    ]

    with pytest.raises(ValueError, match="Region identifier 'same' is used by multiple"):
        ImageRegionList.from_raw(raw)

    regions = ImageRegionList.from_raw(raw, allow_malformed=True)

    assert len(regions) == 2
    duplicate_id_issues = [issue for issue in regions.validate() if issue.code == "DUPLICATE_REGION_ID"]
    assert [issue.path for issue in duplicate_id_issues] == ["imageRegion[0].rId", "imageRegion[1].rId"]


def test_image_region_list_validation_result_reports_duplicate_id_overview():
    regions = ImageRegionList.from_raw(
        [
            {"rId": "same", "regionBoundary": {"rbShape": "rectangle", "rbUnit": "relative"}},
            {"rId": "same", "regionBoundary": {"rbShape": "circle", "rbUnit": "relative"}},
        ],
        allow_malformed=True,
    )

    result = regions.validation_result()

    duplicate_id_overviews = [issue for issue in result.overview_issues if issue.code == "DUPLICATE_REGION_ID"]
    assert len(duplicate_id_overviews) == 1
    assert duplicate_id_overviews[0].severity == "error"
    assert duplicate_id_overviews[0].paths == ("imageRegion[0].rId", "imageRegion[1].rId")
    assert duplicate_id_overviews[0].indexes == (0, 1)
    assert result.as_dict()["overviewIssues"][0]["indexes"] == [0, 1]


def test_image_region_list_reports_duplicate_boundary_warnings():
    regions = ImageRegionList.from_raw(
        [
            {
                "rId": "relative-region",
                "regionBoundary": {
                    "rbShape": "rectangle",
                    "rbUnit": "relative",
                    "rbX": 0.1,
                    "rbY": 0.2,
                    "rbW": 0.3,
                    "rbH": 0.4,
                },
            },
            {
                "rId": "pixel-region",
                "regionBoundary": {
                    "rbShape": "rectangle",
                    "rbUnit": "pixel",
                    "rbX": 100,
                    "rbY": 100,
                    "rbW": 300,
                    "rbH": 200,
                },
            },
        ],
        image_width=1000,
        image_height=500,
        allow_malformed=True,
    )

    warnings = [issue for issue in regions.validate() if issue.code == "DUPLICATE_REGION_BOUNDARY"]

    assert [issue.path for issue in warnings] == [
        "imageRegion[0].regionBoundary",
        "imageRegion[1].regionBoundary",
    ]

    result = regions.validation_result()
    duplicate_boundary_overviews = [
        issue for issue in result.overview_issues if issue.code == "DUPLICATE_REGION_BOUNDARY"
    ]
    assert len(duplicate_boundary_overviews) == 1
    assert duplicate_boundary_overviews[0].indexes == (0, 1)


def test_image_region_list_reports_duplicate_name_warnings():
    regions = ImageRegionList(
        [
            ImageRegion(
                name={"x-default": "Face"},
                boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4),
            ),
            ImageRegion(
                name={"x-default": "Face"},
                boundary=RectangleBoundary(unit="relative", x=0.2, y=0.2, width=0.3, height=0.4),
            ),
        ]
    )

    warnings = [issue for issue in regions.validate() if issue.severity == "warning"]

    assert regions.valid
    assert regions.errors == []
    assert [issue.code for issue in regions.warnings] == ["DUPLICATE_REGION_NAME", "DUPLICATE_REGION_NAME"]
    assert [issue.path for issue in warnings] == ["imageRegion[0].name", "imageRegion[1].name"]


def test_image_region_list_valid_errors_and_warnings_properties():
    regions = ImageRegionList.from_raw(
        [
            {"rId": "", "regionBoundary": {"rbShape": "rectangle", "rbUnit": "relative"}},
        ],
        allow_malformed=True,
    )

    assert not regions.valid
    assert any(issue.code == "MISSING_BOUNDARY_FIELD" for issue in regions.errors)
    assert regions.warnings[0].code == "EMPTY_REGION_ID"


def test_image_region_list_valid_requires_dimensions_for_pixel_boundaries():
    regions = ImageRegionList(
        ImageRegion(
            boundary=RectangleBoundary(unit="pixel", x=10, y=20, width=30, height=40),
            defer_dimensions=True,
        ),
        validate=False,
    )

    with pytest.raises(ValueError, match="image_width and image_height are required"):
        _ = regions.valid
    with pytest.raises(ValueError, match="image_width and image_height are required"):
        regions.validate()

    assert regions.validate(ignore_dimensions=True) == []

    regions_with_dimensions = ImageRegionList(
        ImageRegion(
            boundary=RectangleBoundary(unit="pixel", x=10, y=20, width=30, height=40),
            defer_dimensions=True,
        ),
        image_width=100,
        image_height=100,
    )

    assert regions_with_dimensions.valid
    assert regions_with_dimensions[0].image_width == 100
    assert regions_with_dimensions[0].image_height == 100


def test_image_region_list_uses_dimensions_from_child_regions():
    regions = ImageRegionList(
        ImageRegion(
            image_width=1000,
            image_height=800,
            r_id="region-1",
            boundary=RectangleBoundary(unit="pixel", x=10, y=20, width=100, height=80),
        ),
    )

    assert regions.image_width == 1000
    assert regions.image_height == 800
    assert regions.valid


def test_image_region_list_rejects_conflicting_child_dimensions():
    with pytest.raises(ValueError, match="image_width must match"):
        ImageRegionList(
            [
                ImageRegion(
                    image_width=1000,
                    image_height=800,
                    boundary=RectangleBoundary(unit="pixel", x=10, y=20, width=30, height=40),
                ),
                ImageRegion(
                    image_width=900,
                    image_height=800,
                    boundary=RectangleBoundary(unit="pixel", x=10, y=20, width=30, height=40),
                ),
            ],
            validate=False,
        )


def test_image_region_list_add_region_applies_list_dimensions():
    regions = ImageRegionList(image_width=100, image_height=100)
    region = ImageRegion(
        boundary=RectangleBoundary(unit="pixel", x=10, y=20, width=30, height=40),
        defer_dimensions=True,
    )

    regions.add_region(region)

    assert regions.valid
    assert regions[0].image_width == 100
    assert regions[0].image_height == 100


def test_image_region_list_change_unit_uses_stored_dimensions():
    regions = ImageRegionList(
        [
            ImageRegion(boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4)),
            ImageRegion(boundary=CircleBoundary(unit="relative", x=0.5, y=0.5, radius=0.1)),
        ],
        image_width=1000,
        image_height=500,
    )

    changed = regions.change_unit("pixel")

    assert changed.image_width == 1000
    assert changed.image_height == 500
    assert changed[0].boundary.as_dict()["rbX"] == 100.0
    assert changed[0].boundary.as_dict()["rbH"] == 200.0
    assert changed[1].boundary.as_dict()["rbRx"] == 100.0


def test_image_region_list_change_unit_requires_dimensions():
    regions = ImageRegionList(
        ImageRegion(boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4)),
    )

    with pytest.raises(ValueError, match="image_width and image_height are required"):
        regions.change_unit("pixel")


def test_image_region_list_rejects_invalid_non_boundary_field():
    region = ImageRegion(
        r_role={"name": "person shown"},
        boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4),
    )

    with pytest.raises(ValueError, match=r"imageRegion\[0\]\.rRole: Value must be an array"):
        ImageRegionList(region)


def test_image_region_list_checks_pixel_boundaries_when_dimensions_are_available():
    with pytest.raises(ValueError, match="Rectangle exceeds image width"):
        ImageRegionList(
            ImageRegion(
                boundary=RectangleBoundary(unit="pixel", x=90, y=10, width=20, height=20),
                defer_dimensions=True,
            ),
            image_width=100,
            image_height=100,
        )


def test_geometry_with_methods_return_validated_copies():
    boundary = RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4)

    changed = boundary.with_width(0.4)

    assert boundary.width == 0.3
    assert changed.width == 0.4
    assert changed.valid
    assert changed.as_dict()["rbW"] == 0.4


def test_geometry_with_methods_reject_invalid_copies():
    boundary = RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4)

    with pytest.raises(ValueError, match=r"regionBoundary\.rbW: Relative rectangle exceeds image width\."):
        boundary.with_width(0.95)

    assert boundary.width == 0.3
    assert boundary.valid


def test_malformed_raw_geometry_can_be_repaired_with_copy_method():
    boundary = CircleBoundary.from_raw(
        {
            "rbShape": "circle",
            "rbUnit": "relative",
            "rbX": "0.4",
            "rbY": 0.7,
        },
        allow_malformed=True,
    )

    repaired = boundary.with_radius(0.1)

    assert not boundary.valid
    assert repaired.valid
    assert repaired.radius == 0.1
    assert "rbRx" not in repaired.raw_dict()
    assert repaired.as_dict()["rbRx"] == 0.1


def test_polygon_and_vertex_with_methods_return_validated_copies():
    vertex = Vertex(x=0.1, y=0.2)
    changed_vertex = vertex.with_position(x=0.3)
    other_vertices = [Vertex(x=0.6, y=0.2), Vertex(x=0.1, y=0.6)]
    boundary = PolygonBoundary(unit="relative", vertices=[vertex, *other_vertices])
    changed_boundary = boundary.with_vertices([changed_vertex, *other_vertices])

    assert vertex.x == 0.1
    assert changed_vertex.x == 0.3
    assert boundary.vertices[0].x == 0.1
    assert changed_boundary.vertices[0].x == 0.3
    assert changed_boundary.valid


def test_direct_rectangle_creation_rejects_invalid_relative_coordinate():
    with pytest.raises(ValueError, match=r"regionBoundary\.rbX: rbX must be within 0\.\.1\."):
        RectangleBoundary(
            unit="relative",
            x=1.1,
            y=0.2,
            width=0.3,
            height=0.4,
        )


def test_direct_geometry_creation_rejects_invalid_values():
    with pytest.raises(ValueError, match=r"regionBoundary\.rbRx: rbRx must be greater than zero\."):
        CircleBoundary(unit="relative", x=0.5, y=0.5, radius=0)

    with pytest.raises(ValueError, match=r"regionBoundary\.rbRx: Circle extends before the image left edge\."):
        CircleBoundary(unit="pixel", x=5, y=20, radius=10)

    with pytest.raises(ValueError, match=r"regionBoundary\.rbVertices\[0\]\.rbX: rbX must be within 0\.\.1\."):
        PolygonBoundary(unit="relative", vertices=[Vertex(x=1.1, y=0.2)])


def test_from_dict_rejects_invalid_geometry_values():
    with pytest.raises(ValueError, match="rbX must be a number."):
        RectangleBoundary.from_dict(
            {
                "rbShape": "rectangle",
                "rbUnit": "relative",
                "rbX": "1.1",
                "rbY": 0.2,
                "rbW": 0.3,
                "rbH": 0.4,
            }
        )


def test_from_raw_keeps_invalid_geometry_for_validation_later():
    boundary = RectangleBoundary.from_raw(
        {
            "rbShape": "rectangle",
            "rbUnit": "relative",
            "rbX": 1.1,
            "rbY": 0.2,
            "rbW": 0.3,
            "rbH": 0.4,
        },
        allow_malformed=True,
    )

    issues = boundary.validate("imageRegion[0].regionBoundary", image_width=None, image_height=None)

    assert not boundary.valid
    assert boundary.errors
    assert issues[0].code == "RELATIVE_OUT_OF_RANGE"
    assert issues[0].path == "imageRegion[0].regionBoundary.rbX"


def test_geometry_validate_can_use_default_class_paths():
    circle = CircleBoundary.from_raw(
        {
            "rbShape": "circle",
            "rbUnit": "relative",
            "rbY": 0.7,
        },
        allow_malformed=True,
    )
    rectangle = RectangleBoundary.from_raw(
        {
            "rbShape": "rectangle",
            "rbUnit": "relative",
            "rbY": 0.2,
            "rbW": 0.3,
            "rbH": 0.4,
        },
        allow_malformed=True,
    )
    polygon = PolygonBoundary(
        unit="relative",
        vertices=[Vertex(x=1.1, y=0.2, allow_malformed=True)],
        allow_malformed=True,
    )

    assert ("MISSING_BOUNDARY_FIELD", "Circle.rbX") in {(issue.code, issue.path) for issue in circle.validate()}
    assert ("MISSING_BOUNDARY_FIELD", "Rectangle.rbX") in {(issue.code, issue.path) for issue in rectangle.validate()}
    assert ("RELATIVE_OUT_OF_RANGE", "Polygon.rbVertices[0].rbX") in {
        (issue.code, issue.path) for issue in polygon.validate()
    }


def test_pixel_geometry_validate_requires_dimensions_unless_ignored():
    rectangle = RectangleBoundary(unit="pixel", x=10, y=20, width=30, height=40)
    circle = CircleBoundary(unit="pixel", x=20, y=20, radius=5)

    assert ("MISSING_IMAGE_DIMENSION", "Rectangle.imageWidth") in {
        (issue.code, issue.path) for issue in rectangle.validate()
    }
    assert ("MISSING_IMAGE_DIMENSION", "Circle.imageHeight") in {(issue.code, issue.path) for issue in circle.validate()}
    assert rectangle.validate(ignore_dimensions=True) == []
    assert circle.validate(ignore_dimensions=True) == []
    assert any(issue.code == "BOUNDARY_EXCEEDS_IMAGE" for issue in rectangle.validate(image_width=20, image_height=100))


def test_from_raw_rejects_malformed_geometry_by_default():
    with pytest.raises(ValueError, match=r"regionBoundary\.rbRx: circle requires rbRx\."):
        CircleBoundary.from_raw(
            {
                "rbShape": "circle",
                "rbUnit": "relative",
                "rbX": 0.4,
                "rbY": 0.7,
            }
        )


def test_from_raw_keeps_raw_and_extra_mappings_immutable():
    boundary = CircleBoundary.from_raw(
        {
            "rbShape": "circle",
            "rbUnit": "relative",
            "rbX": 0.4,
            "rbY": 0.7,
            "rbRx": 0.2,
            "rbW": 4,
        },
        allow_malformed=True,
    )

    with pytest.raises(TypeError):
        boundary.raw["rbX"] = 0.5
    with pytest.raises(TypeError):
        boundary.extra["rbW"] = 5


def test_from_raw_coerces_numeric_strings_without_changing_raw_dict():
    boundary = CircleBoundary.from_raw(
        {
            "rbShape": "circle",
            "rbUnit": "relative",
            "rbX": "0.4",
            "rbY": 0.7,
            "rbW": 4,
        },
        allow_malformed=True,
    )

    assert not boundary.valid
    assert boundary.x == 0.4
    assert boundary.y == 0.7
    assert boundary.radius is None
    assert boundary._dict_full() == {
        "rbShape": "circle",
        "rbUnit": "relative",
        "rbX": 0.4,
        "rbY": 0.7,
        "rbRx": None,
        "rbW": 4,
    }
    with pytest.raises(ValueError, match=r"regionBoundary\.rbRx: circle requires rbRx\."):
        boundary.as_dict()
    assert boundary.raw_dict() == {
        "rbShape": "circle",
        "rbUnit": "relative",
        "rbX": "0.4",
        "rbY": 0.7,
        "rbW": 4,
    }

    issues = boundary.validate("imageRegion[0].regionBoundary", image_width=None, image_height=None)
    issue_codes_by_path = {(issue.code, issue.path) for issue in issues}

    assert ("MISSING_BOUNDARY_FIELD", "imageRegion[0].regionBoundary.rbRx") in issue_codes_by_path
    assert ("FORBIDDEN_BOUNDARY_FIELD", "imageRegion[0].regionBoundary.rbW") in issue_codes_by_path


def test_from_raw_reports_values_that_cannot_be_converted_to_numbers():
    boundary = CircleBoundary.from_raw(
        {
            "rbShape": "circle",
            "rbUnit": "relative",
            "rbX": "not-a-number",
            "rbY": 0.7,
            "rbRx": 0.1,
        },
        allow_malformed=True,
    )

    assert not boundary.valid
    assert math.isnan(boundary.x)
    assert boundary._dict_full()["rbX"] is None
    assert boundary._dict_existing()["rbX"] == "not-a-number"
    with pytest.raises(ValueError, match=r"regionBoundary\.rbX: rbX must be a number\."):
        boundary.as_dict()
    assert boundary.raw_dict()["rbX"] == "not-a-number"

    issues = boundary.validate("imageRegion[0].regionBoundary", image_width=None, image_height=None)
    issue_codes_by_path = {(issue.code, issue.path) for issue in issues}

    assert ("INVALID_NUMBER", "imageRegion[0].regionBoundary.rbX") in issue_codes_by_path


def test_rejects_missing_region_boundary():
    result = normalize_metadata({"imageRegion": [{"rId": "region-1"}]}).validation_result()

    assert not result.valid
    assert result.errors[0].code == "MISSING_REGION_BOUNDARY"


def test_rejects_shape_specific_fields_from_other_shape():
    result = normalize_metadata(
        {
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "circle",
                        "rbUnit": "relative",
                        "rbX": 0.5,
                        "rbY": 0.5,
                        "rbRx": 0.2,
                        "rbW": 0.4,
                    }
                }
            ]
        }
    ).validation_result()

    assert not result.valid
    assert any(issue.code == "FORBIDDEN_BOUNDARY_FIELD" for issue in result.errors)


def test_missing_boundary_fields_do_not_also_report_invalid_number():
    result = normalize_metadata(
        {
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "circle",
                        "rbUnit": "relative",
                        "rbVertices": [
                            {"rbX": "0.32", "rbY": "0.1"},
                            {"rbX": "0.59", "rbY": "0.27"},
                        ],
                    }
                }
            ]
        }
    ).validation_result()

    issue_codes_by_path = {(issue.code, issue.path) for issue in result.errors}

    assert ("MISSING_BOUNDARY_FIELD", "imageRegion[0].regionBoundary.rbRx") in issue_codes_by_path
    assert ("MISSING_BOUNDARY_FIELD", "imageRegion[0].regionBoundary.rbX") in issue_codes_by_path
    assert ("MISSING_BOUNDARY_FIELD", "imageRegion[0].regionBoundary.rbY") in issue_codes_by_path
    assert ("FORBIDDEN_BOUNDARY_FIELD", "imageRegion[0].regionBoundary.rbVertices") in issue_codes_by_path
    assert ("INVALID_NUMBER", "imageRegion[0].regionBoundary.rbRx") not in issue_codes_by_path
    assert ("INVALID_NUMBER", "imageRegion[0].regionBoundary.rbX") not in issue_codes_by_path
    assert ("INVALID_NUMBER", "imageRegion[0].regionBoundary.rbY") not in issue_codes_by_path


def test_rejects_unknown_boundary_fields():
    result = normalize_metadata(
        {
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "rectangle",
                        "rbUnit": "relative",
                        "rbE": "0.12",
                        "rbY": "0.76",
                        "rbW": "0.2",
                        "rbH": "0.2",
                    }
                }
            ]
        }
    ).validation_result()

    issue_codes_by_path = {(issue.code, issue.path) for issue in result.errors}

    assert ("UNKNOWN_BOUNDARY_FIELD", "imageRegion[0].regionBoundary.rbE") in issue_codes_by_path
    assert ("MISSING_BOUNDARY_FIELD", "imageRegion[0].regionBoundary.rbX") in issue_codes_by_path


def test_rejects_self_intersecting_polygon():
    result = normalize_metadata(
        {
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "polygon",
                        "rbUnit": "relative",
                        "rbVertices": [
                            {"rbX": 0.0, "rbY": 0.0},
                            {"rbX": 1.0, "rbY": 1.0},
                            {"rbX": 0.0, "rbY": 1.0},
                            {"rbX": 1.0, "rbY": 0.0},
                        ],
                    }
                }
            ]
        }
    ).validation_result()

    assert (
        "SELF_INTERSECTING_POLYGON",
        "imageRegion[0].regionBoundary.rbVertices",
    ) in {(issue.code, issue.path) for issue in result.errors}


def test_rejects_unknown_polygon_vertex_fields():
    result = normalize_metadata(
        {
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "polygon",
                        "rbUnit": "relative",
                        "rbVertices": [
                            {"rbE": "0.12", "rbY": "0.76"},
                        ],
                    }
                }
            ]
        }
    ).validation_result()

    issue_codes_by_path = {(issue.code, issue.path) for issue in result.errors}

    assert ("UNKNOWN_VERTEX_FIELD", "imageRegion[0].regionBoundary.rbVertices[0].rbE") in issue_codes_by_path
    assert ("MISSING_VERTEX_COORDINATE", "imageRegion[0].regionBoundary.rbVertices[0].rbX") in issue_codes_by_path


def test_rejects_relative_rectangle_outside_image():
    result = normalize_metadata(
        {
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "rectangle",
                        "rbUnit": "relative",
                        "rbX": 0.8,
                        "rbY": 0.2,
                        "rbW": 0.3,
                        "rbH": 0.2,
                    }
                }
            ]
        }
    ).validation_result()

    assert not result.valid
    assert any(issue.code == "BOUNDARY_EXCEEDS_IMAGE" for issue in result.errors)


def test_pixel_circle_min_bounds_do_not_require_image_dimensions():
    metadata = normalize_metadata(
        {
            "imageRegion": [
                {
                    "regionBoundary": {
                        "rbShape": "circle",
                        "rbUnit": "pixel",
                        "rbX": 5,
                        "rbY": 5,
                        "rbRx": 10,
                    }
                }
            ]
        }
    )

    with pytest.raises(ValueError, match="image_width and image_height are required"):
        metadata.validation_result()

    result = metadata.validation_result(ignore_dimensions=True)
    messages = [issue.message for issue in result.errors if issue.code == "BOUNDARY_EXCEEDS_IMAGE"]

    assert "Circle extends before the image left edge." in messages
    assert "Circle extends before the image top edge." in messages


def test_duplicate_ids_are_errors_and_duplicate_names_are_warnings():
    result = normalize_metadata(
        {
            "imageRegion": [
                {
                    "rId": "same",
                    "name": {"x-default": "Face"},
                    "regionBoundary": {
                        "rbShape": "polygon",
                        "rbUnit": "relative",
                        "rbVertices": [{"rbX": 0.1, "rbY": 0.1}],
                    },
                },
                {
                    "rId": "same",
                    "name": {"x-default": "Face"},
                    "regionBoundary": {
                        "rbShape": "polygon",
                        "rbUnit": "relative",
                        "rbVertices": [{"rbX": 0.2, "rbY": 0.2}],
                    },
                },
            ]
        }
    ).validation_result()

    assert any(issue.code == "DUPLICATE_REGION_ID" for issue in result.errors)
    assert any(issue.code == "DUPLICATE_REGION_NAME" for issue in result.warnings)


def test_normalized_metadata_reports_known_region_field_errors():
    result = normalize_metadata(
        {
            "imageRegion": [
                {
                    "rId": 123,
                    "name": ["Face"],
                    "regionBoundary": {
                        "rbShape": "rectangle",
                        "rbUnit": "relative",
                        "rbX": 0.1,
                        "rbY": 0.2,
                        "rbW": 0.3,
                        "rbH": 0.4,
                    },
                }
            ]
        }
    ).validation_result()

    issue_codes_by_path = {(issue.code, issue.path) for issue in result.errors}

    assert ("REGION_ID_NOT_STRING", "imageRegion[0].rId") in issue_codes_by_path
    assert ("REGION_NAME_INVALID", "imageRegion[0].name") in issue_codes_by_path
