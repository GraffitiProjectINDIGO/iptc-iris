from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from iptc_iris import IptcProperty, IptcPropertyRegistry
from iptc_iris.io import run_metadata_tool, write_image_regions

# IPTC's example image is not part of the repository; place it in example_data/ to run this test.
EXAMPLE_IMAGE = Path(__file__).resolve().parents[1] / "example_data" / "photo-4iptc-heads.jpg"


@pytest.mark.parametrize("tool", ["exiftool", "exiv2"])
def test_run_metadata_tool_with_installed_executable(tool: str):
    executable = shutil.which(tool)
    if executable is None:
        pytest.skip(f"{tool} is not installed")
    if not EXAMPLE_IMAGE.exists():
        pytest.skip("IPTC example image photo-4iptc-heads.jpg is not available locally")

    metadata = run_metadata_tool(EXAMPLE_IMAGE, tool, executable=executable)
    data = metadata.as_dict()

    assert metadata.valid
    assert "imageRegion" in data
    assert len(data["imageRegion"]) == 4
    assert data["imageRegion"][0]["name"] == {"x-default": "Speaker"}


def test_write_image_regions_preserves_caller_region_shape(capture_tool_calls, tmp_path: Path):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"")
    region = {
        "rId": "region-1",
        "name": {"x-default": "Region name", "de": "Regionsname"},
        "rCtype": [{"identifiers": ["type-uri"], "name": "type name"}],
        "rRole": [{"identifiers": ["role-uri"], "name": "role name"}],
        "XMP-iptcExt:Contributor": [
            {"identifiers": ["person-uri"], "name": "Person Name", "role": ["contributor-role-uri"]}
        ],
        "XMP-dc:Description": {"x-default": "Description text", "de": "Beschreibung"},
        "XMP-dc:Title": {"x-default": "Transcription text", "de": "Transkription"},
        "regionBoundary": {
            "rbShape": "rectangle",
            "rbUnit": "pixel",
            "rbX": 1,
            "rbY": 2,
            "rbW": 3,
            "rbH": 4,
        },
    }

    write_image_regions(image, [region], executable="exiftool", validate=False)

    call = capture_tool_calls[-1]
    assert call.command[-2:] == ["-@", "-"]
    assert call.arguments[-1] == str(image.absolute())
    image_region_arg = call.region_argument
    assert image_region_arg is not None
    assert "RId= region-1" in image_region_arg
    assert "Name-x-default= Region name" in image_region_arg
    assert "Name-de= Regionsname" in image_region_arg
    assert "RCtype= [{Identifier= [type-uri], Name= type name}]" in image_region_arg
    assert "RRole= [{Identifier= [role-uri], Name= role name}]" in image_region_arg
    assert (
        "XMP-iptcExt:Contributor= [{Identifier= [person-uri], Name= Person Name, Role= [contributor-role-uri]}]"
        in image_region_arg
    )
    assert "XMP-dc:Description-x-default= Description text" in image_region_arg
    assert "XMP-dc:Description-de= Beschreibung" in image_region_arg
    assert "XMP-dc:Title-x-default= Transcription text" in image_region_arg
    assert "XMP-dc:Title-de= Transkription" in image_region_arg
    assert "Name= {x-default= type name}" not in image_region_arg
    assert "XMP-dc:Description= {x-default= Description text" not in image_region_arg


