"""IPTC 2026.1 draft semantic region membership (rMemberOf) across domain objects and metadata tools."""

import pytest

from iptc_iris import DRAFT_STANDARD, ImageRegion, ImageRegionList, PointBoundary, normalize_metadata, parse_metadata_text
from iptc_iris.io import write_image_regions


def region(r_id, target=None):
    return ImageRegion(boundary=PointBoundary(coordinates=[0.2, 0.3]), r_id=r_id, r_member_of=target)


def test_membership_survives_parsing_export_and_copying():
    original = region("member", "lead")
    parsed = ImageRegion.from_raw(original.as_dict())
    assert parsed.r_member_of == "lead"
    assert "rMemberOf" not in parsed.extra
    assert parsed.as_diagnostic_dict()["rMemberOf"] == "lead"
    assert parsed.with_dimensions(image_width=100, image_height=200).r_member_of == "lead"
    converted = parsed.change_unit("pixel", image_width=100, image_height=200)
    assert converted.r_member_of == "lead"
    assert converted.as_dict()["rMemberOf"] == "lead"
    from_parts = ImageRegion.from_parts(boundary=parsed.boundary, raw=original.as_dict(), extra={})
    assert from_parts.r_member_of == "lead"


@pytest.mark.parametrize("value", [[], ["lead"], {}, 42, True, None])
def test_membership_requires_one_string(value):
    raw = region("member").as_dict() | {"rMemberOf": value}
    parsed = ImageRegion.from_raw(raw, allow_malformed=True)
    assert "REGION_MEMBER_OF_NOT_STRING" in {issue.code for issue in parsed.validate()}
    with pytest.raises(ValueError, match="rMemberOf"):
        ImageRegion.from_raw(raw)


def test_self_reference_is_invalid_even_without_collection():
    issues = region("self", "self").validate()
    assert [(issue.code, issue.path) for issue in issues] == [("REGION_MEMBER_OF_SELF_REFERENCE", "ImgRegion.rMemberOf")]


@pytest.mark.parametrize("target", ["absent", ""])
def test_unresolved_reference_warns_and_preserves_region(target):
    regions = ImageRegionList([region("member", target)], standard=DRAFT_STANDARD)
    issues = regions.validate()
    assert [(issue.code, issue.severity) for issue in issues] == [("UNRESOLVED_REGION_MEMBER_OF", "warning")]
    assert regions.as_dict_list()[0]["rMemberOf"] == target


@pytest.mark.parametrize("count", [2, 3, 20])
def test_cycles_reject_only_cycle_members(count):
    members = [region(str(index), str((index + 1) % count)) for index in range(count)]
    members.append(region("incoming", "0"))
    regions = ImageRegionList(members, validate=False, standard=DRAFT_STANDARD)
    issues = [issue for issue in regions.validate() if issue.code == "REGION_MEMBER_OF_CYCLE"]
    assert {issue.path for issue in issues} == {f"imageRegion[{index}].rMemberOf" for index in range(count)}
    assert all(issue.severity == "error" for issue in issues)
    with pytest.raises(ValueError, match="cycle"):
        ImageRegionList(members, standard=DRAFT_STANDARD)


def test_valid_chain_allows_different_shapes_and_no_geometric_containment():
    lead = ImageRegion.from_raw(
        {
            "rId": "lead",
            "regionBoundary": {"rbShape": "circle", "rbUnit": "relative", "rbX": 0.8, "rbY": 0.8, "rbRx": 0.05},
        }
    )
    regions = ImageRegionList([region("member", "middle"), region("middle", "lead"), lead], standard=DRAFT_STANDARD)
    assert not regions.errors


def test_membership_long_chain_does_not_require_recursion():
    members = [region(str(index), str(index + 1)) for index in range(1200)] + [region("1200")]
    issues = ImageRegionList(members, validate=False, standard=DRAFT_STANDARD)._validate_memberships(
        {member.r_id: [index] for index, member in enumerate(members)}
    )
    assert issues == []


@pytest.mark.parametrize("key", ["rMemberOf", "RMemberOf", "Iptc4xmpExt:rMemberOf", "ImageRegionMemberOf"])
def test_normalizes_structured_tool_names(key):
    metadata = normalize_metadata({"ImageRegion": [{key: "lead", **region("member").as_dict()}]}, standard=DRAFT_STANDARD)
    assert metadata.image_regions[0].r_member_of == "lead"


def test_reads_exiv2_flat_output():
    metadata = parse_metadata_text(
        "Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:rId XmpText 6 member\n"
        "Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:rMemberOf XmpText 4 lead\n",
        source_format="exiv2",
        standard=DRAFT_STANDARD,
    )
    assert metadata.image_regions[0].r_member_of == "lead"


def test_reads_xmp_property():
    metadata = parse_metadata_text(
        """
    <x:xmpmeta xmlns:x="adobe:ns:meta/"
        xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/">
      <rdf:RDF><rdf:Description><Iptc4xmpExt:ImageRegion><rdf:Bag>
        <rdf:li rdf:parseType="Resource"><Iptc4xmpExt:rId>member</Iptc4xmpExt:rId>
          <Iptc4xmpExt:rMemberOf>lead</Iptc4xmpExt:rMemberOf>
        </rdf:li>
      </rdf:Bag></Iptc4xmpExt:ImageRegion></rdf:Description></rdf:RDF>
    </x:xmpmeta>""",
        source_format="xmp",
        standard=DRAFT_STANDARD,
    )
    assert metadata.image_regions[0].r_member_of == "lead"


@pytest.mark.parametrize("tool", ["exiftool", "exiv2"])
def test_writers_emit_membership(capture_tool_calls, tmp_path, tool):
    # Missing targets are warnings, so they must not prevent writing.
    write_image_regions(
        tmp_path / "image.jpg", [region("member", "lead").as_dict()], tool=tool, executable=tool, standard=DRAFT_STANDARD
    )
    call = capture_tool_calls[-1]
    if tool == "exiftool":
        assert "RMemberOf= lead" in (call.region_argument or "")
    else:
        assert "-Mset Xmp.iptcExt.ImageRegion[1]/Iptc4xmpExt:rMemberOf XmpText lead" in call.command


@pytest.mark.parametrize("tool", ["exiftool", "exiv2"])
def test_writers_reject_cycles_before_running_tool(monkeypatch, tmp_path, tool):
    def unexpected_run(*args, **kwargs):
        pytest.fail("Invalid membership must be rejected before invoking the tool")

    monkeypatch.setattr("iptc_iris.io.subprocess.run", unexpected_run)
    with pytest.raises(ValueError, match="cycle"):
        write_image_regions(
            tmp_path / "image.jpg",
            [region("a", "b").as_dict(), region("b", "a").as_dict()],
            tool=tool,
            executable=tool,
            standard=DRAFT_STANDARD,
        )
