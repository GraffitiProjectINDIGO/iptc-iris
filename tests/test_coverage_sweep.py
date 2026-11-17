"""Focused tests for defensive and edge branches not hit by user-flow tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from examples.direct_class_initialization import expect_failure
from iptc_iris import (
    CircleBoundary,
    ImageRegion,
    ImageRegionList,
    NormalizedMetadata,
    PolygonBoundary,
    RectangleBoundary,
    ValidationResult,
    Vertex,
)
from iptc_iris.builder import _to_float, build_metadata
from iptc_iris.config import ToolConfig, _optional_string
from iptc_iris.geometry.base import (
    InvalidBoundary,
    MissingBoundary,
    UnknownBoundary,
    convert_unit_value,
    number,
    raw_number,
    require_image_dimension,
    require_unit,
    validate_point,
    validate_size,
)
from iptc_iris.io import (
    EXIFTOOL_CONFIG,
    _coerce_scalar,
    _parse_key_value_lines,
    load_metadata_file,
    parse_metadata_text,
    run_metadata_tool,
)
from iptc_iris.models import ValidationIssue, ValidationRun
from iptc_iris.normalizer import (
    _coerce_list,
    _expand_flat_mapping,
    _insert_path,
    _merge_value,
    _normalize_image_region_lang_alts,
    _normalize_value,
    _parse_external_index,
    _tokenize_key,
    normalize_metadata,
)
from iptc_iris.region import _coerce_region_list, _normalize_dimension
from iptc_iris.render import (
    _color_field,
    _format_json_value,
    format_annotated_image_region,
    format_annotated_image_region_runs,
    format_image_region,
    format_image_region_runs,
    format_validation,
    format_validation_runs,
    print_human_runs,
    use_color,
    write_annotated_output,
)
from iptc_iris.xmp import (
    _element_scalar,
    _merge,
    _NameMap,
    _parse_property,
    _parse_struct,
    extract_xmp_packet,
    parse_xmp,
)


def test_builder_models_config_and_cli_edges(tmp_path, capsys, monkeypatch):
    metadata = build_metadata(
        {"imageWidth": ["100"], "imageHeight": ["bad"], "imageRegion": []},
        source_format="test",
        raw={},
    )
    assert metadata.as_dict()["imageWidth"] == 100.0
    assert "imageHeight" not in metadata.as_dict()
    assert _to_float([]) is None
    assert _to_float(object()) is None
    assert NormalizedMetadata().valid
    assert NormalizedMetadata().errors == []
    assert NormalizedMetadata().warnings[0].code == "NO_IMAGE_REGION"

    result = ValidationResult()
    result.add("warning", "WARN", "imageRegion", "warning")
    assert result.warnings[0].code == "WARN"
    assert result.as_dict()["issues"][0]["message"] == "warning"

    assert _optional_string({}, "exiftool") is None
    assert _optional_string({"exiftool": "   "}, "exiftool") is None
    with pytest.raises(ValueError, match="must be a string"):
        _optional_string({"exiftool": 1}, "exiftool")
    assert ToolConfig(exiftool="exiftool").executable_for("exiftool") == "exiftool"
    assert ToolConfig(exiv2="exiv2").executable_for("exiv2") == "exiv2"
    assert ToolConfig().executable_for("other") is None

    config_path = tmp_path / "iptc-iris.toml"
    config_path.write_text("[tools]\nexiftool='exiftool'\nexiv2=''\n", encoding="utf-8")
    assert ToolConfig.load(config_path).exiftool == "exiftool"
    bad_config = tmp_path / "bad.toml"
    bad_config.write_text("tools = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"\[tools\]"):
        ToolConfig.load(bad_config)

    run = ValidationRun(Path("a.json"), metadata, metadata.validation_result())
    print_human_runs([run, run], color=False)
    assert "a.json:" in capsys.readouterr().out
    assert json.loads(format_validation_runs([run, run]))[0]["path"] == "a.json"
    assert '"path": "a.json"' in format_validation_runs([run])
    assert use_color("always")
    assert not use_color("never")
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    assert use_color("auto")


def test_io_and_normalizer_edges(tmp_path, monkeypatch):
    empty_image = tmp_path / "missing.jpg"
    empty_image.write_bytes(b"")
    assert load_metadata_file(empty_image).source_format == "image"
    xmp_path = tmp_path / "metadata.xmp"
    xmp_path.write_text("<rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'/>", encoding="utf-8")
    assert load_metadata_file(xmp_path).as_dict() == {"imageRegion": []}
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"not xmp")
    assert load_metadata_file(image_path).source_format == "image"

    assert parse_metadata_text("   ", source_format="empty").raw == "   "
    assert parse_metadata_text('[{"ImageRegion": []}]', source_format="exiftool-json").as_dict() == {"imageRegion": []}
    assert parse_metadata_text(xmp_path.read_text(encoding="utf-8"), source_format="xmp").as_dict() == {"imageRegion": []}
    parsed = _parse_key_value_lines(
        """
        # comment
        Xmp.foo.A XmpText 1 7
        Xmp.foo.B=8.5
        Xmp.foo.C value
        Xmp.foo.D
        Xmp.foo.Struct XmpText 13 type="Struct"
        """
    )
    assert parsed == {"Xmp.foo.A": 7, "Xmp.foo.B": 8.5, "Xmp.foo.C": "value"}
    assert _coerce_scalar("") == ""
    assert _coerce_scalar("abc") == "abc"

    monkeypatch.setattr("iptc_iris.io.shutil.which", lambda tool: None)
    with pytest.raises(FileNotFoundError):
        run_metadata_tool("file.jpg", "exiftool")

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs.get("input", "")))
        # exiv2 -pX prints the raw XMP packet, which is empty for a file without XMP;
        # exiv2 -ps prints a summary including the image size.
        if "-pX" in command:
            return SimpleNamespace(returncode=0, stdout="")
        if "-ps" in command:
            return SimpleNamespace(returncode=0, stdout="File name       : file.jpg\nImage size      : 640 x 480\n")
        return SimpleNamespace(returncode=0, stdout='[{"ImageRegion": []}]')

    monkeypatch.setattr("iptc_iris.io.shutil.which", lambda tool: f"{tool}.exe")
    monkeypatch.setattr("iptc_iris.io.subprocess.run", fake_run)
    assert run_metadata_tool("file.jpg", "exiftool").as_dict() == {"imageRegion": []}
    assert run_metadata_tool("file.jpg", "exiv2").as_dict() == {
        "imageRegion": [],
        "imageWidth": 640.0,
        "imageHeight": 480.0,
    }
    assert calls[0][0] == ["exiftool.exe", "-config", str(EXIFTOOL_CONFIG), "-@", "-"]
    assert calls[0][1].splitlines()[:5] == ["-charset", "filename=utf8", "-j", "-G1", "-struct"]
    assert calls[1][0][:2] == ["exiv2.exe", "-pX"]
    assert calls[2][0][:2] == ["exiv2.exe", "-ps"]

    normalized = NormalizedMetadata()
    assert normalize_metadata(normalized) is normalized
    assert normalize_metadata(1, source_format="number").raw == 1
    assert normalize_metadata([{"ImageRegion": []}]).as_dict() == {"imageRegion": []}
    assert _normalize_value({"rCtype": {"name": "type"}}, in_image_region=True)["rCtype"] == [{"name": "type"}]
    assert _normalize_image_region_lang_alts(1) == 1
    assert _normalize_image_region_lang_alts({"imageRegion": "bad"}) == {"imageRegion": "bad"}
    value = {"imageRegion": ["bad", {"name": {"x-default": "Face"}, "rCtype": "bad"}]}
    assert _normalize_image_region_lang_alts(value)["imageRegion"][1]["name"]["x-default"] == "Face"
    assert _expand_flat_mapping({"plain": 1}) == {"plain": 1}
    assert _tokenize_key("Xmp.Bad[xx]") == []
    root = {"a": []}
    _insert_path(root, [("a", 0), ("b", None), ("c", None)], 1)
    assert root == {"a": [{"b": {"c": 1}}]}
    root = {"a": [1]}
    _insert_path(root, [("a", 0), ("b", None)], 2)
    assert root == {"a": [{"b": 2}]}
    target = {"x": [1]}
    _merge_value(target, "x", [2])
    assert target["x"] == [1, 2]
    _merge_value(target, "y", [1])
    _merge_value(target, "y", 2)
    assert target["y"] == [1, 2]
    assert _coerce_list(None) == []
    assert _coerce_list([1]) == [1]
    assert _parse_external_index(None) is None
    assert _parse_external_index("0") == 0


def test_geometry_edge_branches():
    unknown = UnknownBoundary({"rbShape": "triangle", "custom": 1})
    assert unknown.as_dict()["custom"] == 1
    assert unknown.raw_dict()["rbShape"] == "triangle"
    assert unknown.validate()[0].code == "UNKNOWN_BOUNDARY_FIELD"
    with pytest.raises(ValueError, match="unknown"):
        unknown.change_unit("relative", image_width=1, image_height=1)

    invalid = InvalidBoundary("bad")
    assert invalid.as_dict() == "bad"
    assert invalid.raw_dict() == "bad"
    assert invalid.validate()[0].path == "InvalidBoundary"
    with pytest.raises(ValueError, match="non-object"):
        invalid.change_unit("relative", image_width=1, image_height=1)

    missing = MissingBoundary()
    assert missing.as_dict() is None
    assert missing.raw_dict() is None
    assert missing.validate()[0].path == "MissingBoundary"
    with pytest.raises(ValueError, match="without"):
        missing.change_unit("relative", image_width=1, image_height=1)

    assert number(object()) is None
    assert raw_number(True) != raw_number(True)
    assert raw_number("") != raw_number("")
    assert raw_number("abc") != raw_number("abc")
    assert raw_number(object()) != raw_number(object())
    with pytest.raises(ValueError, match="rbUnit"):
        require_unit("bad")
    with pytest.raises(ValueError, match="greater than zero"):
        require_image_dimension(0, "image_width")
    assert convert_unit_value(2, "pixel", "pixel", 10) == 2.0
    with pytest.raises(ValueError, match="Cannot convert"):
        convert_unit_value(2, "bad", "pixel", 10)
    assert {issue.code for issue in validate_point({"rbX": "bad", "rbY": "bad"}, "p", image_width=1, image_height=1)}
    assert validate_point({"rbX": -1, "rbY": 2, "rbUnit": "pixel"}, "p", image_width=1, image_height=1)
    assert validate_size({}, "rbW", "p") == []
    assert validate_size({"rbW": "bad"}, "rbW", "p")[0].code == "INVALID_NUMBER"
    assert validate_size({"rbW": 0}, "rbW", "p")[0].code == "INVALID_SIZE"

    circle = CircleBoundary.from_dict({"rbUnit": "relative", "rbX": 0.5, "rbY": 0.5, "rbRx": 0.1})
    assert circle.with_position(x=0.6).x == 0.6
    assert circle.with_unit("relative").unit == "relative"
    assert circle.change_unit("relative", image_width=100, image_height=100).unit == "relative"
    assert CircleBoundary(unit="relative", x=0.95, y=0.95, radius=0.1, allow_malformed=True).validate()
    assert CircleBoundary(unit="pixel", x=95, y=95, radius=10).validate(image_width=100, image_height=100)
    with pytest.raises(ValueError, match="rbRx"):
        circle.with_radius(0)

    rectangle = RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4)
    assert rectangle.with_position(x=0.2).x == 0.2
    assert rectangle.with_size(width=0.2).width == 0.2
    assert rectangle.with_height(0.2).height == 0.2
    assert rectangle.with_unit("relative").unit == "relative"
    assert rectangle.change_unit("relative", image_width=100, image_height=100).unit == "relative"
    assert RectangleBoundary(unit="relative", x=0.1, y=0.95, width=0.1, height=0.1, allow_malformed=True).validate()
    assert RectangleBoundary(unit="pixel", x=10, y=95, width=10, height=10).validate(image_width=100, image_height=100)

    vertex = Vertex.from_dict({"rbX": 0.1, "rbY": 0.2})
    assert vertex.as_dict() == {"rbX": 0.1, "rbY": 0.2}
    assert vertex.with_position(y=0.3).y == 0.3
    assert vertex.change_unit("relative", "relative", image_width=100, image_height=100).x == 0.1
    assert vertex.change_unit("relative", "pixel", image_width=1, image_height=1).x == 0.1
    bad_vertex = Vertex.from_raw("bad", allow_malformed=True)
    with pytest.raises(ValueError, match="vertex"):
        bad_vertex.as_dict()
    assert bad_vertex.raw_dict() == "bad"
    assert bad_vertex.validate()[0].code == "VERTEX_NOT_OBJECT"
    assert Vertex.from_raw({"rbX": "bad"}, allow_malformed=True).validate()

    with pytest.raises(ValueError, match="list"):
        PolygonBoundary.from_dict({"rbUnit": "relative", "rbVertices": "bad"})
    polygon = PolygonBoundary.from_dict(
        {
            "rbUnit": "relative",
            "rbVertices": [{"rbX": 0.1, "rbY": 0.2}, {"rbX": 0.4, "rbY": 0.2}, {"rbX": 0.1, "rbY": 0.5}],
        }
    )
    assert polygon.with_unit("relative").unit == "relative"
    assert polygon.change_unit("relative", image_width=100, image_height=100).unit == "relative"
    bad_polygon = PolygonBoundary.from_raw(
        {"rbShape": "polygon", "rbUnit": "relative", "rbVertices": "bad"},
        allow_malformed=True,
    )
    with pytest.raises(ValueError, match="list"):
        bad_polygon.change_unit("pixel", image_width=100, image_height=100)
    malformed_polygon = PolygonBoundary.from_raw(
        {"rbShape": "polygon", "rbUnit": "relative", "rbX": 1, "rbVertices": None},
        allow_malformed=True,
    )
    assert {issue.code for issue in malformed_polygon.validate()} >= {
        "MISSING_BOUNDARY_FIELD",
        "FORBIDDEN_BOUNDARY_FIELD",
    }


def test_region_render_and_xmp_edges(tmp_path, capsys):
    region = ImageRegion.from_parts(
        boundary=MissingBoundary(),
        raw={"rId": "", "name": "", "rCtype": [1], "rRole": [{"identifiers": ["urn:test"]}]},
        extra={"custom": 1},
        allow_malformed=True,
    )
    assert region.as_dict()["custom"] == 1
    assert region.validate_boundary(None, image_width=None, image_height=None)[0].path == "ImgRegion.regionBoundary"
    assert {issue.code for issue in region.validate()} >= {"EMPTY_REGION_ID", "EMPTY_REGION_NAME", "ENTITY_NOT_OBJECT"}
    weird_name = ImageRegion(
        name={"": 1, "de": ""},
        boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4),
    )
    assert {issue.code for issue in weird_name.validate()} >= {
        "REGION_NAME_LANGUAGE_INVALID",
        "REGION_NAME_VALUE_INVALID",
    }
    assert ImageRegion.from_raw(region) is region
    with pytest.raises(ValueError, match="object"):
        ImageRegion.from_raw("bad")
    assert ImageRegion.from_raw("bad", allow_malformed=True).extra["raw"] == "bad"

    regions = ImageRegionList([region], validate=False)
    assert not regions.delete_region("missing")
    assert _coerce_region_list(None) == []
    assert _coerce_region_list(regions) == [region]
    assert _coerce_region_list(region) == [region]
    assert _coerce_region_list([regions, region]) == [region, region]
    with pytest.raises(ValueError, match="number"):
        _normalize_dimension(True, "image_width")
    with pytest.raises(ValueError, match="greater"):
        _normalize_dimension(-1, "image_width")

    result = ValidationResult([ValidationIssue("warning", "W", "notRegion", "ignored")])
    assert json.loads(format_validation(result))["valid"]
    assert json.loads(format_validation(ImageRegionList(validate=False)))["issues"] == []
    valid_region = ImageRegion(boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4))
    assert json.loads(format_validation(valid_region))["valid"]
    with pytest.raises(TypeError):
        format_validation(object())
    with pytest.raises(TypeError):
        format_image_region(object())

    run = ValidationRun(Path("file.json"), NormalizedMetadata(image_regions=regions), ValidationResult())
    assert "file.json" in format_image_region_runs([run, run], color=False)
    assert "file.json" in format_annotated_image_region_runs([run, run], color=False)
    assert format_image_region(NormalizedMetadata(image_regions=regions), ignore_dimensions=True).startswith("[")
    assert "MISSING_REGION_BOUNDARY" in format_annotated_image_region(region, ignore_dimensions=True)
    write_annotated_output("-", "{}")
    captured = capsys.readouterr()
    assert "{}" in captured.out
    assert "not standard JSON" in captured.err
    output_path = tmp_path / "out.jsonc"
    write_annotated_output(str(output_path), "{}")
    assert output_path.read_text(encoding="utf-8") == "{}\n"
    assert "not standard JSON" in capsys.readouterr().err
    assert _color_field("field", "unknown", enabled=True) == "field"
    assert _format_json_value([], color=False, issue_colors={}, path="imageRegion", level=0, native=True) == "[]"
    assert _format_json_value({}, color=False, issue_colors={}, path="imageRegion", level=0, native=True) == "{}"

    assert extract_xmp_packet(b"abc") is None
    assert extract_xmp_packet(b"xx<rdf:RDF></rdf:RDF>yy") == "<rdf:RDF></rdf:RDF>"
    xmp = b"""noise <?xpacket begin=''?>
    <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
             xmlns:iptcExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/"
             xmlns:xml="http://www.w3.org/XML/1998/namespace">
      <rdf:Description>
        <iptcExt:ImageRegion>
          <rdf:Bag>
            <rdf:li rdf:parseType="Resource" extra="1">
              <iptcExt:Name><rdf:Alt><rdf:li xml:lang="x-default">Face</rdf:li><foo>skip</foo></rdf:Alt></iptcExt:Name>
              <iptcExt:rRole><rdf:Seq><rdf:li rdf:resource="urn:role"/></rdf:Seq></iptcExt:rRole>
              <iptcExt:RegionBoundary rdf:parseType="Resource">
                <iptcExt:rbShape>rectangle</iptcExt:rbShape>
                <iptcExt:rbUnit>relative</iptcExt:rbUnit>
                <iptcExt:rbX>0.1</iptcExt:rbX>
                <iptcExt:rbY>0.2</iptcExt:rbY>
                <iptcExt:rbW>0.3</iptcExt:rbW>
                <iptcExt:rbH>0.4</iptcExt:rbH>
              </iptcExt:RegionBoundary>
            </rdf:li>
          </rdf:Bag>
        </iptcExt:ImageRegion>
      </rdf:Description>
    </rdf:RDF><?xpacket end='w'?>"""
    parsed = parse_xmp(xmp)
    assert parsed["imageRegion"][0]["name"]["x-default"] == "Face"
    assert parsed["imageRegion"][0]["rRole"] == ["urn:role"]


def test_remaining_precision_branches(tmp_path, capsys, monkeypatch):
    with pytest.raises(AssertionError, match="expected ValueError"):
        expect_failure("no failure", lambda: None)

    from iptc_iris import cli

    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps({"imageRegion": []}), encoding="utf-8")
    assert cli.main(["validate", str(metadata_path)]) == 0
    assert "IPTC Image Region metadata is valid." in capsys.readouterr().out
    assert cli.main(["validate", str(metadata_path), "--tool", "exiftool", "--exiftool", "missing"]) == 2
    assert capsys.readouterr().err.startswith("iptc-iris: ")
    with pytest.raises(SystemExit):
        cli.main(["other"])
    assert "invalid choice: 'other'" in capsys.readouterr().err
    args = SimpleNamespace(tool="exiftool", exiftool=None, exiv2=None)
    cli._infer_tool_from_executable_flags(args)
    with pytest.raises(FileNotFoundError):
        cli._expand_paths(tmp_path / "*.missing")

    normalized = NormalizedMetadata(
        image_regions=ImageRegionList(
            ImageRegion(boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4))
        ),
        image_height=800,
    )
    assert normalized.as_dict()["imageHeight"] == 800
    assert normalized.errors == []
    assert normalized.warnings == []
    assert normalized.valid

    assert validate_size({"rbW": 1}, "rbW", "p") == []
    assert CircleBoundary(unit="relative", x=0.05, y=0.05, radius=0.1, allow_malformed=True).validate()
    assert RectangleBoundary.from_raw(
        {"rbShape": "rectangle", "rbUnit": "relative", "rbX": "bad", "rbY": 0.1, "rbW": 0, "rbH": 0.1},
        allow_malformed=True,
    ).validate()
    invalid_vertex = Vertex.from_raw({"rbX": "bad", "rbY": 0.2}, allow_malformed=True)
    assert invalid_vertex.errors
    assert invalid_vertex.warnings == []
    assert not invalid_vertex.valid
    with pytest.raises(ValueError, match="rbX"):
        invalid_vertex.as_dict()

    monkeypatch.setattr("iptc_iris.normalizer._normalize_value", lambda *_args, **_kwargs: [])
    assert normalize_metadata({}).as_dict() == {"imageRegion": []}
    monkeypatch.undo()
    root = {"a": 1}
    _insert_path(root, [("a", None), ("b", None)], 2)
    assert root == {"a": {"b": 2}}
    root = {}
    _insert_path(root, [("a", 0)], 2)
    assert root == {"a": [2]}
    target = {"a": 1, "b": 1}
    _merge_value(target, "a", [2, 3])
    _merge_value(target, "b", 2)
    assert target == {"a": [1, 2, 3], "b": [1, 2]}

    named_region = ImageRegion(
        name="Face",
        boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4),
    )
    assert named_region.valid
    empty_name = ImageRegion(
        name={},
        boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4),
    )
    assert empty_name.warnings[0].code == "EMPTY_REGION_NAME"
    invalid_boundary_region = ImageRegion.from_raw({"regionBoundary": "bad"}, allow_malformed=True)
    assert invalid_boundary_region.errors[0].code == "BOUNDARY_NOT_OBJECT"
    assert _coerce_region_list("raw") == ["raw"]

    run = ValidationRun(
        Path("file.json"),
        NormalizedMetadata(),
        ValidationResult([ValidationIssue("error", "E", "notImageRegion", "ignored")]),
    )
    assert "ignored" not in format_image_region_runs([run], color=False)
    issues = [
        ValidationIssue("error", "E", "imageRegion[0].name", "error"),
        ValidationIssue("warning", "W", "imageRegion[0].name", "warning"),
        ValidationIssue("error", "E", "other", "ignored"),
        ValidationIssue("info", "I", "imageRegion[0].custom", "hint"),
        ValidationIssue("info", "I", "imageRegion[0].name", "hint does not override the error"),
        ValidationIssue("notice", "N", "imageRegion[0].unknown", "ignored"),  # type: ignore[arg-type]
    ]
    rendered = format_image_region(
        ImageRegion(name="Face", boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4)),
        color=True,
    )
    assert "\033[32m" in rendered
    assert _format_json_value(True, color=False, issue_colors={}, path="imageRegion", level=0, native=True) == "true"
    from iptc_iris.render import _issue_colors

    colors = _issue_colors(issues)
    assert colors["imageRegion[0].name"] == "\033[31m"
    assert "other" not in colors
    assert colors["imageRegion[0].custom"] == "\033[36m"
    assert "imageRegion[0].unknown" not in colors

    scalar_xmp = parse_xmp(
        """
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                 xmlns:iptcExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/">
          <rdf:Description><iptcExt:ImageRegion>scalar</iptcExt:ImageRegion></rdf:Description>
        </rdf:RDF>
        """
    )
    assert scalar_xmp["imageRegion"] == [{"raw": "scalar"}]
    nested_alt_xmp = parse_xmp(
        """
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                 xmlns:iptcExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/"
                 xmlns:xml="http://www.w3.org/XML/1998/namespace">
          <rdf:Description>
            <iptcExt:ImageRegion>
              <rdf:Bag><rdf:li><rdf:Alt><rdf:li xml:lang="x-default">Alt</rdf:li></rdf:Alt></rdf:li></rdf:Bag>
            </iptcExt:ImageRegion>
          </rdf:Description>
        </rdf:RDF>
        """
    )
    assert nested_alt_xmp["imageRegion"] == [{"x-default": "Alt"}]
    import xml.etree.ElementTree as ET

    element = ET.fromstring('<x rdf:resource="urn:test" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>')
    assert _element_scalar(element) == "urn:test"
    list_item_xml = """
        <rdf:li xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
          <rdf:Seq><rdf:li>one</rdf:li></rdf:Seq>
        </rdf:li>
        """.strip()
    assert _parse_property(ET.fromstring(list_item_xml), _NameMap(list_item_xml)) == ["one"]
    struct_xml = """
        <x rdf:resource="urn:resource" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
          <rdf:li>skip</rdf:li>
        </x>
        """.strip()
    assert _parse_struct(ET.fromstring(struct_xml), _NameMap(struct_xml)) == {"identifier": "urn:resource"}
    merged = {"a": [1], "b": 1}
    _merge(merged, "a", 2)
    _merge(merged, "b", 2)
    assert merged == {"a": [1, 2], "b": [1, 2]}
