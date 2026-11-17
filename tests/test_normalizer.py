"""Tests for metadata normalization from structured and flat tool outputs."""

from iptc_iris import normalize_metadata, parse_metadata_text
from iptc_iris.geometry import CircleBoundary, PointBoundary, PolygonBoundary, RectangleBoundary


def test_normalizes_exiftool_structured_json():
    metadata = normalize_metadata(
        {
            "SourceFile": "photo.jpg",
            "ExifTool:ImageWidth": 1000,
            "ExifTool:ImageHeight": 500,
            "XMP-iptcExt:ImageRegion": [
                {
                    "RegionBoundary": {
                        "RbShape": "rectangle",
                        "RbUnit": "pixel",
                        "RbX": 10,
                        "RbY": 20,
                        "RbW": 300,
                        "RbH": 100,
                    },
                    "RId": "face-1",
                }
            ],
        }
    )

    assert metadata.image_width == 1000
    assert metadata.image_height == 500
    region = metadata.image_regions[0]
    assert isinstance(region.boundary, RectangleBoundary)
    assert region.boundary.as_dict()["rbShape"] == "rectangle"
    assert region.r_id == "face-1"


def test_parses_exiftool_json_text_with_exiftool_source_format():
    metadata = parse_metadata_text(
        """
        [{
          "SourceFile": "photo.jpg",
          "File:ImageWidth": 1000,
          "File:ImageHeight": 500,
          "XMP-iptcExt:ImageRegion": [{
            "Name": "Speaker",
            "RegionBoundary": {
              "RbShape": "Polygon",
              "RbUnit": "Relative",
              "RbVertices": [{"RbX": 0.146, "RbY": 0.29}, {"RbX": 0.246, "RbY": 0.29}, {"RbX": 0.146, "RbY": 0.39}]
            },
            "RCtype": [{
              "Name": "human",
              "Identifier": ["http://cv.iptc.org/newscodes/imageregiontype/human"]
            }],
            "RId": "face-1"
          }]
        }]
        """,
        source_format="exiftool-json",
    )

    boundary = metadata.image_regions[0].boundary
    region = metadata.image_regions[0]

    assert metadata.image_width == 1000
    assert metadata.image_height == 500
    assert region.name == {"x-default": "Speaker"}
    assert region.r_ctype == [
        {
            "name": {"x-default": "human"},
            "identifiers": ["http://cv.iptc.org/newscodes/imageregiontype/human"],
        }
    ]
    assert isinstance(boundary, PolygonBoundary)
    assert boundary.as_dict() == {
        "rbShape": "polygon",
        "rbUnit": "relative",
        "rbVertices": [{"rbX": 0.146, "rbY": 0.29}, {"rbX": 0.246, "rbY": 0.29}, {"rbX": 0.146, "rbY": 0.39}],
    }


def test_normalizes_exiftool_region_name_language_suffixes():
    metadata = normalize_metadata(
        {
            "XMP-iptcExt:ImageRegion": [
                {
                    "Name": "Speaker",
                    "Name-de": "Sprecher",
                    "Name-x-default": "Speaker default",
                    "RegionBoundary": {
                        "RbShape": "Rectangle",
                        "RbUnit": "Relative",
                        "RbX": 0.1,
                        "RbY": 0.2,
                        "RbW": 0.3,
                        "RbH": 0.4,
                    },
                }
            ]
        }
    )

    region = metadata.image_regions[0]

    assert region.name == {"x-default": "Speaker default", "de": "Sprecher"}
    assert "Name-de" not in region.extra
    assert "Name-x-default" not in region.extra


def test_normalizes_exiv2_style_flat_keys():
    metadata = normalize_metadata(
        {
            "Xmp.iptcExt.ImageRegion[1]/RegionBoundary/rbShape": "circle",
            "Xmp.iptcExt.ImageRegion[1]/RegionBoundary/rbUnit": "relative",
            "Xmp.iptcExt.ImageRegion[1]/RegionBoundary/rbX": "0.5",
            "Xmp.iptcExt.ImageRegion[1]/RegionBoundary/rbY": "0.5",
            "Xmp.iptcExt.ImageRegion[1]/RegionBoundary/rbRx": "0.2",
        }
    )

    boundary = metadata.image_regions[0].boundary
    assert isinstance(boundary, CircleBoundary)
    assert boundary.as_dict() == {
        "rbShape": "circle",
        "rbUnit": "relative",
        "rbX": 0.5,
        "rbY": 0.5,
        "rbRx": 0.2,
    }
    assert boundary.raw_dict() == {
        "rbShape": "circle",
        "rbUnit": "relative",
        "rbX": "0.5",
        "rbY": "0.5",
        "rbRx": "0.2",
    }


