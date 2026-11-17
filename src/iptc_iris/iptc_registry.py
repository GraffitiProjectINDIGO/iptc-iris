"""IPTC Photo Metadata property registry helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

WriterType = Literal["XmpText", "LangAlt", "XmpBag", "XmpSeq", "Struct", "BagStruct"]


XMP_PREFIX_TO_STABLE_PREFIX: dict[str, str] = {
    "dc": "dc",
    "Iptc4xmpCore": "iptcCore",
    "Iptc4xmpExt": "iptcExt",
    "photoshop": "photoshop",
    "plus": "plus",
    "xmp": "xmp",
    "xmpRights": "xmpRights",
}
STABLE_PREFIX_TO_XMP_PREFIX = {value.casefold(): key for key, value in XMP_PREFIX_TO_STABLE_PREFIX.items()}
XMP_PREFIX_ALIASES = {
    "iptccore": "Iptc4xmpCore",
    "iptc4xmpcore": "Iptc4xmpCore",
    "iptcext": "Iptc4xmpExt",
    "iptc4xmpext": "Iptc4xmpExt",
    "dc": "dc",
    "photoshop": "photoshop",
    "plus": "plus",
    "xmp": "xmp",
    "xmprights": "xmpRights",
}

NAMESPACE_URIS: dict[str, str] = {
    "Iptc4xmpCore": "http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/",
    "Iptc4xmpExt": "http://iptc.org/std/Iptc4xmpExt/2008-02-29/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "photoshop": "http://ns.adobe.com/photoshop/1.0/",
    "plus": "http://ns.useplus.org/ldf/xmp/1.0/",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "xmpRights": "http://ns.adobe.com/xap/1.0/rights/",
}


@dataclass(frozen=True, slots=True)
class IptcProperty:
    """One registry entry for an IPTC/XMP metadata property."""

    stable_key: str
    xmp_id: str
    exiv2_path: str
    label: str = ""
    help: str = ""
    data_type: str = ""
    cardinality: str = ""
    structure_name: str = ""
    writer_type: WriterType = "XmpText"
    structure: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    raw: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


class IptcPropertyRegistry:
    """Lookup table for canonical IPTC property keys and Exiv2 paths."""

    def __init__(self, properties: Mapping[str, IptcProperty] | None = None) -> None:
        self._by_stable_key: dict[str, IptcProperty] = {}
        self._by_lookup_key: dict[str, IptcProperty] = {}
        self._by_local_token: dict[str, IptcProperty] = {}
        for prop in (properties or {}).values():
            self.add(prop)

    @property
    def properties(self) -> Mapping[str, IptcProperty]:
        """Return registry entries keyed by canonical stable key."""

        return MappingProxyType(self._by_stable_key)

    def add(self, prop: IptcProperty) -> None:
        """Add or replace a property definition."""

        self._by_stable_key[prop.stable_key] = prop
        for key in _lookup_keys(prop):
            self._by_lookup_key[_normalize_lookup_key(key)] = prop
        local = prop.xmp_id.split(":", 1)[-1]
        self._by_local_token.setdefault(_token(local), prop)
        self._by_local_token.setdefault(_token(prop.stable_key.rsplit(":", 1)[-1]), prop)

    def get(self, key: str) -> IptcProperty | None:
        """Return a property for a stable key, XMP id, Exiv2 path, or local name."""

        prop = self._by_lookup_key.get(_normalize_lookup_key(key))
        if prop is not None:
            return prop
        return self._by_local_token.get(_token(key.rsplit(":", 1)[-1]))

    def stable_key(self, key: str) -> str | None:
        """Return the canonical stable key for a known property key."""

        prop = self.get(key)
        return prop.stable_key if prop is not None else normalize_stable_key(key)

    def exiv2_path(self, key: str) -> str | None:
        """Return the Exiv2 XMP path for a known or derivable stable key."""

        prop = self.get(key)
        if prop is not None:
            return prop.exiv2_path
        normalized = normalize_xmp_id(key)
        return normalized

    @classmethod
    def from_techreference(cls, data: Mapping[str, Any]) -> IptcPropertyRegistry:
        """Build a registry from IPTC Photo Metadata TechReference JSON data."""

        struct_defs = data.get("ipmd_struct")
        if not isinstance(struct_defs, Mapping):
            struct_defs = {}

        registry = cls()
        top = data.get("ipmd_top")
        if isinstance(top, Mapping):
            for item in top.values():
                if isinstance(item, Mapping):
                    prop = property_from_techreference(item, struct_defs=struct_defs)
                    if prop is not None:
                        registry.add(prop)
        return registry

    @classmethod
    def from_json_file(cls, path: str | Path) -> IptcPropertyRegistry:
        """Load a registry from an IPTC TechReference JSON file."""

        with Path(path).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, Mapping):
            raise ValueError("IPTC TechReference JSON must be an object.")
        return cls.from_techreference(data)


def load_iptc_registry(source: str | Path | Mapping[str, Any] | None = None) -> IptcPropertyRegistry:
    """Load an IPTC registry from a TechReference mapping or JSON file.

    When source is omitted, the package's built-in seed registry is returned.
    """

    if source is None:
        return DEFAULT_IPTC_REGISTRY
    if isinstance(source, Mapping):
        return IptcPropertyRegistry.from_techreference(source)
    return IptcPropertyRegistry.from_json_file(source)


def property_from_techreference(
    item: Mapping[str, Any],
    *,
    struct_defs: Mapping[str, Any] | None = None,
) -> IptcProperty | None:
    """Create a property definition from one IPTC TechReference item."""

    xmp_id = _clean_string(item.get("XMPid"))
    et_xmp = _clean_string(item.get("etXMP"))
    if not xmp_id and et_xmp:
        xmp_id = normalize_xmp_id(et_xmp) or ""
    if not xmp_id:
        return None

    stable_key = et_xmp or stable_key_from_xmp_id(xmp_id)
    exiv2_path = normalize_xmp_id(xmp_id) or xmp_id
    data_type = _clean_string(item.get("datatype"))
    data_format = _clean_string(item.get("dataformat"))
    cardinality = _clean_string(item.get("propoccurrence"))
    structure: Mapping[str, Any] = MappingProxyType({})
    if struct_defs is not None and data_format in struct_defs and isinstance(struct_defs[data_format], Mapping):
        structure = MappingProxyType(dict(struct_defs[data_format]))

    return IptcProperty(
        stable_key=stable_key,
        xmp_id=exiv2_path,
        exiv2_path=exiv2_path,
        label=_clean_string(item.get("label") or item.get("name")),
        help=_clean_string(item.get("helptext")),
        data_type=data_type,
        cardinality=cardinality,
        structure_name=data_format,
        writer_type=infer_writer_type(data_type=data_type, data_format=data_format, cardinality=cardinality),
        structure=structure,
        raw=MappingProxyType(dict(item)),
    )


def infer_writer_type(*, data_type: str, data_format: str = "", cardinality: str = "") -> WriterType:
    """Infer the Exiv2 writer container type from TechReference metadata."""

    if data_format.casefold() == "altlang":
        return "LangAlt"
    if data_type.casefold() == "struct":
        return "BagStruct" if cardinality.casefold() == "multi" else "Struct"
    if cardinality.casefold() == "multi":
        return "XmpBag"
    return "XmpText"


def normalize_stable_key(key: str) -> str | None:
    """Return a stable ``XMP-prefix:Property`` key when the input is namespaced."""

    if key.startswith("XMP-") and ":" in key:
        group, local = key[4:].split(":", 1)
        xmp_prefix = _xmp_prefix_from_any(group)
        stable_prefix = XMP_PREFIX_TO_STABLE_PREFIX.get(group, group)
        if xmp_prefix is not None:
            stable_prefix = XMP_PREFIX_TO_STABLE_PREFIX.get(xmp_prefix, stable_prefix)
        return f"XMP-{stable_prefix}:{_stable_local_name(local, stable_prefix)}"

    xmp_id = normalize_xmp_id(key)
    if xmp_id is None:
        return None
    return stable_key_from_xmp_id(xmp_id)


def stable_key_from_xmp_id(xmp_id: str) -> str:
    """Return the package stable key for an XMP id such as ``dc:description``."""

    prefix, local = xmp_id.split(":", 1)
    stable_prefix = XMP_PREFIX_TO_STABLE_PREFIX.get(prefix, prefix)
    return f"XMP-{stable_prefix}:{_stable_local_name(local, stable_prefix)}"


def normalize_xmp_id(key: str) -> str | None:
    """Return an Exiv2/XMP id for namespaced keys, or None for plain names."""

    value = key.strip()
    if value.startswith("XMP-") and ":" in value:
        group, local = value[4:].split(":", 1)
        xmp_prefix = _xmp_prefix_from_any(group)
        if xmp_prefix is None:
            return None
        return f"{xmp_prefix}:{_xmp_local_name(local, xmp_prefix)}"
    if ":" not in value:
        return None
    prefix, local = value.split(":", 1)
    xmp_prefix = _xmp_prefix_from_any(prefix)
    if xmp_prefix is None:
        return None
    return f"{xmp_prefix}:{_xmp_local_name(local, xmp_prefix)}"


def namespace_registration_for_path(exiv2_path: str) -> tuple[str, str] | None:
    """Return an Exiv2 namespace registration tuple for an XMP path."""

    prefix = exiv2_path.split(":", 1)[0]
    uri = NAMESPACE_URIS.get(prefix)
    if uri is None:
        return None
    return prefix, uri


def _lookup_keys(prop: IptcProperty) -> list[str]:
    keys = [prop.stable_key, prop.xmp_id, prop.exiv2_path]
    local = prop.xmp_id.split(":", 1)[-1]
    keys.extend([local, prop.stable_key.rsplit(":", 1)[-1]])
    return keys


def _normalize_lookup_key(key: str) -> str:
    normalized = normalize_stable_key(key) or normalize_xmp_id(key) or key
    return normalized.casefold()


def _xmp_prefix_from_any(prefix: str) -> str | None:
    return XMP_PREFIX_ALIASES.get(prefix.casefold())


def _stable_local_name(local: str, stable_prefix: str) -> str:
    if stable_prefix == "dc":
        return local[:1].upper() + local[1:]
    return local


def _xmp_local_name(local: str, xmp_prefix: str) -> str:
    if xmp_prefix == "dc":
        return local[:1].lower() + local[1:]
    return local


def _token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value).casefold()


def _clean_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _seed_property(
    stable_key: str,
    xmp_id: str,
    *,
    label: str,
    data_type: str,
    cardinality: str,
    structure_name: str = "",
    writer_type: WriterType | None = None,
) -> IptcProperty:
    writer = writer_type or infer_writer_type(
        data_type=data_type,
        data_format=structure_name,
        cardinality=cardinality,
    )
    return IptcProperty(
        stable_key=stable_key,
        xmp_id=xmp_id,
        exiv2_path=xmp_id,
        label=label,
        data_type=data_type,
        cardinality=cardinality,
        structure_name=structure_name,
        writer_type=writer,
    )


DEFAULT_IPTC_REGISTRY = IptcPropertyRegistry(
    {
        "XMP-dc:Description": _seed_property(
            "XMP-dc:Description",
            "dc:description",
            label="Caption/Description",
            data_type="struct",
            cardinality="single",
            structure_name="AltLang",
        ),
        "XMP-dc:Title": _seed_property(
            "XMP-dc:Title",
            "dc:title",
            label="Title",
            data_type="struct",
            cardinality="single",
            structure_name="AltLang",
        ),
        "XMP-iptcExt:Contributor": _seed_property(
            "XMP-iptcExt:Contributor",
            "Iptc4xmpExt:Contributor",
            label="Contributor",
            data_type="struct",
            cardinality="multi",
            structure_name="EntityWRole",
        ),
        "XMP-iptcExt:PersonInImage": _seed_property(
            "XMP-iptcExt:PersonInImage",
            "Iptc4xmpExt:PersonInImage",
            label="Person Shown in the Image",
            data_type="string",
            cardinality="multi",
        ),
        "XMP-iptcExt:OrganisationInImageName": _seed_property(
            "XMP-iptcExt:OrganisationInImageName",
            "Iptc4xmpExt:OrganisationInImageName",
            label="Name of Organisation Featured in the Image",
            data_type="string",
            cardinality="multi",
        ),
        "XMP-iptcExt:OrganisationInImageCode": _seed_property(
            "XMP-iptcExt:OrganisationInImageCode",
            "Iptc4xmpExt:OrganisationInImageCode",
            label="Code of Organisation Featured in the Image",
            data_type="string",
            cardinality="multi",
        ),
    }
)
