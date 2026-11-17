"""ExifTool, Exiv2, and XMP sidecar input must produce the same canonical Image Region data."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from iptc_iris import DRAFT_STANDARD, normalize_metadata, parse_xmp
from iptc_iris.io import run_metadata_tool, write_image_regions

# IPTC's example images are not part of the repository. Tests that read them run only when the
# images have been placed in example_data/ locally.
EXAMPLE_DATA = Path(__file__).resolve().parents[1] / "example_data"

EXIV2_STYLE_XMP = """<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/"
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:dc="http://purl.org/dc/elements/1.1/">
   <Iptc4xmpExt:ImageRegion>
    <rdf:Bag>
     <rdf:li>
      <rdf:Description Iptc4xmpExt:rId="a">
       <Iptc4xmpExt:RegionBoundary>
        <rdf:Description Iptc4xmpExt:rbShape="polygon" Iptc4xmpExt:rbUnit="relative">
         <Iptc4xmpExt:rbVertices>
          <rdf:Seq>
           <rdf:li Iptc4xmpExt:rbX="0.1" Iptc4xmpExt:rbY="0.1"/>
           <rdf:li Iptc4xmpExt:rbX="0.3" Iptc4xmpExt:rbY="0.1"/>
           <rdf:li Iptc4xmpExt:rbX="0.3" Iptc4xmpExt:rbY="0.3"/>
          </rdf:Seq>
         </Iptc4xmpExt:rbVertices>
        </rdf:Description>
       </Iptc4xmpExt:RegionBoundary>
       <Iptc4xmpExt:rCtype>
        <rdf:Bag>
         <rdf:li rdf:parseType="Resource">
          <xmp:Identifier>
           <rdf:Bag><rdf:li>https://example.org/one</rdf:li><rdf:li>https://example.org/two, three</rdf:li></rdf:Bag>
          </xmp:Identifier>
         </rdf:li>
        </rdf:Bag>
       </Iptc4xmpExt:rCtype>
       <dc:description>
        <rdf:Alt><rdf:li xml:lang="x-default">  Text with spaces  </rdf:li><rdf:li xml:lang="de">Text</rdf:li></rdf:Alt>
       </dc:description>
      </rdf:Description>
     </rdf:li>
     <rdf:li>
      <rdf:Description Iptc4xmpExt:rId="b">
       <Iptc4xmpExt:RegionBoundary Iptc4xmpExt:rbShape="rectangle" Iptc4xmpExt:rbUnit="relative"
        Iptc4xmpExt:rbX="0.5" Iptc4xmpExt:rbY="0.5" Iptc4xmpExt:rbW="0.1" Iptc4xmpExt:rbH="0.1"/>
      </rdf:Description>
     </rdf:li>
    </rdf:Bag>
   </Iptc4xmpExt:ImageRegion>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>"""


def test_xmp_parser_reads_exiv2_style_structures():
    regions = parse_xmp(EXIV2_STYLE_XMP)["imageRegion"]

    assert regions[0]["rId"] == "a"
    assert regions[0]["regionBoundary"]["rbVertices"] == [
        {"rbX": 0.1, "rbY": 0.1},
        {"rbX": 0.3, "rbY": 0.1},
        {"rbX": 0.3, "rbY": 0.3},
    ]
    assert regions[0]["rCtype"] == [{"identifiers": ["https://example.org/one", "https://example.org/two, three"]}]
    assert regions[0]["XMP-dc:Description"] == {"x-default": "  Text with spaces  ", "de": "Text"}
    assert regions[1]["regionBoundary"] == {
        "rbShape": "rectangle",
        "rbUnit": "relative",
        "rbX": 0.5,
        "rbY": 0.5,
        "rbW": 0.1,
        "rbH": 0.1,
    }


def test_exiftool_language_suffix_keys_are_folded_for_langalt_fields():
    metadata = normalize_metadata(
        {
            "imageRegion": [
                {
                    "rId": "a",
                    "Name": "Name",
                    "Name-de": "Name de",
                    "XMP-dc:Description": "Desc",
                    "XMP-dc:Description-de": "Beschreibung",
                    "XMP-iptcExt:PersonInImage": ["Doe, John"],
                    "regionBoundary": {"rbShape": "point", "rbUnit": "relative", "rbCoordinates": "[0.5,0.5]"},
                }
            ]
        },
        standard=DRAFT_STANDARD,
    )

    region = metadata.as_dict()["imageRegion"][0]
    assert region["name"] == {"x-default": "Name", "de": "Name de"}
    assert region["XMP-dc:Description"] == {"x-default": "Desc", "de": "Beschreibung"}
    assert "XMP-dc:Description-de" not in region


def _square(x: float, y: float, size: float) -> list[list[float]]:
    return [[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]


RICH_DOCUMENT = {
    "imageRegion": [
        {
            "rId": "a",
            "rMemberOf": "b",
            "name": {"x-default": 'Front 日本, "q"', "de": "Vorne"},
            "rCtype": [
                {
                    "identifiers": ["https://example.org/one", "https://example.org/two, with comma"],
                    "name": {"x-default": "type"},
                }
            ],
            "XMP-dc:Description": {"x-default": "Desc", "de": "Beschreibung"},
            "XMP-iptcExt:PersonInImage": ["Doe, John", "Roe, Jane"],
            "regionBoundary": {
                "rbShape": "multipolygon",
                "rbUnit": "relative",
                "rbCoordinates": json.dumps(
                    [[_square(0.1, 0.1, 0.3), _square(0.15, 0.15, 0.05)], [_square(0.6, 0.6, 0.1)]]
                ),
                "rbMbPartDetails": [{"rbMbPdPartIndex": 1, "rbMbPdPartId": "p2", "rbMbPdPartName": "lower, right"}],
            },
        },
        {
            "rId": "b",
            "regionBoundary": {
                "rbShape": "polygon",
                "rbUnit": "relative",
                "rbVertices": [{"rbX": 0.1, "rbY": 0.7}, {"rbX": 0.2, "rbY": 0.7}, {"rbX": 0.2, "rbY": 0.8}],
            },
        },
        {
            "rId": "c",
            "regionBoundary": {"rbShape": "circle", "rbUnit": "pixel", "rbX": 100, "rbY": 100, "rbRx": 20},
        },
    ],
    "imageRegionDepthOrder": ["c", "a"],
    "imageWidth": 2529,
    "imageHeight": 1691,
}


def _canonical(metadata) -> dict:
    data = metadata.as_dict()
    for region in data["imageRegion"]:
        boundary = region["regionBoundary"]
        if isinstance(boundary.get("rbCoordinates"), str):
            boundary["rbCoordinates"] = json.loads(boundary["rbCoordinates"])
    return data


@pytest.mark.parametrize("writer", ["exiftool", "exiv2"])
def test_exiftool_and_exiv2_read_the_same_data(minimal_jpeg: bytes, tmp_path: Path, writer: str):
    exiftool = shutil.which("exiftool")
    exiv2 = shutil.which("exiv2")
    if exiftool is None or exiv2 is None:
        pytest.skip("exiftool and exiv2 must both be installed")
    image = tmp_path / "image.jpg"
    image.write_bytes(minimal_jpeg)

    write_image_regions(
        image, RICH_DOCUMENT, executable=exiftool if writer == "exiftool" else exiv2, tool=writer, standard=DRAFT_STANDARD
    )
    by_exiftool = _canonical(run_metadata_tool(image, "exiftool", executable=exiftool, standard=DRAFT_STANDARD))
    by_exiv2 = _canonical(run_metadata_tool(image, "exiv2", executable=exiv2, standard=DRAFT_STANDARD))

    assert by_exiftool == by_exiv2
    assert by_exiv2["imageWidth"] == 1
    first = by_exiv2["imageRegion"][0]
    expected = RICH_DOCUMENT["imageRegion"][0]
    assert first["rCtype"][0]["identifiers"] == expected["rCtype"][0]["identifiers"]
    assert first["XMP-iptcExt:PersonInImage"] == ["Doe, John", "Roe, Jane"]
    assert first["XMP-dc:Description"] == {"x-default": "Desc", "de": "Beschreibung"}
    assert first["regionBoundary"]["rbMbPartDetails"] == expected["regionBoundary"]["rbMbPartDetails"]
    assert by_exiv2["imageRegionDepthOrder"] == ["c", "a"]


@pytest.mark.parametrize("image_name", ["photo-4iptc-heads.jpg", "photo-stalactite-stalagmite.jpg"])
def test_exiftool_and_exiv2_read_example_images_identically(image_name: str):
    exiftool = shutil.which("exiftool")
    exiv2 = shutil.which("exiv2")
    if exiftool is None or exiv2 is None:
        pytest.skip("exiftool and exiv2 must both be installed")
    image = EXAMPLE_DATA / image_name
    if not image.exists():
        pytest.skip(f"IPTC example image {image_name} is not available locally")

    by_exiftool = run_metadata_tool(image, "exiftool", executable=exiftool, standard=DRAFT_STANDARD).as_diagnostic_dict()
    by_exiv2 = run_metadata_tool(image, "exiv2", executable=exiv2, standard=DRAFT_STANDARD).as_diagnostic_dict()

    assert by_exiftool == by_exiv2


def _fake_exiv2(monkeypatch, summary_exit_code: int) -> None:
    """Let `exiv2 -pX` print nothing and `exiv2 -ps` print a summary with the given exit code."""

    def fake_run(command, **kwargs):
        if "-ps" in command:
            stdout = "File name       : image.jpg\nImage size      : 640 x 480\n"
            stderr = "image.jpg: No Exif data found in the file\n" if summary_exit_code == 253 else "error\n"
            return subprocess.CompletedProcess(command, summary_exit_code, stdout=stdout, stderr=stderr)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("iptc_iris.io.subprocess.run", fake_run)


def test_exiv2_reads_image_size_from_files_without_exif(monkeypatch):
    _fake_exiv2(monkeypatch, summary_exit_code=253)

    metadata = run_metadata_tool("image.jpg", "exiv2", executable="exiv2")

    assert (metadata.image_width, metadata.image_height) == (640, 480)


def test_exiv2_summary_errors_other_than_missing_exif_still_raise(monkeypatch):
    _fake_exiv2(monkeypatch, summary_exit_code=255)

    with pytest.raises(subprocess.CalledProcessError):
        run_metadata_tool("image.jpg", "exiv2", executable="exiv2")
