"""Build typed domain objects from canonical normalized dictionaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import NormalizedMetadata
from .region import ImageRegionList
from .spec import DEFAULT_STANDARD, Standard


def build_metadata(
    data: Mapping[str, Any], *, source_format: str, raw: Any, standard: Standard = DEFAULT_STANDARD
) -> NormalizedMetadata:
    """Build the typed metadata document from a canonical dictionary.

    Args:
        data: Canonical metadata mapping with optional `imageRegion`,
            `imageWidth`, and `imageHeight` fields.
        source_format: Label describing the original input format.
        raw: Original unnormalized input preserved for diagnostics.

    Returns:
        Normalized metadata with typed Image Region objects.
    """

    image_width = _to_float(data.get("imageWidth"))
    image_height = _to_float(data.get("imageHeight"))
    return NormalizedMetadata(
        image_regions=ImageRegionList.from_raw(
            data.get("imageRegion"),
            image_width=image_width,
            image_height=image_height,
            allow_malformed=True,
            validate=False,
            depth_order=data.get("imageRegionDepthOrder"),
            standard=standard,
        ),
        image_width=image_width,
        image_height=image_height,
        source_format=source_format,
        raw=raw,
    )


def _to_float(value: Any) -> float | None:
    """Coerce image dimensions to floats and ignore non-numeric values.

    Args:
        value: Raw dimension value, or a one-item list from metadata tools.

    Returns:
        Parsed float or None when the value is missing or invalid.
    """

    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