def test_normalizes_boundary_coordinates_shape_from_exiftool_json():
    metadata = normalize_metadata(
        {
            "XMP-iptcExt:ImageRegion": [
                {
                    "RegionBoundary": {
                        "RbShape": "Point",
                        "RbUnit": "Relative",
                        "RbCoordinates": "[0.25,0.75]",
                    }
                }
            ],
        }
    )

    boundary = metadata.image_regions[0].boundary

    assert isinstance(boundary, PointBoundary)
    assert boundary.as_dict() == {
        "rbShape": "point",
        "rbUnit": "relative",
        "rbCoordinates": "[0.25,0.75]",
    }


def test_parses_exiv2_text_lines():
    metadata = parse_metadata_text(
        """
        Xmp.iptcExt.ImageRegion[1]/RegionBoundary/rbShape XmpText 9 rectangle
        Xmp.iptcExt.ImageRegion[1]/RegionBoundary/rbUnit XmpText 5 pixel
        Xmp.iptcExt.ImageRegion[1]/RegionBoundary/rbX XmpText 2 10
        Xmp.iptcExt.ImageRegion[1]/RegionBoundary/rbY XmpText 2 20
        Xmp.iptcExt.ImageRegion[1]/RegionBoundary/rbW XmpText 3 200
        Xmp.iptcExt.ImageRegion[1]/RegionBoundary/rbH XmpText 3 150
        """,
        source_format="exiv2",
    )

    assert metadata.image_regions[0].boundary.as_dict()["rbW"] == 200


def test_parses_exiv2_repeated_region_name_lang_alt_lines():
    metadata = parse_metadata_text(
        """
        Xmp.iptcExt.ImageRegion XmpText 10 type="Bag"
        Xmp.iptcExt.ImageRegion[1] XmpText 13 type="Struct"
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:Name LangAlt 1 lang="x-default" Speaker
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:Name LangAlt 1 lang="de" Sprecher
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary XmpText 13 type="Struct"
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbShape XmpText 9 rectangle
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbUnit XmpText 8 relative
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbX XmpText 3 0.1
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbY XmpText 3 0.2
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbW XmpText 3 0.3
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbH XmpText 3 0.4
        """,
        source_format="exiv2",
    )

    assert metadata.image_regions[0].name == {"x-default": "Speaker", "de": "Sprecher"}


def test_parses_exiv2_joined_region_name_lang_alt_line():
    metadata = parse_metadata_text(
        """
        Xmp.iptcExt.ImageRegion XmpText 10 type="Bag"
        Xmp.iptcExt.ImageRegion[1] XmpText 13 type="Struct"
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:Name LangAlt 2 lang="x-default" Speaker, lang="de" Sprecher
        """,
        source_format="exiv2",
    )

    assert metadata.image_regions[0].name == {"x-default": "Speaker", "de": "Sprecher"}


