"""Normalize IPTC Image Region metadata from JSON and metadata-tool tag names."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .builder import build_metadata
from .iptc_registry import DEFAULT_IPTC_REGISTRY
from .models import NormalizedMetadata
from .spec import DEFAULT_STANDARD, Standard

_INDEXED_SEGMENT = re.compile(r"^(?P<name>[^\[\]]+)(?:\[(?P<index>\d+)])?$")
_LANG_ALT_TEXT = re.compile(r"""^lang=(?P<quote>["'])(?P<language>[^"']+)(?P=quote)\s*(?P<text>.*)$""")
_LANG_ALT_ITEMS = re.compile(
    r"""(?:^|,\s*)lang=(?P<quote>["'])(?P<language>[^"']+)(?P=quote)\s*(?P<text>.*?)(?=,\s*lang=["']|$)"""
)
_LANG_ALT_SUFFIX = re.compile(r"^(?P<base>.+)-(?P<language>[a-z]{2,3}(?:-[A-Za-z]{2,8})?|x-default)$")


# Tool and XML outputs use different spelling/casing conventions for the same
# IPTC Image Region concepts. Region aliases are applied only after the parser
# has entered an ImageRegion path or while normalizing ImageRegion values.
_ALIASES_REGION = {
    "imageregion": "imageRegion",
    "regionboundary": "regionBoundary",
    "rbshape": "rbShape",
    "rbunit": "rbUnit",
    "rbx": "rbX",
    "rby": "rbY",
    "rbw": "rbW",
    "rbh": "rbH",
    "rbrx": "rbRx",
    "rbvertices": "rbVertices",
    "rbcoordinates": "rbCoordinates",
    "rbmbpartdetails": "rbMbPartDetails",
    "rbmbpdpartindex": "rbMbPdPartIndex",
    "rbmbpdpartid": "rbMbPdPartId",
    "rbmbpdpartname": "rbMbPdPartName",
    "rbmbpdpartdescription": "rbMbPdPartDescription",
    "rid": "rId",
    "rctype": "rCtype",
    "rrole": "rRole",
    "rmemberof": "rMemberOf",
    "imageregionmemberof": "rMemberOf",
    "identifier": "identifiers",
    "identifiers": "identifiers",
    "name": "name",
    "role": "role",
    "cvtermid": "cvTermId",
    "cvtermname": "cvTermName",
}

# Image-level aliases are needed only to get dimensions for pixel validation.
_ALIASES_IMG_PROP = {
    "imagewidth": "imageWidth",
    "exifimagewidth": "imageWidth",
    "sourceimagewidth": "imageWidth",
    "imageheight": "imageHeight",
    "imageimageheight": "imageHeight",
    "exifimageheight": "imageHeight",
    "sourceimageheight": "imageHeight",
    "imageregiondepthorder": "imageRegionDepthOrder",
}

# Prefixes such as Xmp, rdf, and Iptc4xmpExt are transport details, not part of
# the Image Region path. They are ignored until the parser sees ImageRegion.
_IGNORED_PREFIXES = {
    "xmp",
    "xmp-iptcext",
    "iptcext",
    "iptc4xmpext",
    "rdf",
    "xml",
    "xmlns",
    "exif",
    "file",
}


def normalize_metadata(
    data: Any, *, source_format: str = "unknown", standard: Standard = DEFAULT_STANDARD
) -> NormalizedMetadata:
    """Normalize common IPTC Image Region representations into canonical JSON keys.

    The function intentionally accepts broad input because callers may provide
    already-normalized objects, plain imageRegion lists, ExifTool-style JSON, or
    flat Exiv2-style tag dictionaries. The returned object is always the narrow
    NormalizedMetadata shape consumed by validation.

    Args:
        data: Raw metadata in one of the supported external or canonical forms.
        source_format: Label describing the input source.
        standard: Validation profile, `"2025.1"` (default) or `"2026.1-draft"`.
            Reading never rejects content; the profile only affects validation.

    Returns:
        Normalized metadata with typed Image Region objects.
    """

    if isinstance(data, NormalizedMetadata):
        return data

    raw = data
    if isinstance(data, list):
        # exiftool -j returns a list of source-file objects. A bare list that is
        # not a single mapping is treated as an imageRegion array directly.
        if len(data) == 1 and isinstance(data[0], Mapping):
            data = data[0]
        else:
            data = {"imageRegion": data}

    if not isinstance(data, Mapping):
        # Non-object inputs cannot be normalized, but preserving raw data can
        # help callers diagnose what was supplied.
        return NormalizedMetadata(source_format=source_format, raw=raw).with_standard(standard)

    # First expand flat tool paths into nested dictionaries, then canonicalize
    # every key recursively.
    expanded = _expand_flat_mapping(data)
    normalized = _normalize_value(expanded, in_image_region=False)
    normalized = _normalize_image_region_lang_alts(normalized)
    if not isinstance(normalized, Mapping):
        normalized = {}

    return build_metadata(normalized, source_format=source_format, raw=raw, standard=standard)


def _normalize_value(value: Any, *, in_image_region: bool) -> Any:
    """Recursively canonicalize keys and coerce known array-valued fields.

    Args:
        value: Value to normalize.
        in_image_region: Whether key aliases should use Image Region names.

    Returns:
        Normalized value.
    """

    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, child in value.items():
            normalized_key = _canonical_key(str(key), in_image_region=in_image_region)
            child_in_image_region = in_image_region or normalized_key == "imageRegion"
            normalized_child = _normalize_value(child, in_image_region=child_in_image_region)
            if normalized_key in {"rbShape", "rbUnit"} and isinstance(normalized_child, str):
                normalized_child = normalized_child.casefold()
            if normalized_key == "rbMbPdPartIndex":
                normalized_child = _coerce_part_index(normalized_child)
            # Some IPTC fields are semantically arrays even if a source emits a
            # single object/string. Coercing here keeps validators simpler.
            prop = DEFAULT_IPTC_REGISTRY.get(normalized_key) if child_in_image_region else None
            if normalized_key in {
                "identifiers",
                "role",
                "rCtype",
                "rRole",
                "rbVertices",
                "rbMbPartDetails",
                "imageRegion",
                "imageRegionDepthOrder",
            } or (prop is not None and prop.cardinality == "multi"):
                normalized_child = _coerce_list(normalized_child)
            _merge_value(out, normalized_key, normalized_child)
        return out
    if isinstance(value, list):
        return [_normalize_value(item, in_image_region=in_image_region) for item in value]
    return value


def _coerce_part_index(value: Any) -> Any:
    """Return integer Part Index values for XMP text such as "0"."""

    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    return value


def _normalize_image_region_lang_alts(value: Any) -> Any:
    """Canonicalize Image Region LangAlt fields to language mappings."""

    if not isinstance(value, Mapping):
        return value

    image_regions = value.get("imageRegion")
    if not isinstance(image_regions, list):
        return value

    for region in image_regions:
        if not isinstance(region, dict):
            continue
        _fold_region_lang_alt_suffix_keys(region)
        if "name" in region:
            region["name"] = _lang_alt_value(region["name"])
        for key, child in list(region.items()):
            prop = DEFAULT_IPTC_REGISTRY.get(str(key))
            if prop is not None and prop.writer_type == "LangAlt":
                region[key] = _lang_alt_value(child)
        for key in ("rCtype", "rRole"):
            entities = region.get(key)
            if not isinstance(entities, list):
                continue
            for entity in entities:
                if isinstance(entity, dict) and "name" in entity:
                    entity["name"] = _lang_alt_value(entity["name"])
    return value


def _lang_alt_value(value: Any) -> Any:
    """Return a canonical LangAlt mapping for scalar language-alt text."""

    if isinstance(value, list):
        merged: dict[str, Any] = {}
        for item in value:
            if isinstance(item, Mapping):
                item_value = item
            elif isinstance(item, str) and (_LANG_ALT_TEXT.match(item) is not None or _parse_lang_alt_items(item)):
                item_value = _lang_alt_value(item)
            else:
                return value
            if isinstance(item_value, Mapping):
                merged.update(item_value)
            else:
                return value
        return merged or value
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str):
        return value
    alternatives = _parse_lang_alt_items(value)
    if alternatives is not None:
        return alternatives
    match = _LANG_ALT_TEXT.match(value)
    if match is not None:
        return {match.group("language"): match.group("text")}
    return {"x-default": value}


def _parse_lang_alt_items(value: str) -> dict[str, str] | None:
    """Parse Exiv2's comma-joined LangAlt display value."""

    matches = list(_LANG_ALT_ITEMS.finditer(value))
    if len(matches) < 2:
        return None
    alternatives = {}
    for match in matches:
        alternatives[match.group("language")] = match.group("text")
    return alternatives


def _fold_region_lang_alt_suffix_keys(region: dict[str, Any]) -> None:
    """Merge ExifTool ``Tag-lang`` keys into language-alternative mappings.

    ExifTool reports XMP language alternatives as separate keys such as
    ``Name-de`` or ``XMP-dc:Description-de``. They are folded into the region
    name and into every additional field that the IPTC registry defines as
    LangAlt, so all readers produce the same mapping.
    """

    groups: dict[str, dict[str, Any]] = {}
    for key in list(region):
        match = _LANG_ALT_SUFFIX.match(str(key))
        if match is None:
            continue
        target = _lang_alt_target(match.group("base"))
        if target is None:
            continue
        groups.setdefault(target, {})[match.group("language")] = region.pop(key)

    for target, alternatives in groups.items():
        existing = _lang_alt_value(region.get(target)) if target in region else None
        if isinstance(existing, Mapping):
            alternatives = {**existing, **alternatives}
        region[target] = alternatives


def _lang_alt_target(base: str) -> str | None:
    """Return the canonical key of a language-alternative field, or None."""

    canonical = _canonical_key(base, in_image_region=True)
    if canonical == "name":
        return canonical
    prop = DEFAULT_IPTC_REGISTRY.get(canonical)
    if prop is not None and prop.writer_type == "LangAlt":
        return prop.stable_key
    return None


def _expand_flat_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    """Expand tool paths like Xmp.iptcExt.ImageRegion[1]/... into objects."""

    out: dict[str, Any] = {}
    for key, value in data.items():
        path = _tokenize_key(str(key))
        if path == [("imageRegionDepthOrder", None)]:
            _merge_value(out, "imageRegionDepthOrder", value)
            continue
        if len(path) <= 1:
            _merge_value(out, str(key), value)
            continue
        _insert_path(out, path, value)
    return out


def _tokenize_key(key: str) -> list[tuple[str, int | None]]:
    """Turn a flat metadata key into canonical path segments.

    Exiv2 and similar tools encode hierarchy in tag names using separators such
    as '.', ':', '/', and optional one-based indexes. This tokenizer keeps only
    the Image Region path and image dimension fields relevant to validation.
    """

    if "ImageRegion" in key or "imageregion" in key.casefold():
        cleaned = key.replace("\\", "/").replace(".", "/")
    else:
        cleaned = key.replace("\\", "/").replace(":", "/").replace(".", "/")
    parts = [part for part in cleaned.split("/") if part]
    tokens: list[tuple[str, int | None]] = []
    seen_image_region = False

    for part in parts:
        match = _INDEXED_SEGMENT.match(part)
        if match is None:
            continue
        name = match.group("name")
        canonical = _canonical_key(name, in_image_region=seen_image_region)
        if canonical.casefold() in _IGNORED_PREFIXES:
            continue
        if canonical == "imageRegion":
            seen_image_region = True
        if not seen_image_region and canonical not in {"imageWidth", "imageHeight", "imageRegionDepthOrder"}:
            continue
        index = match.group("index")
        parsed_index = _parse_external_index(index) if index is not None else None
        tokens.append((canonical, parsed_index))
    return tokens


def _insert_path(root: dict[str, Any], path: list[tuple[str, int | None]], value: Any) -> None:
    """Insert a scalar value into a nested object/list path."""

    current: Any = root
    for position, (key, index) in enumerate(path):
        last = position == len(path) - 1
        if not isinstance(current, dict):  # pragma: no cover - defensive guard for corrupted traversal state.
            return
        if index is None:
            if last:
                _merge_value(current, key, value)
                return
            child = current.get(key)
            if not isinstance(child, dict):
                child = {}
                current[key] = child
            current = child
            continue

        items = current.get(key)
        if not isinstance(items, list):
            items = []
            current[key] = items
        while len(items) <= index:
            items.append({})
        if last:
            items[index] = value
            return
        if not isinstance(items[index], dict):
            items[index] = {}
        current = items[index]


def _canonical_key(key: str, *, in_image_region: bool) -> str:
    """Map one source key to the canonical spelling when it is recognized."""

    bare = key.split("}")[-1]
    bare_local = bare.split(":")[-1]
    token = re.sub(r"[^A-Za-z0-9]", "", bare_local).casefold()
    if token == "imageregion":
        return "imageRegion"
    if in_image_region:
        alias = _ALIASES_REGION.get(token)
        if alias is not None:
            return alias
        stable_key = DEFAULT_IPTC_REGISTRY.stable_key(bare)
        if stable_key is not None:
            return stable_key
        return bare
    return _ALIASES_IMG_PROP.get(token, bare)


def _merge_value(target: dict[str, Any], key: str, value: Any) -> None:
    """Merge duplicate keys without losing repeated metadata values."""

    if key not in target:
        target[key] = value
        return
    current = target[key]
    if isinstance(current, list):
        if isinstance(value, list):
            current.extend(value)
        else:
            current.append(value)
        return
    if isinstance(value, list):
        target[key] = [current, *value]
    else:
        target[key] = [current, value]


def _coerce_list(value: Any) -> list[Any]:
    """Return a list for fields that can be emitted as one-or-many values."""

    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _parse_external_index(value: str | None) -> int | None:
    """Convert external one-based indexes to Python zero-based indexes."""

    if value is None:
        return None
    parsed = int(value)
    if parsed > 0:
        return parsed - 1
    return 0
