from iptc_iris import DEFAULT_IPTC_REGISTRY, load_iptc_registry


def test_default_registry_maps_stable_keys_to_exiv2_paths():
    description = DEFAULT_IPTC_REGISTRY.get("XMP-dc:Description")
    contributor = DEFAULT_IPTC_REGISTRY.get("Iptc4xmpExt:Contributor")

    assert description is not None
    assert description.exiv2_path == "dc:description"
    assert description.writer_type == "LangAlt"
    assert contributor is not None
    assert contributor.stable_key == "XMP-iptcExt:Contributor"
    assert contributor.writer_type == "BagStruct"


def test_loads_iptc_techreference_shape():
    registry = load_iptc_registry(
        {
            "ipmd_top": {
                "description": {
                    "name": "Description",
                    "label": "Caption/Description",
                    "helptext": "Describe the image.",
                    "datatype": "struct",
                    "dataformat": "AltLang",
                    "propoccurrence": "single",
                    "XMPid": "dc:description",
                    "etXMP": "XMP-dc:Description",
                },
                "contributors": {
                    "name": "Contributor",
                    "datatype": "struct",
                    "dataformat": "EntityWRole",
                    "propoccurrence": "multi",
                    "XMPid": "Iptc4xmpExt:Contributor",
                    "etXMP": "XMP-iptcExt:Contributor",
                },
            },
            "ipmd_struct": {
                "EntityWRole": {
                    "name": {"XMPid": "Iptc4xmpExt:Name"},
                    "role": {"XMPid": "Iptc4xmpExt:Role"},
                }
            },
        }
    )

    description = registry.get("dc:description")
    contributor = registry.get("Contributor")

    assert description is not None
    assert description.stable_key == "XMP-dc:Description"
    assert description.writer_type == "LangAlt"
    assert contributor is not None
    assert contributor.stable_key == "XMP-iptcExt:Contributor"
    assert contributor.writer_type == "BagStruct"
    assert "EntityWRole" == contributor.structure_name