def test_parses_exiv2_nested_container_marker_lines():
    metadata = parse_metadata_text(
        """
        Xmp.iptcExt.ImageRegion XmpText 10 type="Bag"
        Xmp.iptcExt.ImageRegion[1] XmpText 13 type="Struct"
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:Name LangAlt 1 lang="x-default" Speaker
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary XmpText 13 type="Struct"
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbShape XmpText 7 polygon
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbUnit XmpText 8 relative
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbVertices XmpText 10 type="Seq"
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbVertices[1] XmpText 13 type="Struct"
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbVertices[1]/Iptc4xmpExt:rbX XmpText 5 0.146
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbVertices[1]/Iptc4xmpExt:rbY XmpText 4 0.29
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbVertices[2] XmpText 13 type="Struct"
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbVertices[2]/Iptc4xmpExt:rbX XmpText 5 0.246
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbVertices[2]/Iptc4xmpExt:rbY XmpText 4 0.29
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbVertices[3] XmpText 13 type="Struct"
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbVertices[3]/Iptc4xmpExt:rbX XmpText 5 0.146
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbVertices[3]/Iptc4xmpExt:rbY XmpText 4 0.39
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:rCtype XmpText 10 type="Bag"
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:rCtype[1] XmpText 13 type="Struct"
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:rCtype[1]/Iptc4xmpExt:Name LangAlt 1 lang="x-default" human
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:rCtype[1]/xmp:Identifier XmpBag 1 http://cv.iptc.org/newscodes/imageregiontype/human
        """,
        source_format="exiv2",
    )

    region = metadata.image_regions[0]

    assert region.name == {"x-default": "Speaker"}
    assert region.r_ctype == [
        {
            "name": {"x-default": "human"},
            "identifiers": ["http://cv.iptc.org/newscodes/imageregiontype/human"],
        }
    ]
    assert region.boundary.as_dict() == {
        "rbShape": "polygon",
        "rbUnit": "relative",
        "rbVertices": [{"rbX": 0.146, "rbY": 0.29}, {"rbX": 0.246, "rbY": 0.29}, {"rbX": 0.146, "rbY": 0.39}],
    }


def test_parses_exiv2_region_extra_metadata_to_stable_keys():
    metadata = parse_metadata_text(
        """
        Xmp.iptcExt.ImageRegion XmpText 10 type="Bag"
        Xmp.iptcExt.ImageRegion[1] XmpText 13 type="Struct"
        Xmp.iptcExt.ImageRegion[1]/dc:description LangAlt 1 lang="x-default" Description
        Xmp.iptcExt.ImageRegion[1]/dc:description LangAlt 1 lang="de" Beschreibung
        Xmp.iptcExt.ImageRegion[1]/dc:title LangAlt 1 lang="x-default" Title
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:Contributor XmpText 10 type="Bag"
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:Contributor[1] XmpText 13 type="Struct"
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:Contributor[1]/Iptc4xmpExt:Name XmpText 11 Person Name
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:Contributor[1]/xmp:Identifier XmpBag 1 https://example.org/person/1
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:Contributor[1]/Iptc4xmpExt:Role XmpBag 1 https://example.org/role/describer
        Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:PersonInImage XmpBag 1 Person Name
        """,
        source_format="exiv2",
    )

    region = metadata.as_dict()["imageRegion"][0]

    assert region["XMP-dc:Description"] == {"x-default": "Description", "de": "Beschreibung"}
    assert region["XMP-dc:Title"] == {"x-default": "Title"}
    assert region["XMP-iptcExt:Contributor"] == [
        {
            "name": "Person Name",
            "identifiers": ["https://example.org/person/1"],
            "role": ["https://example.org/role/describer"],
        }
    ]
    assert region["XMP-iptcExt:PersonInImage"] == ["Person Name"]


def test_preserves_utf8_text_from_tool_output():
    metadata = parse_metadata_text(
        """
        [{
          "XMP-iptcExt:ImageRegion": [{
            "OrganisationInImageName": ["TT Nyhetsbyrån AB (Swedish Newsageny)"],
            "RegionBoundary": {
              "RbShape": "Rectangle",
              "RbUnit": "Relative",
              "RbX": 0.1,
              "RbY": 0.2,
              "RbW": 0.3,
              "RbH": 0.4
            }
          }]
        }]
        """,
        source_format="exiftool-json",
    )

    assert metadata.image_regions[0].extra["XMP-iptcExt:OrganisationInImageName"] == [
        "TT Nyhetsbyrån AB (Swedish Newsageny)"
    ]


def test_region_aliases_do_not_apply_to_unrelated_top_level_metadata():
    metadata = normalize_metadata(
        {
            "File:ImageWidth": 1000,
            "PersonShown": "top-level person",
            "XMP-iptcExt:ImageRegion": [
                {
                    "PersonShown": "region person",
                    "RegionBoundary": {
                        "RbShape": "Rectangle",
                        "RbUnit": "Relative",
                        "RbX": 0.1,
                        "RbY": 0.2,
                        "RbW": 0.3,
                        "RbH": 0.4,
                    },
                }
            ],
        }
    )

    assert metadata.image_width == 1000
    assert metadata.raw["PersonShown"] == "top-level person"
    assert metadata.image_regions[0].extra["PersonShown"] == "region person"