def test_write_image_regions_can_emit_exiv2_commands(monkeypatch, tmp_path: Path):
    completed = subprocess.CompletedProcess(["exiv2"], 0, stdout="", stderr="")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return completed

    monkeypatch.setattr("iptc_iris.io.subprocess.run", fake_run)
    image = tmp_path / "image.jpg"
    image.write_bytes(b"")
    region = {
        "rId": "region-1",
        "name": {"x-default": "Region name", "de": "Regionsname"},
        "rCtype": [{"identifiers": ["type-uri"], "name": "type name"}],
        "rRole": [{"identifiers": ["role-uri"], "name": "role name"}],
        "XMP-iptcExt:Contributor": [
            {"identifiers": ["person-uri"], "name": "Person Name", "role": ["contributor-role-uri"]}
        ],
        "XMP-dc:Description": {"x-default": "Description text", "de": "Beschreibung"},
        "XMP-dc:Title": {"x-default": "Transcription text", "de": "Transkription"},
        "regionBoundary": {
            "rbShape": "rectangle",
            "rbUnit": "pixel",
            "rbX": 1,
            "rbY": 2,
            "rbW": 3,
            "rbH": 4,
        },
    }

    result = write_image_regions(image, [region], executable="exiv2", tool="exiv2", validate=False)

    assert result is completed
    command, kwargs = calls[-1]
    assert '-Mset Xmp.iptcExt.ImageRegion XmpText type="Bag"' in command
    assert '-Mset Xmp.iptcExt.ImageRegion[1] XmpText type="Struct"' in command
    assert "-Mset Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:rId XmpText region-1" in command
    assert '-Mset Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:Name LangAlt lang="x-default" Region name' in command
    assert '-Mset Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:Name LangAlt lang="de" Regionsname' in command
    assert '-Mset Xmp.iptcExt.ImageRegion[1]/dc:description LangAlt lang="de" Beschreibung' in command
    assert '-Mset Xmp.iptcExt.ImageRegion[1]/dc:title LangAlt lang="de" Transkription' in command
    assert '-Mset Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:Contributor XmpText type="Bag"' in command
    contributor = "Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:Contributor[1]"
    assert f'-Mset {contributor}/xmp:Identifier XmpText type="Bag"' in command
    assert f"-Mset {contributor}/xmp:Identifier[1] XmpText person-uri" in command
    assert f'-Mset {contributor}/Iptc4xmpExt:Role XmpText type="Bag"' in command
    assert f"-Mset {contributor}/Iptc4xmpExt:Role[1] XmpText contributor-role-uri" in command
    assert not any(arg.startswith("-Madd") for arg in command)
    assert kwargs["input"] == ""


def test_write_image_regions_uses_passed_registry_for_exiv2(monkeypatch, tmp_path: Path):
    completed = subprocess.CompletedProcess(["exiv2"], 0, stdout="", stderr="")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return completed

    monkeypatch.setattr("iptc_iris.io.subprocess.run", fake_run)
    registry = IptcPropertyRegistry(
        {
            "XMP-iptcExt:CustomLangAlt": IptcProperty(
                stable_key="XMP-iptcExt:CustomLangAlt",
                xmp_id="Iptc4xmpExt:CustomLangAlt",
                exiv2_path="Iptc4xmpExt:CustomLangAlt",
                writer_type="LangAlt",
            )
        }
    )
    image = tmp_path / "image.jpg"
    image.write_bytes(b"")
    region = {
        "XMP-iptcExt:CustomLangAlt": {"x-default": "Custom text", "de": "Eigener Text"},
        "regionBoundary": {
            "rbShape": "rectangle",
            "rbUnit": "relative",
            "rbX": 0.1,
            "rbY": 0.2,
            "rbW": 0.3,
            "rbH": 0.4,
        },
    }

    result = write_image_regions(
        image,
        [region],
        executable="exiv2",
        tool="exiv2",
        validate=False,
        registry=registry,
    )

    assert result is completed
    command, _kwargs = calls[-1]
    assert '-Mset Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:CustomLangAlt LangAlt lang="de" Eigener Text' in command


def test_write_image_regions_rejects_unregistered_exiv2_region_extra(monkeypatch, tmp_path: Path):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(["exiv2"], 0, stdout="", stderr="")

    monkeypatch.setattr("iptc_iris.io.subprocess.run", fake_run)
    image = tmp_path / "image.jpg"
    image.write_bytes(b"")
    region = {
        "XMP-iptcExt:MissingFromRegistry": "value",
        "regionBoundary": {
            "rbShape": "rectangle",
            "rbUnit": "relative",
            "rbX": 0.1,
            "rbY": 0.2,
            "rbW": 0.3,
            "rbH": 0.4,
        },
    }

    with pytest.raises(ValueError, match=r"imageRegion\[0\]\.XMP-iptcExt:MissingFromRegistry"):
        write_image_regions(
            image,
            [region],
            executable="exiv2",
            tool="exiv2",
            validate=False,
            registry=IptcPropertyRegistry(),
        )

    assert calls == []
