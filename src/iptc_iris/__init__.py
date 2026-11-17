"""Public API exports for IPTC Image Region normalization and validation."""

from .addition_metadata import STANDARD_EXIF_TAGS, standard_exif_json
from .fixer import FixAction, FixResult, safe_fix_metadata
from .geometry import (
    CircleBoundary,
    CoordinateBoundary,
    LineStringBoundary,
    MultiboundaryPart,
    MultiLineStringBoundary,
    MultiPointBoundary,
    MultiPolygonBoundary,
    PointBoundary,
    PolygonBoundary,
    RectangleBoundary,
    Vertex,
    join_multiboundary_parts,
    split_multiboundary_parts,
)
from .io import (
    MetadataToolWarning,
    canonical_to_exiftool_image_regions,
    format_exiftool_image_region_arg,
    load_metadata_file,
    parse_metadata_text,
    run_metadata_tool,
    write_image_regions,
)
from .iptc_registry import DEFAULT_IPTC_REGISTRY, IptcProperty, IptcPropertyRegistry, load_iptc_registry
from .models import NormalizedMetadata, ValidationIssue, ValidationOverviewIssue, ValidationResult
from .normalizer import normalize_metadata
from .region import ImageRegion, ImageRegionList
from .render import format_annotated_image_region, format_image_region, format_validation
from .spec import DEFAULT_STANDARD, DRAFT_STANDARD, IPTC_STANDARDS, Standard
from .xmp import parse_xmp

__all__ = [
    "DEFAULT_STANDARD",
    "DRAFT_STANDARD",
    "IPTC_STANDARDS",
    "Standard",
    "CircleBoundary",
    "CoordinateBoundary",
    "FixAction",
    "FixResult",
    "ImageRegion",
    "ImageRegionList",
    "IptcProperty",
    "IptcPropertyRegistry",
    "MetadataToolWarning",
    "NormalizedMetadata",
    "LineStringBoundary",
    "MultiboundaryPart",
    "MultiLineStringBoundary",
    "MultiPointBoundary",
    "MultiPolygonBoundary",
    "PointBoundary",
    "PolygonBoundary",
    "RectangleBoundary",
    "STANDARD_EXIF_TAGS",
    "DEFAULT_IPTC_REGISTRY",
    "ValidationIssue",
    "ValidationOverviewIssue",
    "ValidationResult",
    "Vertex",
    "format_annotated_image_region",
    "join_multiboundary_parts",
    "split_multiboundary_parts",
    "canonical_to_exiftool_image_regions",
    "format_exiftool_image_region_arg",
    "format_image_region",
    "format_validation",
    "load_metadata_file",
    "load_iptc_registry",
    "normalize_metadata",
    "parse_metadata_text",
    "parse_xmp",
    "run_metadata_tool",
    "safe_fix_metadata",
    "standard_exif_json",
    "write_image_regions",
]
