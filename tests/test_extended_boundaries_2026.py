"""Tests for the IPTC 2026.1 Extended Image Region Boundaries rules.

Covers Multiboundary Part Details, Image Region Depth Order, duplicate parts in
multipoint/multilinestring, and multipolygon interior overlap with holes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from iptc_iris import (
    DRAFT_STANDARD,
    ImageRegionList,
    MetadataToolWarning,
    MultiboundaryPart,
    format_exiftool_image_region_arg,
    normalize_metadata,
    parse_xmp,
)
from iptc_iris.geometry import MultiPointBoundary, MultiPolygonBoundary
from iptc_iris.io import EXIFTOOL_CONFIG, _parse_key_value_lines, run_metadata_tool, write_image_regions


def square(x: float, y: float, size: float) -> list[list[float]]:
    return [[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]


def codes(boundary: dict, **list_kwargs) -> list[str]:
    regions = ImageRegionList.from_raw(
        [{"rId": "r1", "regionBoundary": boundary}],
        allow_malformed=True,
        validate=False,
        **list_kwargs,
        standard=DRAFT_STANDARD,
    )
    return [issue.code for issue in regions.validate()]


def multipoint(details=None, points=None) -> dict:
    boundary = {
        "rbShape": "multipoint",
        "rbUnit": "relative",
        "rbCoordinates": json.dumps(points or [[0.1, 0.1], [0.2, 0.2]]),
    }
    if details is not None:
        boundary["rbMbPartDetails"] = details
    return boundary


def multipolygon(polygons) -> dict:
    return {"rbShape": "multipolygon", "rbUnit": "relative", "rbCoordinates": json.dumps(polygons)}


def point_region(r_id: str, x: float) -> dict:
    return {"rId": r_id, "regionBoundary": {"rbShape": "point", "rbUnit": "relative", "rbCoordinates": f"[{x},0.5]"}}


# --- duplicate parts -------------------------------------------------------------------------------------------------


def test_multipoint_rejects_duplicate_points():
    assert codes(multipoint(points=[[0.1, 0.1], [0.2, 0.2], [0.1, 0.1]])) == ["DUPLICATE_MULTIPOINT_POINT"]


@pytest.mark.parametrize(
    "second",
    [[[0.1, 0.1], [0.2, 0.2]], [[0.2, 0.2], [0.1, 0.1]]],
    ids=["same-direction", "reversed"],
)
def test_multilinestring_rejects_duplicate_linestrings(second):
    boundary = {
        "rbShape": "multilinestring",
        "rbUnit": "relative",
        "rbCoordinates": json.dumps([[[0.1, 0.1], [0.2, 0.2]], second]),
    }
    assert codes(boundary) == ["DUPLICATE_LINESTRING"]


# --- multipolygon interior overlap -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("polygons", "expected"),
    [
        ([[square(0.1, 0.1, 0.8), square(0.3, 0.3, 0.4)], [square(0.4, 0.4, 0.2)]], []),
        ([[square(0.1, 0.1, 0.2)], [square(0.3, 0.1, 0.2)]], []),
        ([[square(0.1, 0.1, 0.8)], [square(0.4, 0.4, 0.2)]], ["OVERLAPPING_MULTIPOLYGON_BOUNDARIES"]),
        (
            [[square(0.1, 0.1, 0.8), square(0.4, 0.4, 0.2)], [square(0.3, 0.3, 0.4)]],
            ["OVERLAPPING_MULTIPOLYGON_BOUNDARIES"],
        ),
        ([[square(0.1, 0.1, 0.2)], [square(0.1, 0.1, 0.2)]], ["OVERLAPPING_MULTIPOLYGON_BOUNDARIES"]),
    ],
    ids=["inside-hole", "shared-edge", "nested-no-hole", "larger-than-hole", "identical"],
)
def test_multipolygon_interior_overlap_respects_holes(polygons, expected):
    assert codes(multipolygon(polygons)) == expected


# --- Multiboundary Part Details --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("details", "expected"),
    [
        ([{"rbMbPdPartIndex": 1, "rbMbPdPartName": "right"}], []),
        ([{"rbMbPdPartName": "no index"}], ["MISSING_PART_INDEX"]),
        ([{"rbMbPdPartIndex": -1}], ["INVALID_PART_INDEX"]),
        ([{"rbMbPdPartIndex": True}], ["INVALID_PART_INDEX"]),
        ([{"rbMbPdPartIndex": 2}], ["PART_INDEX_OUT_OF_RANGE"]),
        ([{"rbMbPdPartIndex": 0}, {"rbMbPdPartIndex": 0}], ["DUPLICATE_PART_INDEX"]),
        ("not an array", ["INVALID_PART_DETAILS"]),
        (["not an object"], ["INVALID_PART_DETAILS"]),
        ([{"rbMbPdPartIndex": 0, "rbMbPdPartName": 3}], ["INVALID_PART_DETAIL_VALUE"]),
        ([{"rbMbPdPartIndex": 0, "extra": "x"}], ["UNKNOWN_PART_DETAIL_FIELD"]),
    ],
    ids=[
        "valid",
        "missing-index",
        "negative-index",
        "bool-index",
        "out-of-range",
        "duplicate-index",
        "not-array",
        "entry-not-object",
        "name-not-string",
        "unknown-field",
    ],
)
def test_part_details_validation(details, expected):
    assert codes(multipoint(details)) == expected


def test_part_details_are_forbidden_on_single_shapes():
    boundary = {
        "rbShape": "linestring",
        "rbUnit": "relative",
        "rbCoordinates": "[[0.1,0.1],[0.2,0.2]]",
        "rbMbPartDetails": [{"rbMbPdPartIndex": 0}],
    }
    assert "FORBIDDEN_BOUNDARY_FIELD" in codes(boundary)


def test_part_index_text_from_metadata_tools_is_normalized_to_integer():
    metadata = normalize_metadata(
        {"imageRegion": [{"rId": "r1", "regionBoundary": multipoint([{"RbMbPdPartIndex": "1"}])}]},
        standard=DRAFT_STANDARD,
    )

    details = metadata.as_dict()["imageRegion"][0]["regionBoundary"]["rbMbPartDetails"]
    assert details == [{"rbMbPdPartIndex": 1}]
    assert metadata.valid


def test_parts_pair_coordinates_with_details_by_part_index():
    boundary = MultiPointBoundary(
        unit="relative",
        coordinates=[[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]],
        part_details=[
            {"rbMbPdPartIndex": 2, "rbMbPdPartName": "third"},
            {"rbMbPdPartIndex": 0, "rbMbPdPartId": "first"},
        ],
    )

    parts = boundary.parts()

    assert [part.coordinates for part in parts] == [[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]]
    assert [(part.part_id, part.part_name) for part in parts] == [("first", None), (None, None), (None, "third")]


def test_with_parts_renumbers_part_index_after_remove_and_reorder():
    boundary = MultiPolygonBoundary(
        unit="relative",
        coordinates=[[square(0.1, 0.1, 0.1)], [square(0.5, 0.5, 0.1)], [square(0.7, 0.1, 0.1)]],
        part_details=[
            {"rbMbPdPartIndex": 0, "rbMbPdPartId": "first"},
            {"rbMbPdPartIndex": 2, "rbMbPdPartName": "third", "rbMbPdPartDescription": "right"},
        ],
    )
    first, second, third = boundary.parts()

    updated = boundary.with_parts([third, second])

    assert updated.coordinates == [[square(0.7, 0.1, 0.1)], [square(0.5, 0.5, 0.1)]]
    assert updated.part_details == [{"rbMbPdPartIndex": 0, "rbMbPdPartName": "third", "rbMbPdPartDescription": "right"}]
    assert updated.valid


def test_with_parts_without_details_drops_part_details():
    boundary = MultiPointBoundary(unit="relative", coordinates=[[0.1, 0.1], [0.2, 0.2]])

    updated = boundary.with_parts([MultiboundaryPart([0.3, 0.3]), MultiboundaryPart([0.4, 0.4])])

    assert updated.part_details is None
    assert updated.coordinates == [[0.3, 0.3], [0.4, 0.4]]


# --- Image Region Depth Order ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("depth_order", "expected"),
    [
        (["b", "a"], []),
        (["a"], []),
        (["a", "a"], ["DUPLICATE_DEPTH_ORDER_ID"]),
        (["a", "missing"], ["UNKNOWN_DEPTH_ORDER_ID"]),
        (["a", 1], ["INVALID_DEPTH_ORDER"]),
        ("a", []),
    ],
    ids=["valid", "partial", "duplicate", "unknown", "not-string", "single-string"],
)
def test_depth_order_validation(depth_order, expected):
    metadata = normalize_metadata(
        {"imageRegion": [point_region("a", 0.1), point_region("b", 0.2)], "imageRegionDepthOrder": depth_order},
        standard=DRAFT_STANDARD,
    )

    assert [issue.code for issue in metadata.validate()] == expected


def test_depth_order_without_regions_reports_unknown_ids():
    metadata = normalize_metadata({"imageRegionDepthOrder": ["ghost"]}, standard=DRAFT_STANDARD)

    assert [issue.code for issue in metadata.validate()] == ["UNKNOWN_DEPTH_ORDER_ID"]


def test_depth_order_round_trips_through_as_dict():
    metadata = normalize_metadata(
        {"imageRegion": [point_region("a", 0.1), point_region("b", 0.2)], "ImageRegionDepthOrder": ["b", "a"]},
        standard=DRAFT_STANDARD,
    )

    assert metadata.as_dict()["imageRegionDepthOrder"] == ["b", "a"]


def test_delete_region_removes_its_depth_order_reference():
    regions = ImageRegionList.from_raw(
        [point_region("a", 0.1), point_region("b", 0.2)], depth_order=["b", "a"], validate=True, standard=DRAFT_STANDARD
    )

    assert regions.delete_region("b")

    assert regions.depth_order == ["a"]
    assert regions.valid


def test_depth_order_is_read_from_exiv2_output():
    flat = _parse_key_value_lines(
        "Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:rId XmpText 1 a\n"
        "Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbShape XmpText 5 point\n"
        "Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbUnit XmpText 8 relative\n"
        "Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbCoordinates XmpText 9 [0.1,0.5]\n"
        "Xmp.iptcExt.ImageRegion[2]/Iptc4xmpExt:rId XmpText 1 b\n"
        "Xmp.iptcExt.ImageRegion[2]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbShape XmpText 5 point\n"
        "Xmp.iptcExt.ImageRegion[2]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbUnit XmpText 8 relative\n"
        "Xmp.iptcExt.ImageRegion[2]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbCoordinates XmpText 9 [0.2,0.5]\n"
        "Xmp.iptcExt.ImageRegionDepthOrder XmpSeq 2 b, a\n"
    )

    metadata = normalize_metadata(flat, source_format="exiv2", standard=DRAFT_STANDARD)

    assert metadata.image_regions.depth_order == ["b", "a"]
    assert metadata.valid


def test_depth_order_is_read_from_xmp():
    xmp = """<x:xmpmeta xmlns:x="adobe:ns:meta/">
      <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/">
        <rdf:Description rdf:about="">
          <Iptc4xmpExt:ImageRegionDepthOrder>
            <rdf:Seq><rdf:li>b</rdf:li><rdf:li>a</rdf:li></rdf:Seq>
          </Iptc4xmpExt:ImageRegionDepthOrder>
        </rdf:Description>
      </rdf:RDF>
    </x:xmpmeta>"""

    assert parse_xmp(xmp)["imageRegionDepthOrder"] == ["b", "a"]


# --- writers ---------------------------------------------------------------------------------------------------------


def _capture_run(monkeypatch) -> list:
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("iptc_iris.io.subprocess.run", fake_run)
    return calls


def test_exiv2_writes_part_index_and_depth_order(monkeypatch, tmp_path: Path):
    calls = _capture_run(monkeypatch)
    image = tmp_path / "image.jpg"
    image.write_bytes(b"")
    region = {"rId": "a", "regionBoundary": multipoint([{"rbMbPdPartIndex": 1, "rbMbPdPartName": "right"}])}

    write_image_regions(
        image,
        {"imageRegion": [region, point_region("b", 0.5)], "imageRegionDepthOrder": ["b", "a"]},
        executable="exiv2",
        tool="exiv2",
        standard=DRAFT_STANDARD,
    )

    command = calls[-1]
    details = "Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:RegionBoundary/Iptc4xmpExt:rbMbPartDetails[1]"
    assert f"-Mset {details}/Iptc4xmpExt:rbMbPdPartIndex XmpText 1" in command
    assert f"-Mset {details}/Iptc4xmpExt:rbMbPdPartName XmpText right" in command
    assert "-Mdel Xmp.iptcExt.ImageRegionDepthOrder" in command
    assert '-Mset Xmp.iptcExt.ImageRegionDepthOrder XmpText type="Seq"' in command
    assert "-Mset Xmp.iptcExt.ImageRegionDepthOrder[1] XmpText b" in command
    assert "-Mset Xmp.iptcExt.ImageRegionDepthOrder[2] XmpText a" in command


def test_exiv2_leaves_depth_order_untouched_when_absent(monkeypatch, tmp_path: Path):
    calls = _capture_run(monkeypatch)
    image = tmp_path / "image.jpg"
    image.write_bytes(b"")

    write_image_regions(image, [point_region("a", 0.1)], executable="exiv2", tool="exiv2", standard=DRAFT_STANDARD)

    assert not any("ImageRegionDepthOrder" in arg for arg in calls[-1])


def test_exiftool_writes_part_index(capture_tool_calls, tmp_path: Path):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"")
    region = {"rId": "a", "regionBoundary": multipoint([{"rbMbPdPartIndex": 1}])}

    write_image_regions(image, [region], executable="exiftool", standard=DRAFT_STANDARD)

    assert "RbMbPartDetails= [{RbMbPdPartIndex= 1}]" in (capture_tool_calls[-1].region_argument or "")


def test_exiftool_uses_bundled_config_and_writes_depth_order(capture_tool_calls, tmp_path: Path):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"")

    write_image_regions(
        image,
        {"imageRegion": [point_region("a", 0.1), point_region("b", 0.2)], "imageRegionDepthOrder": ["b", "a"]},
        executable="exiftool",
        standard=DRAFT_STANDARD,
    )

    call = capture_tool_calls[-1]
    assert call.command[1:3] == ["-config", str(EXIFTOOL_CONFIG)]
    assert EXIFTOOL_CONFIG.is_file()
    assert call.arguments[-3:-1] == ["-XMP-iptcExt:ImageRegionDepthOrder=b", "-XMP-iptcExt:ImageRegionDepthOrder=a"]


def test_exiftool_removes_depth_order_when_empty(capture_tool_calls, tmp_path: Path):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"")

    write_image_regions(
        image,
        {"imageRegion": [point_region("a", 0.1)], "imageRegionDepthOrder": []},
        executable="exiftool",
        standard=DRAFT_STANDARD,
    )

    call = capture_tool_calls[-1]
    assert [arg for arg in call.arguments if "ImageRegionDepthOrder" in arg] == ["-XMP-iptcExt:ImageRegionDepthOrder="]


def test_exiftool_leaves_depth_order_untouched_when_absent(capture_tool_calls, tmp_path: Path):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"")

    write_image_regions(image, [point_region("a", 0.1)], executable="exiftool", standard=DRAFT_STANDARD)

    call = capture_tool_calls[-1]
    assert call.region_argument is not None
    assert not any("ImageRegionDepthOrder" in argument for argument in call.arguments)


def test_exiftool_removes_all_regions_for_an_empty_list(capture_tool_calls, tmp_path: Path):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"")

    write_image_regions(image, [], executable="exiftool", standard=DRAFT_STANDARD)

    call = capture_tool_calls[-1]
    assert "-XMP-iptcExt:ImageRegion=" in call.arguments
    assert call.region_argument is None


def test_exiftool_warning_raises_by_default(monkeypatch, tmp_path: Path):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 0, stdout="", stderr="Warning: Tag 'Foo' is not defined\n    1 image files updated\n"
        )

    monkeypatch.setattr("iptc_iris.io.subprocess.run", fake_run)
    image = tmp_path / "image.jpg"
    image.write_bytes(b"")

    with pytest.raises(MetadataToolWarning, match="Foo") as raised:
        write_image_regions(image, [point_region("a", 0.1)], executable="exiftool", standard=DRAFT_STANDARD)
    assert raised.value.messages == ["Warning: Tag 'Foo' is not defined"]

    completed = write_image_regions(
        image, [point_region("a", 0.1)], executable="exiftool", fail_on_warning=False, standard=DRAFT_STANDARD
    )
    assert "Warning" in completed.stderr


def test_exiftool_summary_on_stderr_is_not_a_warning(monkeypatch, tmp_path: Path):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="    1 image files updated\n")

    monkeypatch.setattr("iptc_iris.io.subprocess.run", fake_run)
    image = tmp_path / "image.jpg"
    image.write_bytes(b"")

    write_image_regions(image, [point_region("a", 0.1)], executable="exiftool", standard=DRAFT_STANDARD)


def test_exiftool_argument_lines_encode_line_breaks_and_trailing_spaces(capture_tool_calls, tmp_path: Path):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"")
    region = point_region("a", 0.1)
    region["name"] = {"x-default": "line 1\nline 2 & <b>  "}

    write_image_regions(
        image, {"imageRegion": [region], "imageRegionDepthOrder": ["a"]}, executable="exiftool", standard=DRAFT_STANDARD
    )

    call = capture_tool_calls[-1]
    assert all("\n" not in argument and argument == argument.rstrip() for argument in call.arguments)
    assert "Name-x-default= line 1\nline 2 & <b>  " in (call.region_argument or "")


def test_inline_struct_argument_keeps_quotes_and_backslashes():
    region = {
        "rId": 'say "hi" \\ there, [x]',
        "regionBoundary": {"rbShape": "point", "rbUnit": "relative", "rbCoordinates": "[0.5,0.5]"},
    }

    argument = format_exiftool_image_region_arg([region])

    assert 'RId= say "hi" \\ there|, [x|]' in argument


# Non-ASCII scripts, emoji, entity-like text, a line break, and ExifTool/argument-file metacharacters.
UNICODE_TEXT = (
    "  Gr\u00fc\u00dfe \u0395\u03bb\u03bb\u03b7\u03bd\u03b9\u03ba\u03ac \u65e5\u672c \U0001f600"
    ' &amp; &#xa; <b>\r\nline 2 \\ "q"\t# c, [x] {y} |pipe  '
)


@pytest.mark.parametrize("tool", ["exiftool", "exiv2"])
def test_unicode_text_and_file_name_round_trip(minimal_jpeg: bytes, tmp_path: Path, tool: str):
    executable = shutil.which(tool)
    if executable is None:
        pytest.skip(f"{tool} is not installed")
    image = tmp_path / "b\u00e4ume \u65e5\u672c.jpg"
    image.write_bytes(minimal_jpeg)
    region = {
        "rId": "a",
        "name": {"x-default": UNICODE_TEXT, "de": "\u00fc"},
        "rCtype": [{"identifiers": ["https://example.org/\u00e4"], "name": {"x-default": UNICODE_TEXT}}],
        "regionBoundary": {"rbShape": "point", "rbUnit": "relative", "rbCoordinates": "[0.5,0.5]"},
    }

    write_image_regions(image, [region], executable=executable, tool=tool, standard=DRAFT_STANDARD)  # type: ignore[arg-type]
    metadata = run_metadata_tool(image, tool, executable=executable, standard=DRAFT_STANDARD)  # type: ignore[arg-type]

    written = metadata.as_dict()["imageRegion"]
    assert len(written) == 1
    # Exiv2 trims trailing spaces from -M values when writing; everything else must survive exactly.
    expected_text = UNICODE_TEXT.rstrip(" ") if tool == "exiv2" else UNICODE_TEXT
    assert written[0]["name"] == {"x-default": expected_text, "de": "\u00fc"}
    assert written[0]["rCtype"] == [{"identifiers": ["https://example.org/\u00e4"], "name": {"x-default": expected_text}}]


def test_exiftool_reports_unwritable_tags_as_warning(minimal_jpeg: bytes, tmp_path: Path):
    executable = shutil.which("exiftool")
    if executable is None:
        pytest.skip("exiftool is not installed")
    image = tmp_path / "image.jpg"
    image.write_bytes(minimal_jpeg)
    region = point_region("a", 0.5)
    region["regionBoundary"]["rbNotAField"] = "x"

    with pytest.raises(MetadataToolWarning):
        write_image_regions(image, [region], executable=executable, validate=False, standard=DRAFT_STANDARD)


@pytest.mark.parametrize("reader", ["exiftool", "exiv2"])
def test_exiftool_round_trip_of_2026_properties(minimal_jpeg: bytes, tmp_path: Path, reader: str):
    writer_executable = shutil.which("exiftool")
    reader_executable = shutil.which(reader)
    if writer_executable is None or reader_executable is None:
        pytest.skip("exiftool and the reader tool must be installed")
    image = tmp_path / "image.jpg"
    image.write_bytes(minimal_jpeg)
    regions = [
        {
            "rId": "a",
            "rMemberOf": "b",
            "regionBoundary": {
                "rbShape": "multipolygon",
                "rbUnit": "relative",
                "rbCoordinates": json.dumps([[square(0.1, 0.1, 0.1), square(0.12, 0.12, 0.02)], [square(0.5, 0.5, 0.1)]]),
                "rbMbPartDetails": [{"rbMbPdPartIndex": 1, "rbMbPdPartId": "p2", "rbMbPdPartName": "lower, right [x]"}],
            },
        },
        point_region("b", 0.5),
        {
            "rId": "c",
            "regionBoundary": {
                "rbShape": "multilinestring",
                "rbUnit": "relative",
                "rbCoordinates": "[[[0.1,0.9],[0.2,0.9]],[[0.3,0.9],[0.4,0.8]]]",
            },
        },
    ]

    completed = write_image_regions(
        image,
        {"imageRegion": regions, "imageRegionDepthOrder": ["b", "a", "c"]},
        executable=writer_executable,
        standard=DRAFT_STANDARD,
    )
    metadata = run_metadata_tool(image, reader, executable=reader_executable, standard=DRAFT_STANDARD)  # type: ignore[arg-type]

    assert "Warning" not in completed.stderr
    data = metadata.as_dict()
    written = {region["rId"]: region for region in data["imageRegion"]}
    for region in regions:
        boundary = written[region["rId"]]["regionBoundary"]
        assert boundary["rbShape"] == region["regionBoundary"]["rbShape"]
        assert json.loads(boundary["rbCoordinates"]) == json.loads(region["regionBoundary"]["rbCoordinates"])
    assert written["a"]["rMemberOf"] == "b"
    assert written["a"]["regionBoundary"]["rbMbPartDetails"] == regions[0]["regionBoundary"]["rbMbPartDetails"]
    assert data["imageRegionDepthOrder"] == ["b", "a", "c"]
    assert metadata.valid


def test_exiv2_round_trip_of_2026_properties(minimal_jpeg: bytes, tmp_path: Path):
    executable = shutil.which("exiv2")
    if executable is None:
        pytest.skip("exiv2 is not installed")
    image = tmp_path / "image.jpg"
    image.write_bytes(minimal_jpeg)
    region = {
        "rId": "a",
        "rMemberOf": "b",
        "regionBoundary": {
            "rbShape": "multipolygon",
            "rbUnit": "relative",
            "rbCoordinates": json.dumps([[square(0.1, 0.1, 0.1)], [square(0.5, 0.5, 0.1)]]),
            "rbMbPartDetails": [{"rbMbPdPartIndex": 1, "rbMbPdPartId": "p2", "rbMbPdPartName": "lower right"}],
        },
    }

    write_image_regions(
        image,
        {"imageRegion": [region, point_region("b", 0.5)], "imageRegionDepthOrder": ["b", "a"]},
        executable=executable,
        tool="exiv2",
        standard=DRAFT_STANDARD,
    )
    metadata = run_metadata_tool(image, "exiv2", executable=executable, standard=DRAFT_STANDARD)

    data = metadata.as_dict()
    first = next(item for item in data["imageRegion"] if item["rId"] == "a")
    assert first["rMemberOf"] == "b"
    assert json.loads(first["regionBoundary"]["rbCoordinates"]) == json.loads(region["regionBoundary"]["rbCoordinates"])
    assert first["regionBoundary"]["rbMbPartDetails"] == region["regionBoundary"]["rbMbPartDetails"]
    assert data["imageRegionDepthOrder"] == ["b", "a"]
    assert metadata.valid


def test_exiv2_writes_every_value_of_a_bag(minimal_jpeg: bytes, tmp_path: Path):
    executable = shutil.which("exiv2")
    if executable is None:
        pytest.skip("exiv2 is not installed")
    image = tmp_path / "image.jpg"
    image.write_bytes(minimal_jpeg)
    region = point_region("a", 0.5)
    region["rCtype"] = [{"identifiers": ["https://example.org/one", "https://example.org/two"], "name": "type"}]

    write_image_regions(image, [region], executable=executable, tool="exiv2", standard=DRAFT_STANDARD)

    packet = subprocess.run(
        [executable, "-pX", str(image)], capture_output=True, check=True, text=True, encoding="utf-8"
    ).stdout
    assert "<rdf:li>https://example.org/one</rdf:li>" in packet
    assert "<rdf:li>https://example.org/two</rdf:li>" in packet


# --- renaming Region Identifiers --------------------------------------------------------------------------------------


def member_region(r_id: str, member_of: str | None = None) -> dict:
    region = point_region(r_id, 0.1 + 0.1 * len(r_id))
    if member_of is not None:
        region["rMemberOf"] = member_of
    return region


def test_rename_region_updates_member_of_and_depth_order():
    regions = ImageRegionList.from_raw(
        [member_region("lead"), member_region("m1", "lead"), member_region("m22", "lead"), member_region("x")],
        depth_order=["m1", "lead", "x"],
        standard=DRAFT_STANDARD,
    )

    assert regions.rename_region("lead", "boss")

    assert [region.r_id for region in regions] == ["boss", "m1", "m22", "x"]
    assert [region.r_member_of for region in regions] == [None, "boss", "boss", None]
    assert regions.depth_order == ["m1", "boss", "x"]
    assert regions.valid


def test_rename_region_rejects_used_or_empty_identifiers():
    regions = ImageRegionList.from_raw([member_region("a"), member_region("bb")], standard=DRAFT_STANDARD)

    with pytest.raises(ValueError, match="already used"):
        regions.rename_region("a", "bb")
    with pytest.raises(ValueError, match="non-empty"):
        regions.rename_region("a", "")
    assert [region.r_id for region in regions] == ["a", "bb"]


def test_rename_region_returns_false_for_unknown_identifier():
    regions = ImageRegionList.from_raw([member_region("a")], standard=DRAFT_STANDARD)

    assert not regions.rename_region("missing", "b")
    assert regions.rename_region("a", "a")


def test_rename_region_keeps_references_when_old_identifier_is_still_used():
    regions = ImageRegionList.from_raw(
        [member_region("dup"), member_region("dup2"), member_region("m", "dup")],
        allow_malformed=True,
        validate=False,
        standard=DRAFT_STANDARD,
    )
    regions._regions[1] = replace(regions._regions[1], r_id="dup")

    assert regions.rename_region("dup", "new")

    assert [region.r_id for region in regions] == ["new", "dup", "m"]
    assert regions[2].r_member_of == "dup"


# --- deprecated Polygon Vertices -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("vertices", "hint"),
    [
        ([[0.1, 0.1]], "point"),
        ([[0.1, 0.1], [0.2, 0.2]], "linestring"),
        ([[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]], "rbCoordinates [[["),
    ],
    ids=["one-vertex", "two-vertices", "polygon"],
)
def test_polygon_vertices_get_a_deprecation_hint_but_stay_valid(vertices, hint):
    boundary = {
        "rbShape": "polygon",
        "rbUnit": "relative",
        "rbVertices": [{"rbX": x, "rbY": y} for x, y in vertices],
    }
    regions = ImageRegionList.from_raw([{"rId": "a", "regionBoundary": boundary}], standard=DRAFT_STANDARD)

    result = regions.validation_result()

    assert [(issue.severity, issue.code) for issue in result.issues] == [("info", "DEPRECATED_POLYGON_VERTICES")]
    assert hint in result.infos[0].message
    assert result.valid
    assert result.warnings == []


def test_polygon_coordinates_get_no_deprecation_hint():
    boundary = {
        "rbShape": "polygon",
        "rbUnit": "relative",
        "rbCoordinates": json.dumps([[[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.1]]]),
    }

    assert codes(boundary) == []


def test_exiftool_write_does_not_create_an_iptc_iim_block(minimal_jpeg: bytes, tmp_path: Path):
    executable = shutil.which("exiftool")
    if executable is None:
        pytest.skip("exiftool is not installed")
    image = tmp_path / "plain.jpg"
    image.write_bytes(minimal_jpeg)

    write_image_regions(image, [point_region("a", 0.5)], executable=executable, standard=DRAFT_STANDARD)

    iptc = subprocess.run(
        [executable, "-j", "-IPTC:all", str(image)], capture_output=True, check=True, text=True, encoding="utf-8"
    ).stdout
    assert json.loads(iptc)[0].keys() == {"SourceFile"}


@pytest.mark.parametrize("tool", ["exiftool", "exiv2"])
def test_writing_without_depth_order_prunes_removed_regions_from_the_file(minimal_jpeg: bytes, tmp_path: Path, tool: str):
    executable = shutil.which(tool)
    if executable is None:
        pytest.skip(f"{tool} is not installed")
    image = tmp_path / "image.jpg"
    image.write_bytes(minimal_jpeg)
    a, b, c = (point_region(r_id, x) for r_id, x in (("a", 0.1), ("b", 0.2), ("c", 0.3)))

    def file_depth_order():
        return run_metadata_tool(image, tool, executable=executable, standard=DRAFT_STANDARD).image_regions.depth_order  # type: ignore[arg-type]

    write_image_regions(
        image,
        {"imageRegion": [a, b, c], "imageRegionDepthOrder": ["c", "a", "b"]},
        executable=executable,
        tool=tool,
        standard=DRAFT_STANDARD,
    )  # type: ignore[arg-type]
    assert file_depth_order() == ["c", "a", "b"]

    # A caller that does not know about the depth order removes region b.
    write_image_regions(image, [a, c], executable=executable, tool=tool, standard=DRAFT_STANDARD)  # type: ignore[arg-type]
    assert file_depth_order() == ["c", "a"]

    # Nothing to prune: the depth order stays as it is.
    write_image_regions(image, [a, c], executable=executable, tool=tool, standard=DRAFT_STANDARD)  # type: ignore[arg-type]
    assert file_depth_order() == ["c", "a"]

    # No listed region remains: the property is removed.
    write_image_regions(image, [point_region("x", 0.5)], executable=executable, tool=tool, standard=DRAFT_STANDARD)  # type: ignore[arg-type]
    assert file_depth_order() is None


def test_delete_region_removes_member_of_references_to_it():
    regions = ImageRegionList.from_raw(
        [member_region("lead"), member_region("m1", "lead"), member_region("m22", "other"), member_region("other")],
        depth_order=["m1", "lead"],
        standard=DRAFT_STANDARD,
    )

    assert regions.delete_region("lead")

    assert [(region.r_id, region.r_member_of) for region in regions] == [("m1", None), ("m22", "other"), ("other", None)]
    assert "rMemberOf" not in regions[0].as_dict()
    assert regions.depth_order == ["m1"]
    assert regions.validation_result().issues == []


def test_delete_region_keeps_member_of_while_the_identifier_is_still_used():
    regions = ImageRegionList.from_raw(
        [member_region("dup"), member_region("dup2"), member_region("m", "dup")],
        allow_malformed=True,
        validate=False,
        standard=DRAFT_STANDARD,
    )
    regions._regions[1] = replace(regions._regions[1], r_id="dup")

    assert regions.delete_region("dup")

    assert regions[1].r_member_of == "dup"
