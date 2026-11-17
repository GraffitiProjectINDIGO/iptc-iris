"""Parse XMP packets and extract IPTC Image Region metadata structures."""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from typing import Any

from .iptc_registry import NAMESPACE_URIS
from .normalizer import normalize_metadata

RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDF_RESOURCE = f"{{{RDF_NS}}}resource"
RDF_DESCRIPTION = f"{{{RDF_NS}}}Description"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
# RDF syntax attributes that control parsing and are not metadata fields.
_RDF_CONTROL_ATTRIBUTES = {
    f"{{{RDF_NS}}}about",
    f"{{{RDF_NS}}}parseType",
    f"{{{RDF_NS}}}ID",
    f"{{{RDF_NS}}}nodeID",
    f"{{{RDF_NS}}}datatype",
    XML_LANG,
}
_RDF_ARRAYS = {f"{{{RDF_NS}}}Bag", f"{{{RDF_NS}}}Seq", f"{{{RDF_NS}}}Alt"}
_RDF_LI = f"{{{RDF_NS}}}li"


def parse_xmp(xmp_text: str | bytes) -> dict[str, Any]:
    """Parse an XMP packet and return normalized IPTC-style JSON keys.

    The parser intentionally extracts only ImageRegion data. Other XMP fields
    may be present in a sidecar or embedded packet, but they are outside the
    validator's scope.

    Args:
        xmp_text: XMP/XML text or bytes.

    Returns:
        Canonical metadata dictionary containing normalized `imageRegion`.

    Raises:
        xml.etree.ElementTree.ParseError: If the XML cannot be parsed.
    """

    normalized = normalize_metadata(xmp_image_region_data(xmp_text), source_format="xmp")
    return normalized.as_dict()


def xmp_image_region_data(xmp_text: str | bytes) -> dict[str, Any]:
    """Return the raw Image Region data of an XMP packet before normalization.

    Handles the RDF forms used by ExifTool, Exiv2, and other XMP writers:
    structures as `rdf:parseType="Resource"`, as nested `rdf:Description`, or
    as attributes. Property names keep their namespace prefix, such as
    `dc:description`, so additional Image Region fields get the same keys as
    when read through ExifTool or Exiv2.

    Args:
        xmp_text: XMP/XML text or bytes.

    Returns:
        Mapping with `imageRegion` and `imageRegionDepthOrder` when present.

    Raises:
        xml.etree.ElementTree.ParseError: If the XML cannot be parsed.
    """

    if isinstance(xmp_text, bytes):
        # Embedded XMP is expected to be UTF-8. Invalid bytes are ignored so a
        # larger binary image scan can still recover a readable packet.
        xmp_text = xmp_text.decode("utf-8", errors="ignore")
    xml_text = _extract_xml(xmp_text)
    root = ET.fromstring(xml_text)
    names = _NameMap(xml_text)

    metadata: dict[str, Any] = {}
    regions: list[Any] = []

    for element in root.iter():
        if _local_name(element.tag) == "ImageRegion":
            # IPTC ImageRegion is usually an rdf:Bag of resource structs, but
            # _parse_property also tolerates scalar or direct-struct forms.
            value = _parse_property(element, names)
            if isinstance(value, list):
                regions.extend(value)
            elif value not in (None, ""):
                regions.append(value)
        elif _local_name(element.tag) == "ImageRegionDepthOrder":
            # Iptc4xmpExt:ImageRegionDepthOrder is an rdf:Seq of Region Identifiers.
            value = _parse_property(element, names)
            if value not in (None, ""):
                metadata["imageRegionDepthOrder"] = value if isinstance(value, list) else [value]

    if regions:
        metadata["imageRegion"] = regions
    return metadata


def extract_xmp_packet(data: bytes) -> str | None:
    """Return the first embedded XMP packet found in a binary file.

    This is a lightweight fallback for images when the user does not route
    parsing through exiftool/exiv2. It searches for common XMP/RDF wrapper tags
    and returns the first complete packet it can find.

    Args:
        data: Binary file data.

    Returns:
        Extracted XMP/XML text, or None when no packet is found.
    """

    text = data.decode("utf-8", errors="ignore")
    for start_marker in ("<x:xmpmeta", "<rdf:RDF"):
        start = text.find(start_marker)
        if start < 0:
            continue
        end_marker = "</x:xmpmeta>" if start_marker == "<x:xmpmeta" else "</rdf:RDF>"
        end = text.find(end_marker, start)
        if end >= 0:
            return text[start : end + len(end_marker)]
    return None


