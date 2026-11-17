"""Tests for the IPTC standard profiles ("2025.1" default, "2026.1-draft" opt-in).

The standard travels with loaded data. Reading never rejects content; the
standard only affects validation and, through it, writing.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from iptc_iris import (
    DEFAULT_STANDARD,
    DRAFT_STANDARD,
    IPTC_STANDARDS,
    ImageRegion,
    ImageRegionList,
    normalize_metadata,
)
from iptc_iris.cli import main
from iptc_iris.config import ValidationConfig
from iptc_iris.geometry import MultiPolygonBoundary
from iptc_iris.io import load_metadata_file, parse_metadata_text, write_image_regions


def square(x: float, y: float, size: float) -> list[list[float]]:
    return [[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]


MULTIPOLYGON = {
    "rbShape": "multipolygon",
    "rbUnit": "relative",
    "rbCoordinates": json.dumps([[square(0.1, 0.1, 0.2)], [square(0.5, 0.5, 0.2)]], separators=(",", ":")),
}
RECTANGLE = {"rbShape": "rectangle", "rbUnit": "relative", "rbX": 0.1, "rbY": 0.1, "rbW": 0.2, "rbH": 0.2}


def multipolygon_document() -> dict:
    return {"imageRegion": [{"rId": "a", "regionBoundary": MULTIPOLYGON}]}


def not_in_standard(issues) -> list:
    return [issue for issue in issues if issue.code == "NOT_IN_STANDARD"]


def test_public_constants():
    assert DEFAULT_STANDARD == "2025.1"
    assert IPTC_STANDARDS == ("2025.1", "2026.1-draft")
    assert DRAFT_STANDARD == "2026.1-draft"


def test_unknown_standard_is_rejected():
    with pytest.raises(ValueError, match="standard must be one of"):
        normalize_metadata(multipolygon_document(), standard="2027")  # type: ignore[arg-type]


def test_reading_keeps_draft_content_under_default_standard():
    metadata = normalize_metadata(multipolygon_document())

    assert metadata.standard == DEFAULT_STANDARD
    assert isinstance(metadata.image_regions[0].boundary, MultiPolygonBoundary)
    assert metadata.as_dict()["imageRegion"][0]["regionBoundary"] == MULTIPOLYGON
    assert not metadata.valid


def test_not_in_standard_message():
    [issue] = not_in_standard(normalize_metadata(multipolygon_document()).errors)

    assert issue.severity == "error"
    assert issue.path == "imageRegion[0].regionBoundary.rbShape"
    assert issue.message == (
        "multipolygon is not part of IPTC Photo Metadata 2025.1; it is defined by the 2026.1 draft. "
        'Use standard="2026.1-draft" to allow it.'
    )


def test_load_metadata_file_carries_standard(tmp_path: Path):
    path = tmp_path / "regions.json"
    path.write_text(json.dumps(multipolygon_document()), encoding="utf-8")

    default = load_metadata_file(path)
    draft = load_metadata_file(path, standard=DRAFT_STANDARD)

    assert default.image_regions.standard == DEFAULT_STANDARD
    assert not default.valid
    assert draft.image_regions.standard == DRAFT_STANDARD
    assert draft.valid
    assert draft.errors == []


def test_parse_metadata_text_carries_standard():
    text = json.dumps(multipolygon_document())

    assert not parse_metadata_text(text).valid
    assert parse_metadata_text(text, standard=DRAFT_STANDARD).valid
    assert parse_metadata_text("", standard=DRAFT_STANDARD).standard == DRAFT_STANDARD


def test_one_off_validation_against_another_standard():
    metadata = normalize_metadata(multipolygon_document(), standard=DRAFT_STANDARD)

    result = metadata.validation_result(standard="2025.1")

    assert not result.valid
    assert not_in_standard(result.errors)
    assert metadata.standard == DRAFT_STANDARD
    assert metadata.valid


@pytest.mark.parametrize(
    ("region", "depth_order", "path"),
    [
        (
            {"regionBoundary": {"rbShape": "point", "rbUnit": "relative", "rbCoordinates": "[0.5,0.5]"}},
            None,
            "imageRegion[0].regionBoundary.rbShape",
        ),
        (
            {
                "regionBoundary": {
                    "rbShape": "multipoint",
                    "rbUnit": "relative",
                    "rbCoordinates": "[[0.1,0.1],[0.2,0.2]]",
                }
            },
            None,
            "imageRegion[0].regionBoundary.rbShape",
        ),
        (
            {
                "regionBoundary": {
                    "rbShape": "linestring",
                    "rbUnit": "relative",
                    "rbCoordinates": "[[0.1,0.1],[0.2,0.2]]",
                }
            },
            None,
            "imageRegion[0].regionBoundary.rbShape",
        ),
        (
            {
                "regionBoundary": {
                    "rbShape": "multilinestring",
                    "rbUnit": "relative",
                    "rbCoordinates": "[[[0.1,0.1],[0.2,0.2]],[[0.5,0.5],[0.6,0.6]]]",
                }
            },
            None,
            "imageRegion[0].regionBoundary.rbShape",
        ),
        ({"regionBoundary": MULTIPOLYGON}, None, "imageRegion[0].regionBoundary.rbShape"),
        (
            {
                "regionBoundary": {
                    "rbShape": "polygon",
                    "rbUnit": "relative",
                    "rbCoordinates": json.dumps([square(0.1, 0.1, 0.6), square(0.2, 0.2, 0.1)]),
                }
            },
            None,
            "imageRegion[0].regionBoundary.rbCoordinates",
        ),
        (
            {
                "regionBoundary": {
                    **MULTIPOLYGON,
                    "rbMbPartDetails": [{"rbMbPdPartIndex": 1, "rbMbPdPartName": "left"}],
                }
            },
            None,
            "imageRegion[0].regionBoundary.rbMbPartDetails",
        ),
        ({"rId": "b", "rMemberOf": "a", "regionBoundary": RECTANGLE}, None, "imageRegion[0].rMemberOf"),
        ({"rId": "a", "regionBoundary": RECTANGLE}, ["a"], "imageRegionDepthOrder"),
    ],
)
def test_draft_features_are_not_in_2025_1(region, depth_order, path):
    data: dict = {"imageRegion": [region]}
    if depth_order is not None:
        data["imageRegionDepthOrder"] = depth_order

    default_paths = [issue.path for issue in not_in_standard(normalize_metadata(data).errors)]
    draft_paths = [issue.path for issue in not_in_standard(normalize_metadata(data, standard=DRAFT_STANDARD).errors)]

    assert path in default_paths
    assert draft_paths == []


def test_published_shapes_are_valid_under_2025_1():
    polygon = {
        "rbShape": "polygon",
        "rbUnit": "relative",
        "rbVertices": [{"rbX": 0.1, "rbY": 0.1}, {"rbX": 0.5, "rbY": 0.1}, {"rbX": 0.3, "rbY": 0.5}],
    }
    circle = {"rbShape": "circle", "rbUnit": "relative", "rbX": 0.5, "rbY": 0.5, "rbRx": 0.1}
    metadata = normalize_metadata(
        {"imageRegion": [{"regionBoundary": RECTANGLE}, {"regionBoundary": polygon}, {"regionBoundary": circle}]}
    )

    assert metadata.validate() == []


def test_rb_vertices_deprecation_hint_only_under_draft():
    polygon = {
        "rbShape": "polygon",
        "rbUnit": "relative",
        "rbVertices": [{"rbX": 0.1, "rbY": 0.1}, {"rbX": 0.5, "rbY": 0.1}, {"rbX": 0.3, "rbY": 0.5}],
    }
    metadata = normalize_metadata({"imageRegion": [{"regionBoundary": polygon}]})

    assert "DEPRECATED_POLYGON_VERTICES" not in [issue.code for issue in metadata.validate()]
    assert "DEPRECATED_POLYGON_VERTICES" in [issue.code for issue in metadata.validate(standard=DRAFT_STANDARD)]


def test_geometry_classes_stay_neutral():
    boundary = MultiPolygonBoundary(coordinates=[[square(0.1, 0.1, 0.2)], [square(0.5, 0.5, 0.2)]])
    region = ImageRegion(boundary=boundary, r_id="a")

    with pytest.raises(ValueError, match="2025.1"):
        ImageRegionList([region])
    assert ImageRegionList([region], standard=DRAFT_STANDARD).valid


# --- writing -------------------------------------------------------------------


@pytest.fixture
def tool_runs(monkeypatch) -> list:
    calls: list = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("iptc_iris.io.subprocess.run", fake_run)
    return calls


def write(image: Path, regions, **kwargs):
    return write_image_regions(image, regions, executable="exiv2", tool="exiv2", **kwargs)


def is_write(command: list[str]) -> bool:
    return any(str(part).startswith("-Mset") for part in command) or "-Mdel Xmp.iptcExt.ImageRegion" in command


def test_plain_lists_default_to_2025_1_and_refuse_draft_content(tmp_path: Path, tool_runs):
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"")

    with pytest.raises(ValueError, match="2026.1-draft"):
        write(image, multipolygon_document()["imageRegion"])
    assert tool_runs == []


def test_write_standard_override_for_plain_lists(tmp_path: Path, tool_runs):
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"")

    write(image, multipolygon_document()["imageRegion"], standard=DRAFT_STANDARD)

    assert any(is_write(command) for command in tool_runs)


def test_write_uses_the_standard_of_loaded_data(tmp_path: Path, tool_runs):
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"")
    draft = normalize_metadata(multipolygon_document(), standard=DRAFT_STANDARD)

    write(image, draft)
    write(image, draft.image_regions)
    assert any(is_write(command) for command in tool_runs)

    tool_runs.clear()
    with pytest.raises(ValueError, match="2025.1"):
        write(image, draft, standard="2025.1")
    with pytest.raises(ValueError, match="2025.1"):
        write(image, normalize_metadata(multipolygon_document()))
    assert tool_runs == []


def test_write_without_validation_keeps_draft_content(tmp_path: Path, tool_runs):
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"")

    write(image, multipolygon_document(), validate=False)

    assert any(is_write(command) for command in tool_runs)


# --- configuration and CLI -----------------------------------------------------


def test_validation_config(tmp_path: Path):
    config = tmp_path / "iptc-iris.toml"
    assert ValidationConfig.load(config).standard is None

    config.write_text('[validation]\nstandard = "2026.1-draft"\n', encoding="utf-8")
    assert ValidationConfig.load(config).standard == DRAFT_STANDARD

    config.write_text('[validation]\nstandard = "2027"\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"\[validation\]\.standard"):
        ValidationConfig.load(config)

    config.write_text('validation = "2026.1-draft"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="TOML table"):
        ValidationConfig.load(config)


@pytest.fixture
def regions_json(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "regions.json"
    path.write_text(json.dumps(multipolygon_document()), encoding="utf-8")
    return path


def test_cli_validate_default_standard(regions_json: Path, capsys):
    assert main(["validate", str(regions_json), "--color", "never"]) == 1
    assert "NOT_IN_STANDARD" in capsys.readouterr().out


def test_cli_validate_standard_flag(regions_json: Path, capsys):
    assert main(["validate", str(regions_json), "--standard", "2026.1-draft", "--color", "never"]) == 0
    assert "NOT_IN_STANDARD" not in capsys.readouterr().out


def test_cli_validate_standard_from_config(regions_json: Path, tmp_path: Path, capsys):
    (tmp_path / "iptc-iris.toml").write_text('[validation]\nstandard = "2026.1-draft"\n', encoding="utf-8")

    assert main(["validate", str(regions_json), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"]
    assert main(["validate", str(regions_json), "--json", "--standard", "2025.1"]) == 1
    assert "NOT_IN_STANDARD" in capsys.readouterr().out


def test_cli_rejects_invalid_config_standard(regions_json: Path, tmp_path: Path, capsys):
    (tmp_path / "iptc-iris.toml").write_text('[validation]\nstandard = "2027"\n', encoding="utf-8")

    assert main(["validate", str(regions_json)]) == 2
    assert "[validation].standard" in capsys.readouterr().err


def test_cli_batch_and_convert_keep_standard(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    batch = tmp_path / "batch.json"
    batch.write_text(json.dumps({"files": [{"path": "a.jpg", **multipolygon_document()}]}), encoding="utf-8")

    assert main(["validate", str(batch), "--json"]) == 1
    assert main(["validate", str(batch), "--json", "--standard", "2026.1-draft"]) == 0
    capsys.readouterr()

    single = tmp_path / "regions.json"
    single.write_text(json.dumps(multipolygon_document()), encoding="utf-8")
    args = ["convert", str(single), "--to", "pixel", "--image-width", "100", "--image-height", "100"]
    assert main(args) == 1
    assert main([*args, "--standard", "2026.1-draft"]) == 0
    assert json.loads(capsys.readouterr().out)["imageRegion"][0]["regionBoundary"]["rbShape"] == "multipolygon"