class _NameMap:
    """Turn ElementTree `{uri}local` names into `prefix:local` property names.

    Well-known IPTC namespaces use their conventional prefix; other namespaces
    use the prefix declared in the packet.
    """

    def __init__(self, xml_text: str) -> None:
        self._prefixes: dict[str, str] = {}
        for _event, (prefix, uri) in ET.iterparse(io.StringIO(xml_text), events=("start-ns",)):
            if prefix:
                self._prefixes.setdefault(uri, prefix)
        self._prefixes.update({uri: prefix for prefix, uri in NAMESPACE_URIS.items()})

    def __call__(self, tag: str) -> str:
        if not tag.startswith("{"):
            return tag
        uri, local = tag[1:].split("}", 1)
        prefix = self._prefixes.get(uri)
        return f"{prefix}:{local}" if prefix else local


def _extract_xml(value: str) -> str:
    """Strip xpacket processing instructions and leading non-XML bytes."""

    stripped = value.strip()
    stripped = re.sub(r"^<\?xpacket[^>]*\?>", "", stripped).strip()
    stripped = re.sub(r"<\?xpacket[^>]*\?>$", "", stripped).strip()
    first = stripped.find("<")
    if first > 0:
        stripped = stripped[first:]
    return stripped


def _parse_property(element: ET.Element, names: _NameMap) -> Any:
    """Parse an RDF property element or rdf:li item.

    Returns a scalar, a list for rdf:Bag/rdf:Seq, a language mapping for
    rdf:Alt, or a dictionary for a structure in any of the RDF forms.
    """

    children = list(element)
    if not children:
        fields = _attribute_fields(element, names)
        # A structure written entirely as attributes, e.g. <rdf:li rbX="1" rbY="2"/>.
        return fields if fields else _element_scalar(element)

    if len(children) == 1 and children[0].tag in _RDF_ARRAYS:
        if children[0].tag == f"{{{RDF_NS}}}Alt":
            return _parse_alt(children[0])
        return [_parse_property(item, names) for item in children[0] if item.tag == _RDF_LI]
    if len(children) == 1 and children[0].tag == RDF_DESCRIPTION:
        # A structure written as a nested rdf:Description node (Exiv2 style).
        return _parse_struct(children[0], names)
    return _parse_struct(element, names)


def _parse_alt(element: ET.Element) -> dict[str, str]:
    """Parse rdf:Alt language alternatives into a lang-to-text mapping."""

    values: dict[str, str] = {}
    for item in element:
        if item.tag != _RDF_LI:
            continue
        lang = item.attrib.get(XML_LANG, "x-default")
        values[lang] = _element_scalar(item)
    return values


def _parse_struct(element: ET.Element, names: _NameMap) -> dict[str, Any]:
    """Parse an RDF structure from attributes and child property elements."""

    result = _attribute_fields(element, names)
    if RDF_RESOURCE in element.attrib:
        # rdf:resource is commonly used for URI references.
        result["identifier"] = element.attrib[RDF_RESOURCE]
    for child in element:
        if child.tag == _RDF_LI:
            continue
        _merge(result, names(child.tag), _parse_property(child, names))
    return result


def _attribute_fields(element: ET.Element, names: _NameMap) -> dict[str, Any]:
    """Return structure fields written as XML attributes."""

    result: dict[str, Any] = {}
    for attr_name, attr_value in element.attrib.items():
        if attr_name in _RDF_CONTROL_ATTRIBUTES or attr_name == RDF_RESOURCE:
            continue
        _merge(result, names(attr_name), attr_value)
    return result


def _element_scalar(element: ET.Element) -> str:
    """Return a scalar text value or rdf:resource URI for an element.

    XMP text values are returned unchanged; leading and trailing whitespace is
    part of the value.
    """

    if RDF_RESOURCE in element.attrib:
        return element.attrib[RDF_RESOURCE]
    return element.text or ""


def _merge(target: dict[str, Any], key: str, value: Any) -> None:
    """Merge repeated XML properties into lists without dropping values."""

    if key not in target:
        target[key] = value
        return
    current = target[key]
    if isinstance(current, list):
        current.append(value)
    else:
        target[key] = [current, value]


def _local_name(tag: str) -> str:
    """Remove an XML namespace from an ElementTree tag name."""

    return tag.split("}")[-1]
