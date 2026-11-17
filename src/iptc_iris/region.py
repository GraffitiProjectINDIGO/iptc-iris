"""Typed IPTC Image Region domain objects."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any
from urllib.parse import urlparse

from .geometry import (
    BoundaryUnit,
    CircleBoundary,
    CoordinateBoundary,
    InvalidBoundary,
    MissingBoundary,
    PolygonBoundary,
    RectangleBoundary,
    RegionBoundary,
    UnknownBoundary,
)
from .models import ValidationIssue, ValidationResult
from .spec import DEFAULT_STANDARD, ENTITY_ARRAY_KEYS, Standard, require_standard

REGION_KEYS = {"rId", "name", "regionBoundary", "rCtype", "rRole", "rMemberOf"}


@dataclass(frozen=True)
class ImageRegion:
    """One parsed Image Region with a typed boundary object.

    Attributes:
        boundary: Typed region boundary.
        r_id: Optional IPTC region identifier.
        name: Optional string or language-alternative region name.
        r_ctype: Optional region content type Entity array.
        r_role: Optional region role Entity array.
        r_member_of: Optional identifier of this region's semantic lead region.
        image_width: Optional source image width for pixel validation.
        image_height: Optional source image height for pixel validation.
        defer_dimensions: Whether pixel dimensions may be supplied later.
        allow_malformed: Whether malformed parsed input is preserved.
        extra: Extra fields outside the validated Image Region subset.
        raw: Original raw region mapping.
    """

    boundary: RegionBoundary = field(default_factory=MissingBoundary)
    r_id: Any = None
    name: Any = None
    r_ctype: Any = None
    r_role: Any = None
    image_width: float | int | None = None
    image_height: float | int | None = None
    defer_dimensions: bool = False
    allow_malformed: bool = False
    extra: Mapping[str, Any] = field(default_factory=dict)
    raw: Mapping[str, Any] = field(default_factory=dict)
    r_member_of: Any = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        """Normalize dimensions and enforce pixel-region dimension rules.

        Raises:
            ValueError: If image dimensions are invalid or required for a pixel
                boundary and not deferred.
        """

        object.__setattr__(self, "image_width", _normalize_dimension(self.image_width, "image_width"))
        object.__setattr__(self, "image_height", _normalize_dimension(self.image_height, "image_height"))
        if not self._missing_dimensions():
            object.__setattr__(self, "defer_dimensions", False)
        if (
            not self.allow_malformed
            and not self.defer_dimensions
            and _uses_pixel_unit(self)
            and self._missing_dimensions()
        ):
            _raise_missing_image_dimensions()

    @classmethod
    def from_parts(
        cls,
        *,
        boundary: RegionBoundary,
        raw: dict[str, Any],
        extra: dict[str, Any],
        image_width: float | int | None = None,
        image_height: float | int | None = None,
        defer_dimensions: bool = False,
        allow_malformed: bool = False,
    ) -> ImageRegion:
        """Create a region while keeping common IPTC fields easily accessible.

        Args:
            boundary: Typed boundary object.
            raw: Raw region mapping containing common IPTC fields.
            extra: Extra fields not modeled directly.
            image_width: Optional source image width.
            image_height: Optional source image height.
            defer_dimensions: Allow pixel dimensions to be supplied later.
            allow_malformed: Preserve malformed input instead of raising.

        Returns:
            Constructed Image Region.

        Raises:
            ValueError: If pixel dimensions are required and not deferred.
        """

        return cls(
            boundary=boundary,
            r_id=raw.get("rId"),
            name=raw.get("name"),
            r_ctype=raw.get("rCtype"),
            r_role=raw.get("rRole"),
            r_member_of=raw.get("rMemberOf"),
            image_width=image_width,
            image_height=image_height,
            defer_dimensions=defer_dimensions,
            allow_malformed=allow_malformed,
            extra=extra,
            raw=raw,
        )

    @classmethod
    def from_raw(
        cls,
        raw: Any,
        *,
        image_width: float | int | None = None,
        image_height: float | int | None = None,
        defer_dimensions: bool = False,
        allow_malformed: bool = False,
    ) -> ImageRegion:
        """Create a region from canonical raw Image Region data.

        Args:
            raw: Canonical Image Region mapping or existing `ImageRegion`.
            image_width: Optional source image width.
            image_height: Optional source image height.
            defer_dimensions: Allow pixel dimensions to be supplied later.
            allow_malformed: Preserve malformed input instead of raising.

        Returns:
            Parsed Image Region.

        Raises:
            ValueError: If the raw value is invalid and malformed input is not
                allowed, or if required pixel dimensions are missing.
        """

        if isinstance(raw, ImageRegion):
            return raw.with_dimensions(image_width=image_width, image_height=image_height)

        if not isinstance(raw, Mapping):
            if not allow_malformed:
                raise ValueError("Image Region entry must be an object.")
            raw_snapshot = _freeze_mapping({"raw": raw})
            return cls(
                raw=raw_snapshot,
                extra=raw_snapshot,
                image_width=image_width,
                image_height=image_height,
                defer_dimensions=defer_dimensions,
                allow_malformed=allow_malformed,
            )

        raw_dict = dict(raw)
        region = cls(
            boundary=_boundary_from_raw(raw_dict.get("regionBoundary"), allow_malformed=allow_malformed),
            r_id=raw_dict.get("rId"),
            name=raw_dict.get("name"),
            r_ctype=raw_dict.get("rCtype"),
            r_role=raw_dict.get("rRole"),
            r_member_of=raw_dict.get("rMemberOf"),
            image_width=image_width,
            image_height=image_height,
            defer_dimensions=defer_dimensions,
            allow_malformed=allow_malformed,
            extra=_freeze_mapping({key: value for key, value in raw_dict.items() if key not in REGION_KEYS}),
            raw=_freeze_mapping(raw_dict),
        )
        if not allow_malformed:
            _raise_if_errors(region.validate(image_width=None, image_height=None, ignore_dimensions=True))
        return region

    def with_dimensions(
        self,
        *,
        image_width: float | int | None = None,
        image_height: float | int | None = None,
    ) -> ImageRegion:
        """Return a copy with image dimensions set for pixel-boundary validation.

        Args:
            image_width: Optional replacement image width.
            image_height: Optional replacement image height.

        Returns:
            Region with dimensions applied, or the original region when no
            values change.

        Raises:
            ValueError: If provided dimensions are invalid.
        """

        width = self.image_width if image_width is None else image_width
        height = self.image_height if image_height is None else image_height
        if width == self.image_width and height == self.image_height:
            return self
        return ImageRegion(
            boundary=self.boundary,
            r_id=self.r_id,
            name=self.name,
            r_ctype=self.r_ctype,
            r_role=self.r_role,
            r_member_of=self.r_member_of,
            image_width=width,
            image_height=height,
            defer_dimensions=self.defer_dimensions,
            allow_malformed=self.allow_malformed,
            extra=self.extra,
            raw=self.raw,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return the canonical JSON-compatible Image Region object.

        Returns:
            Canonical Image Region dictionary.

        Raises:
            ValueError: If the boundary cannot be exported because it is
                malformed.
        """

        data = dict(self.extra)
        if self.r_id is not None:
            data["rId"] = self.r_id
        if self.name is not None:
            data["name"] = self.name
        if self.r_ctype is not None:
            data["rCtype"] = self.r_ctype
        if self.r_role is not None:
            data["rRole"] = self.r_role
        if self.r_member_of is not None:
            data["rMemberOf"] = self.r_member_of
        if not isinstance(self.boundary, MissingBoundary):
            data["regionBoundary"] = self.boundary.as_dict()
        return data

    def as_diagnostic_dict(self) -> dict[str, Any]:
        """Return Image Region data without rejecting malformed boundaries.

        This is intended for diagnostics and editor UIs that need to show or
        store the original parsed fields even when `as_dict()` would reject an
        invalid boundary.

        Returns:
            Canonical-looking Image Region dictionary with malformed boundary
            fields preserved where possible.
        """

        data = dict(self.extra)
        if self.r_id is not None:
            data["rId"] = self.r_id
        if self.name is not None:
            data["name"] = self.name
        if self.r_ctype is not None:
            data["rCtype"] = self.r_ctype
        if self.r_role is not None:
            data["rRole"] = self.r_role
        if self.r_member_of is not None:
            data["rMemberOf"] = self.r_member_of

        boundary = self.boundary
        if isinstance(boundary, MissingBoundary):
            return data
        if boundary.valid:
            data["regionBoundary"] = boundary.as_dict()
        else:
            data["regionBoundary"] = boundary._dict_existing()
        return data

    def validate_boundary(
        self,
        path: str | None,
        *,
        image_width: float | None,
        image_height: float | None,
        ignore_dimensions: bool = False,
    ) -> list[ValidationIssue]:
        """Validate this region's boundary object.

        Args:
            path: JSON-style region path.
            image_width: Optional image width for pixel bounds.
            image_height: Optional image height for pixel bounds.
            ignore_dimensions: Skip missing image-dimension checks.

        Returns:
            Boundary validation issues.
        """

        if path is None:
            path = "ImgRegion"
        return self.boundary.validate(
            f"{path}.regionBoundary",
            image_width=image_width,
            image_height=image_height,
            ignore_dimensions=ignore_dimensions,
        )

    def validate(
        self,
        path: str | None = None,
        *,
        image_width: float | None = None,
        image_height: float | None = None,
        ignore_dimensions: bool = False,
    ) -> list[ValidationIssue]:
        """Validate this region's known fields and boundary object.

        Args:
            path: JSON-style region path.
            image_width: Optional image width overriding the region value.
            image_height: Optional image height overriding the region value.
            ignore_dimensions: Skip missing image-dimension checks.

        Returns:
            Validation issues for this region.

        Raises:
            ValueError: If pixel validation requires missing image dimensions.
        """

        if path is None:
            path = "ImgRegion"
        width = self.image_width if image_width is None else image_width
        height = self.image_height if image_height is None else image_height
        if not ignore_dimensions and _uses_pixel_unit(self) and (width is None or height is None):
            _raise_missing_image_dimensions()

        issues: list[ValidationIssue] = []
        issues.extend(self._validate_id(path))
        issues.extend(self._validate_name(path))
        issues.extend(self._validate_entities(path))
        issues.extend(self._validate_member_of(path))
        issues.extend(
            self.validate_boundary(
                path,
                image_width=width,
                image_height=height,
                ignore_dimensions=ignore_dimensions,
            )
        )
        return issues

    def change_unit(
        self,
        unit: BoundaryUnit,
        *,
        image_width: float | int,
        image_height: float | int,
        allow_malformed: bool = False,
    ) -> ImageRegion:
        """Return a copy with its boundary converted to another measuring unit.

        Args:
            unit: Target unit, either `pixel` or `relative`.
            image_width: Source image width used for conversion.
            image_height: Source image height used for conversion.
            allow_malformed: Preserve converted values even when they fail
                validation, such as out-of-image relative coordinates.

        Returns:
            Region copy with converted boundary coordinates.

        Raises:
            ValueError: If the target unit, image dimensions, or boundary values
                are invalid.
        """

        return ImageRegion(
            boundary=self.boundary.change_unit(
                unit,
                image_width=image_width,
                image_height=image_height,
                allow_malformed=allow_malformed,
            ),
            r_id=self.r_id,
            name=self.name,
            r_ctype=self.r_ctype,
            r_role=self.r_role,
            r_member_of=self.r_member_of,
            image_width=image_width,
            image_height=image_height,
            defer_dimensions=False,
            allow_malformed=self.allow_malformed or allow_malformed,
            extra=self.extra,
            raw=self.raw,
        )

    def _validate_member_of(self, path: str) -> list[ValidationIssue]:
        """Validate the scalar reference; target and cycle checks need the collection."""

        target = self.r_member_of
        if target is None and "rMemberOf" not in self.raw:
            return []
        if not isinstance(target, str):
            return [
                ValidationIssue(
                    "error", "REGION_MEMBER_OF_NOT_STRING", f"{path}.rMemberOf", "rMemberOf must be a single string."
                )
            ]
        if isinstance(self.r_id, str) and target == self.r_id:
            return [
                ValidationIssue(
                    "error",
                    "REGION_MEMBER_OF_SELF_REFERENCE",
                    f"{path}.rMemberOf",
                    "rMemberOf must reference another Image Region, not itself.",
                )
            ]
        return []

    def _missing_dimensions(self) -> bool:
        """Return whether this region lacks width or height.

        Returns:
            True when at least one image dimension is missing.
        """

        return self.image_width is None or self.image_height is None

    @property
    def errors(self) -> list[ValidationIssue]:
        """Return validation errors for this region."""

        return [issue for issue in self.validate() if issue.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Return validation warnings for this region."""

        return [issue for issue in self.validate() if issue.severity == "warning"]

    @property
    def valid(self) -> bool:
        """Return whether this region has no validation errors."""

        return not self.errors

    def _validate_id(self, path: str) -> list[ValidationIssue]:
        """Validate the optional region identifier field.

        Args:
            path: JSON-style path prefix for validation issues.

        Returns:
            Validation issues for `rId`.
        """

        if self.r_id is None:
            return []
        if not isinstance(self.r_id, str):
            return [ValidationIssue("error", "REGION_ID_NOT_STRING", f"{path}.rId", "rId must be a string.")]
        if not self.r_id.strip():
            return [ValidationIssue("warning", "EMPTY_REGION_ID", f"{path}.rId", "rId is empty.")]
        return []

    def _validate_name(self, path: str) -> list[ValidationIssue]:
        """Validate region names in string or language-alternative form.

        Args:
            path: JSON-style path prefix for validation issues.

        Returns:
            Validation issues for `name`.
        """

        if self.name is None:
            return []
        if isinstance(self.name, str):
            if self.name.strip():
                return []
            return [ValidationIssue("warning", "EMPTY_REGION_NAME", f"{path}.name", "Region name is empty.")]
        if not isinstance(self.name, Mapping):
            return [
                ValidationIssue(
                    "error",
                    "REGION_NAME_INVALID",
                    f"{path}.name",
                    "Region name must be a string or language-to-string mapping.",
                )
            ]

        issues: list[ValidationIssue] = []
        if not self.name:
            issues.append(ValidationIssue("warning", "EMPTY_REGION_NAME", f"{path}.name", "Region name is empty."))
        for language, text in self.name.items():
            language_path = f"{path}.name.{language}"
            if not isinstance(language, str) or not language:
                issues.append(
                    ValidationIssue(
                        "error",
                        "REGION_NAME_LANGUAGE_INVALID",
                        language_path,
                        "Region name language keys must be non-empty strings.",
                    )
                )
            if not isinstance(text, str):
                issues.append(
                    ValidationIssue(
                        "error",
                        "REGION_NAME_VALUE_INVALID",
                        language_path,
                        "Region name values must be strings.",
                    )
                )
            elif not text.strip():
                issues.append(ValidationIssue("warning", "EMPTY_REGION_NAME", language_path, "Region name is empty."))
        return issues

    def _validate_entities(self, path: str) -> list[ValidationIssue]:
        """Validate optional region Entity arrays.

        Args:
            path: JSON-style path prefix for validation issues.

        Returns:
            Validation issues for `rCtype` and `rRole`.
        """

        issues: list[ValidationIssue] = []
        values = {"rCtype": self.r_ctype, "rRole": self.r_role}
        for key in ENTITY_ARRAY_KEYS:
            if values[key] is not None:
                issues.extend(_validate_entity_array(values[key], f"{path}.{key}"))
        return issues


class ImageRegionList:
    """List-like container for creating and managing ImageRegion objects.

    Attributes:
        image_width: Optional shared image width.
        image_height: Optional shared image height.
        depth_order: Optional Image Region Depth Order
            (`imageRegionDepthOrder`): Region Identifiers ordered from the
            region closest to the viewer. None means the property is absent.
        standard: Validation profile, `"2025.1"` (default, the published IPTC
            standard) or `"2026.1-draft"` (adds the 2026.1 draft features).
    """

    def __init__(
        self,
        regions: ImageRegion | list[ImageRegion] | None = None,
        *,
        image_width: float | int | None = None,
        image_height: float | int | None = None,
        depth_order: list[str] | None = None,
        standard: Standard = DEFAULT_STANDARD,
        validate: bool = True,
    ) -> None:
        """Create a list-like Image Region container.

        Args:
            regions: One region, a list of regions, or None for an empty list.
            image_width: Optional image width shared by child regions.
            image_height: Optional image height shared by child regions.
            depth_order: Optional Region Identifiers ordered from the region
                closest to the viewer.
            standard: Validation profile, `"2025.1"` or `"2026.1-draft"`.
            validate: Whether to reject invalid collection state immediately.

        Raises:
            ValueError: If dimensions are invalid or validation finds errors.
        """

        self.image_width = _normalize_dimension(image_width, "image_width")
        self.image_height = _normalize_dimension(image_height, "image_height")
        self.depth_order: Any = list(depth_order) if isinstance(depth_order, list) else depth_order
        self.standard: Standard = require_standard(standard)
        if regions is None:
            self._regions = []
        elif isinstance(regions, ImageRegion):
            self._regions = [self._with_list_dimensions(regions)]
        else:
            self._regions = [self._with_list_dimensions(region) for region in regions]
        if self.image_width is None:
            self.image_width = _infer_region_dimension(self._regions, "image_width")
        if self.image_height is None:
            self.image_height = _infer_region_dimension(self._regions, "image_height")
        if self.image_width is not None or self.image_height is not None:
            self._regions = [self._with_list_dimensions(region) for region in self._regions]
        if validate:
            self._raise_if_invalid()

    @classmethod
    def from_raw(
        cls,
        regions: Any,
        *,
        image_width: float | int | None = None,
        image_height: float | int | None = None,
        allow_malformed: bool = False,
        validate: bool | None = None,
        depth_order: Any = None,
        standard: Standard = DEFAULT_STANDARD,
    ) -> ImageRegionList:
        """Create a region list from canonical raw Image Region data.

        Args:
            regions: Raw one-or-many Image Region values.
            image_width: Optional shared image width.
            image_height: Optional shared image height.
            depth_order: Optional raw `imageRegionDepthOrder` value.
            standard: Validation profile, `"2025.1"` or `"2026.1-draft"`.
            allow_malformed: Preserve malformed input instead of raising.
            validate: Override whether to validate immediately.

        Returns:
            Parsed Image Region list.

        Raises:
            ValueError: If validation fails and immediate validation is enabled.
        """

        parsed_regions = [
            item.with_dimensions(image_width=image_width, image_height=image_height)
            if isinstance(item, ImageRegion)
            else ImageRegion.from_raw(
                item,
                image_width=image_width,
                image_height=image_height,
                allow_malformed=allow_malformed,
            )
            for item in _coerce_region_list(regions)
        ]
        if validate is None:
            validate = not allow_malformed
        if isinstance(depth_order, str):
            depth_order = [depth_order]
        return cls(
            parsed_regions,
            image_width=image_width,
            image_height=image_height,
            depth_order=depth_order,
            standard=standard,
            validate=validate,
        )

    def __iter__(self):
        """Return an iterator over contained regions.

        Returns:
            Iterator over `ImageRegion` objects.
        """

        return iter(self._regions)

    def __len__(self) -> int:
        """Return the number of contained regions.

        Returns:
            Region count.
        """

        return len(self._regions)

    def __getitem__(self, index: int) -> ImageRegion:
        """Return a region by index.

        Args:
            index: Zero-based region index.

        Returns:
            The selected region.

        Raises:
            IndexError: If the index is out of range.
        """

        return self._regions[index]

    def as_list(self) -> list[ImageRegion]:
        """Return a shallow copy of the contained regions.

        Returns:
            List of contained regions.
        """

        return list(self._regions)

    def as_dict_list(self) -> list[dict[str, Any]]:
        """Return canonical JSON-compatible Image Region objects.

        Returns:
            List of canonical Image Region dictionaries.

        Raises:
            ValueError: If any contained region cannot be exported because it is
                malformed.
        """

        return [region.as_dict() for region in self._regions]

    def as_diagnostic_dict_list(self) -> list[dict[str, Any]]:
        """Return Image Region dictionaries preserving malformed boundaries.

        Returns:
            List of canonical-looking Image Region dictionaries suitable for
            diagnostics and editor UIs.
        """

        return [region.as_diagnostic_dict() for region in self._regions]

    def with_standard(self, standard: Standard) -> ImageRegionList:
        """Return a copy of this list that validates against another standard profile."""

        if require_standard(standard) == self.standard:
            return self
        return ImageRegionList(
            self._regions,
            image_width=self.image_width,
            image_height=self.image_height,
            depth_order=self.depth_order,
            standard=standard,
            validate=False,
        )

    def validate(self, *, ignore_dimensions: bool = False, standard: Standard | None = None) -> list[ValidationIssue]:
        """Validate contained regions using the optional image dimensions.

        Args:
            ignore_dimensions: Skip missing image-dimension checks for pixel
                boundaries.
            standard: Validate against this profile instead of `self.standard`.

        Returns:
            Collection-level and child-region validation issues.

        Raises:
            ValueError: If pixel validation requires missing image dimensions.
        """

        return self.validation_result(ignore_dimensions=ignore_dimensions, standard=standard).issues

    def validation_result(self, *, ignore_dimensions: bool = False, standard: Standard | None = None) -> ValidationResult:
        """Return detailed and overview validation issues for this region list.

        Args:
            ignore_dimensions: Skip missing image-dimension checks for pixel
                boundaries.
            standard: Validate against this profile instead of `self.standard`.

        Returns:
            Validation result with per-path issues and image/list-level overview
            issues.

        Raises:
            ValueError: If pixel validation requires missing image dimensions.
        """

        if (
            not ignore_dimensions
            and (self.image_width is None or self.image_height is None)
            and any(_uses_pixel_unit(region) for region in self._regions)
        ):
            _raise_missing_image_dimensions()

        result = ValidationResult()
        region_ids: dict[str, list[int]] = {}
        region_names: dict[str, list[int]] = {}
        region_boundaries: dict[str, list[int]] = {}

        for index, region in enumerate(self._regions):
            if isinstance(region.r_id, str) and region.r_id:
                region_ids.setdefault(region.r_id, []).append(index)
            region_name = _name_value(region.name)
            if region_name:
                region_names.setdefault(region_name, []).append(index)
            boundary_signature = _boundary_signature(region, self.image_width, self.image_height)
            if boundary_signature:
                region_boundaries.setdefault(boundary_signature, []).append(index)

        result.issues.extend(self._validate_memberships(region_ids))
        result.issues.extend(self._validate_depth_order(region_ids))

        for region_id, indexes in region_ids.items():
            if len(indexes) < 2:
                continue
            group_paths = tuple(f"imageRegion[{index}].rId" for index in indexes)
            group = ", ".join(f"imageRegion[{index}]" for index in indexes)
            message = f"Region identifier {region_id!r} is used by multiple Image Region entries: {group}."
            result.add_overview(
                "error",
                "DUPLICATE_REGION_ID",
                message,
                paths=group_paths,
                indexes=tuple(indexes),
            )
            for index in indexes:
                result.add(
                    "error",
                    "DUPLICATE_REGION_ID",
                    f"imageRegion[{index}].rId",
                    message,
                )

        for region_name, indexes in region_names.items():
            if len(indexes) < 2:
                continue
            group_paths = tuple(f"imageRegion[{index}].name" for index in indexes)
            group = ", ".join(f"imageRegion[{index}]" for index in indexes)
            message = f"Region name {region_name!r} is used by multiple Image Region entries: {group}."
            result.add_overview(
                "warning",
                "DUPLICATE_REGION_NAME",
                message,
                paths=group_paths,
                indexes=tuple(indexes),
            )
            for index in indexes:
                result.add(
                    "warning",
                    "DUPLICATE_REGION_NAME",
                    f"imageRegion[{index}].name",
                    message,
                )

        for _boundary_sig, indexes in region_boundaries.items():
            if len(indexes) < 2:
                continue
            group_paths = tuple(f"imageRegion[{index}].regionBoundary" for index in indexes)
            group = ", ".join(f"imageRegion[{index}]" for index in indexes)
            message = f"Region Boundary is identical to another Image Region boundary: {group}."
            result.add_overview(
                "warning",
                "DUPLICATE_REGION_BOUNDARY",
                message,
                paths=group_paths,
                indexes=tuple(indexes),
            )
            for index in indexes:
                result.add(
                    "warning",
                    "DUPLICATE_REGION_BOUNDARY",
                    f"imageRegion[{index}].regionBoundary",
                    message,
                )

        for index, region in enumerate(self._regions):
            path = f"imageRegion[{index}]"
            result.issues.extend(
                region.validate(
                    path,
                    image_width=float(self.image_width) if self.image_width is not None else None,
                    image_height=float(self.image_height) if self.image_height is not None else None,
                    ignore_dimensions=ignore_dimensions,
                )
            )
        if (standard or self.standard) == DEFAULT_STANDARD:
            result.issues = [issue for issue in result.issues if issue.code != "DEPRECATED_POLYGON_VERTICES"]
            result.issues.extend(self._issues_outside_2025_1())
        return result

    def _issues_outside_2025_1(self) -> list[ValidationIssue]:
        """Report content that the published 2025.1 standard does not define."""

        def outside(path: str, what: str) -> ValidationIssue:
            return ValidationIssue(
                "error",
                "NOT_IN_STANDARD",
                path,
                f"{what} is not part of IPTC Photo Metadata 2025.1; it is defined by the 2026.1 draft. "
                'Use standard="2026.1-draft" to allow it.',
            )

        issues: list[ValidationIssue] = []
        for index, region in enumerate(self._regions):
            path = f"imageRegion[{index}]"
            boundary = region.boundary
            boundary_path = f"{path}.regionBoundary"
            boundary_raw = getattr(boundary, "raw", None)
            if isinstance(boundary, CoordinateBoundary):
                issues.append(outside(f"{boundary_path}.rbShape", boundary.shape))
            elif isinstance(boundary, PolygonBoundary) and boundary.coordinates is not None:
                issues.append(outside(f"{boundary_path}.rbCoordinates", "rbCoordinates (including holes)"))
            if getattr(boundary, "part_details", None) is not None or (
                isinstance(boundary_raw, Mapping) and "rbMbPartDetails" in boundary_raw
            ):
                issues.append(outside(f"{boundary_path}.rbMbPartDetails", "rbMbPartDetails"))
            if region.r_member_of is not None or "rMemberOf" in region.raw:
                issues.append(outside(f"{path}.rMemberOf", "rMemberOf"))
        if self.depth_order is not None:
            issues.append(outside("imageRegionDepthOrder", "imageRegionDepthOrder"))
        return issues

    def _validate_depth_order(self, region_ids: dict[str, list[int]]) -> list[ValidationIssue]:
        """Validate Image Region Depth Order references against existing rIds."""

        if self.depth_order is None:
            return []
        path = "imageRegionDepthOrder"
        if not isinstance(self.depth_order, list):
            return [
                ValidationIssue(
                    "error",
                    "INVALID_DEPTH_ORDER",
                    path,
                    "imageRegionDepthOrder must be an array of Region Identifiers.",
                )
            ]
        issues: list[ValidationIssue] = []
        first_use: dict[str, int] = {}
        for index, r_id in enumerate(self.depth_order):
            item_path = f"{path}[{index}]"
            if not isinstance(r_id, str) or not r_id:
                issues.append(
                    ValidationIssue(
                        "error",
                        "INVALID_DEPTH_ORDER",
                        item_path,
                        "Depth order values must be non-empty Region Identifier strings.",
                    )
                )
                continue
            if r_id in first_use:
                issues.append(
                    ValidationIssue(
                        "error",
                        "DUPLICATE_DEPTH_ORDER_ID",
                        item_path,
                        f"Region identifier {r_id!r} occurs more than once in the depth order "
                        f"(see {path}[{first_use[r_id]}]).",
                    )
                )
                continue
            first_use[r_id] = index
            if r_id not in region_ids:
                issues.append(
                    ValidationIssue(
                        "error",
                        "UNKNOWN_DEPTH_ORDER_ID",
                        item_path,
                        f"Region identifier {r_id!r} in the depth order does not match an existing Image Region.",
                    )
                )
        return issues

    def _validate_memberships(self, region_ids: dict[str, list[int]]) -> list[ValidationIssue]:
        """Warn about unresolved references and reject cycles in resolved references."""

        issues: list[ValidationIssue] = []
        edges: dict[int, int] = {}
        for index, region in enumerate(self._regions):
            target = region.r_member_of
            if not isinstance(target, str) or target == region.r_id:
                continue
            targets = region_ids.get(target, [])
            if not targets:
                issues.append(
                    ValidationIssue(
                        "warning",
                        "UNRESOLVED_REGION_MEMBER_OF",
                        f"imageRegion[{index}].rMemberOf",
                        f"Referenced region {target!r} was not found; this membership reference is ignored.",
                    )
                )
            elif len(targets) == 1:
                edges[index] = targets[0]

        visited: set[int] = set()
        for start in edges:
            chain: list[int] = []
            positions: dict[int, int] = {}
            current = start
            while current in edges and current not in visited and current not in positions:
                positions[current] = len(chain)
                chain.append(current)
                current = edges[current]
            if current in positions:
                for index in chain[positions[current] :]:
                    issues.append(
                        ValidationIssue(
                            "error",
                            "REGION_MEMBER_OF_CYCLE",
                            f"imageRegion[{index}].rMemberOf",
                            "rMemberOf references must not form a cycle.",
                        )
                    )
            visited.update(chain)
        return issues

    @property
    def errors(self) -> list[ValidationIssue]:
        """Return validation errors for this region list."""

        return [issue for issue in self.validate() if issue.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Return validation warnings for this region list."""

        return [issue for issue in self.validate() if issue.severity == "warning"]

    @property
    def valid(self) -> bool:
        """Return whether this region list has no validation errors."""

        return not self.errors

    def change_unit(
        self,
        unit: BoundaryUnit,
        *,
        image_width: float | int | None = None,
        image_height: float | int | None = None,
        allow_malformed: bool = False,
    ) -> ImageRegionList:
        """Return a copy with all region boundaries converted to another measuring unit.

        Args:
            unit: Target unit, either `pixel` or `relative`.
            image_width: Optional image width overriding the list value.
            image_height: Optional image height overriding the list value.
            allow_malformed: Preserve converted values even when they fail
                validation, such as out-of-image relative coordinates.

        Returns:
            New list with converted region boundaries.

        Raises:
            ValueError: If dimensions are missing/invalid or a region cannot be
                converted.
        """

        width = self.image_width if image_width is None else image_width
        height = self.image_height if image_height is None else image_height
        if width is None or height is None:
            raise ValueError("image_width and image_height are required to change Image Region units.")
        return ImageRegionList(
            [
                region.change_unit(
                    unit,
                    image_width=width,
                    image_height=height,
                    allow_malformed=allow_malformed,
                )
                for region in self._regions
            ],
            image_width=width,
            image_height=height,
            depth_order=self.depth_order,
            standard=self.standard,
            validate=not allow_malformed,
        )

    def add_region(self, region: ImageRegion) -> None:
        """Add a region after checking the resulting collection is valid.

        Args:
            region: Region to add.

        Raises:
            ValueError: If adding the region would make the collection invalid.
        """

        region = self._with_list_dimensions(region)
        candidate = [*self._regions, region]
        self._validate_candidate(candidate)
        self._regions.append(region)

    def get_region(self, r_id: str) -> ImageRegion | None:
        """Return the first region with the requested rId.

        Args:
            r_id: Region identifier to look up.

        Returns:
            Matching region, or None.
        """

        for region in self._regions:
            if region.r_id == r_id:
                return region
        return None

    def rename_region(self, old_id: str, new_id: str) -> bool:
        """Change a Region Identifier and every reference to it.

        IPTC requires references to follow a changed Region Identifier, so
        this updates the region's `rId`, the `rMemberOf` of regions that
        reference it, and the Image Region Depth Order in one step.

        If several regions share `old_id`, only the first is renamed, and
        references are moved only when no region keeps `old_id`.

        Args:
            old_id: Current Region Identifier.
            new_id: New Region Identifier.

        Returns:
            True when a region was renamed, False when no region has `old_id`.

        Raises:
            ValueError: If `new_id` is empty or already used by another region.
        """

        if not isinstance(new_id, str) or not new_id:
            raise ValueError("new_id must be a non-empty Region Identifier string.")
        index = next((position for position, region in enumerate(self._regions) if region.r_id == old_id), None)
        if index is None:
            return False
        if new_id == old_id:
            return True
        if self.get_region(new_id) is not None:
            raise ValueError(f"Region identifier {new_id!r} is already used by another Image Region.")

        self._regions[index] = replace(self._regions[index], r_id=new_id)
        if self.get_region(old_id) is not None:
            return True
        self._regions = [
            replace(region, r_member_of=new_id) if region.r_member_of == old_id else region for region in self._regions
        ]
        if isinstance(self.depth_order, list):
            self.depth_order = [new_id if item == old_id else item for item in self.depth_order]
        return True

    def delete_region(self, r_id: str) -> bool:
        """Delete the first region with the requested rId.

        IPTC requires references to point to existing regions, so once no
        region has `r_id` any more, it is also removed from the Image Region
        Depth Order and from the `rMemberOf` of regions that were members of
        the deleted region. Those regions remain as independent regions.

        Args:
            r_id: Region identifier to remove.

        Returns:
            True when a region was removed.
        """

        for index, region in enumerate(self._regions):
            if region.r_id == r_id:
                del self._regions[index]
                if self.get_region(r_id) is None:
                    self._remove_references_to(r_id)
                return True
        return False

    def _remove_references_to(self, r_id: str) -> None:
        """Remove a Region Identifier from the depth order and from rMemberOf references."""

        if isinstance(self.depth_order, list):
            self.depth_order = [item for item in self.depth_order if item != r_id]
        self._regions = [
            replace(
                region,
                r_member_of=None,
                raw={key: value for key, value in region.raw.items() if key != "rMemberOf"},
            )
            if region.r_member_of == r_id
            else region
            for region in self._regions
        ]

    def _raise_if_invalid(self) -> None:
        """Raise the first validation error for the current collection.

        Raises:
            ValueError: If collection validation finds an error.
        """

        issues = self.validate()
        errors = [issue for issue in issues if issue.severity == "error"]
        if errors:
            first = errors[0]
            raise ValueError(f"{first.path}: {first.message}")

    def _validate_candidate(self, regions: list[ImageRegion]) -> None:
        """Validate a candidate collection before mutating this list.

        Args:
            regions: Candidate region list.

        Raises:
            ValueError: If the candidate collection is invalid.
        """

        candidate = ImageRegionList(
            regions,
            image_width=self.image_width,
            image_height=self.image_height,
            depth_order=self.depth_order,
            standard=self.standard,
            validate=False,
        )
        issues = candidate.validate()
        errors = [issue for issue in issues if issue.severity == "error"]
        if errors:
            first = errors[0]
            raise ValueError(f"{first.path}: {first.message}")

    def _with_list_dimensions(self, region: ImageRegion) -> ImageRegion:
        """Return a region copy with this list's dimensions applied.

        Args:
            region: Region to complete with list dimensions.

        Returns:
            The original region or a dimension-completed copy.
        """

        return region.with_dimensions(image_width=self.image_width, image_height=self.image_height)


def _validate_entity_array(value: Any, path: str) -> list[ValidationIssue]:
    """Validate IPTC Entity arrays such as rCtype and rRole."""

    issues: list[ValidationIssue] = []
    if not isinstance(value, list):
        issues.append(
            ValidationIssue("error", "ENTITY_ARRAY_EXPECTED", path, "Value must be an array of Entity objects.")
        )
        return issues

    for index, entity in enumerate(value):
        entity_path = f"{path}[{index}]"
        if not isinstance(entity, Mapping):
            issues.append(ValidationIssue("error", "ENTITY_NOT_OBJECT", entity_path, "Entity value must be an object."))
            continue
        identifiers = entity.get("identifiers", [])
        if not isinstance(identifiers, list):
            issues.append(
                ValidationIssue(
                    "error",
                    "IDENTIFIERS_NOT_ARRAY",
                    f"{entity_path}.identifiers",
                    "identifiers must be an array.",
                )
            )
            identifiers = []
        for id_index, identifier in enumerate(identifiers):
            if not isinstance(identifier, str) or not _is_uri(identifier):
                issues.append(
                    ValidationIssue(
                        "error",
                        "INVALID_URI",
                        f"{entity_path}.identifiers[{id_index}]",
                        "Entity identifier must be a URI.",
                    )
                )
        if not identifiers and "name" not in entity:
            issues.append(
                ValidationIssue("warning", "EMPTY_ENTITY", entity_path, "Entity has neither identifiers nor name.")
            )

    return issues


def _is_uri(value: str) -> bool:
    """Return whether a string looks like a URI for Entity identifiers."""

    parsed = urlparse(value)
    return bool(parsed.scheme and (parsed.netloc or parsed.scheme in {"urn", "tag"}))


def _name_value(value: Any) -> str | None:
    """Extract a comparable display name from string or lang-alt mappings."""

    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key in ("x-default", "en", "de"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                return candidate
    return None


def _boundary_signature(
    region: ImageRegion, image_width: float | int | None, image_height: float | int | None
) -> str | None:
    """Return a comparable canonical boundary signature for duplicate checks."""

    try:
        if image_width is not None and image_height is not None:
            boundary = (
                region.change_unit("relative", image_width=image_width, image_height=image_height)
                .as_dict()
                .get("regionBoundary")
            )
        else:
            boundary = region.as_dict().get("regionBoundary")
    except (TypeError, ValueError, AttributeError, KeyError):
        return None
    if not isinstance(boundary, Mapping):
        return None
    return json.dumps(boundary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _boundary_from_raw(value: Any, *, allow_malformed: bool) -> RegionBoundary:
    """Build the shape-specific boundary object for a canonical boundary dict."""

    if value is None:
        return MissingBoundary()
    if not isinstance(value, Mapping):
        return InvalidBoundary(value)

    raw = dict(value)
    shape = raw.get("rbShape")
    if shape == "rectangle":
        return RectangleBoundary.from_raw(raw, allow_malformed=allow_malformed)
    if shape == "circle":
        return CircleBoundary.from_raw(raw, allow_malformed=allow_malformed)
    if shape in {"point", "multipoint", "linestring", "multilinestring", "multipolygon"}:
        return CoordinateBoundary.from_raw(raw, allow_malformed=allow_malformed)
    if shape == "polygon":
        return PolygonBoundary.from_raw(raw, allow_malformed=allow_malformed)
    return UnknownBoundary(raw)


def _coerce_region_list(value: Any) -> list[Any]:
    """Return a list for one-or-many raw Image Region values."""

    if value is None:
        return []
    if isinstance(value, ImageRegionList):
        return value.as_list()
    if isinstance(value, ImageRegion):
        return [value]
    if isinstance(value, list):
        items: list[Any] = []
        for item in value:
            if isinstance(item, ImageRegionList):
                items.extend(item.as_list())
            else:
                items.append(item)
        return items
    return [value]


def _freeze_mapping(values: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return an immutable shallow source snapshot."""

    return MappingProxyType(dict(values))


def _raise_if_errors(issues: list[ValidationIssue]) -> None:
    """Raise the first error from a validation issue list.

    Args:
        issues: Validation issues to inspect.

    Raises:
        ValueError: If an error-severity issue exists.
    """

    errors = [issue for issue in issues if issue.severity == "error"]
    if not errors:
        return
    first = errors[0]
    raise ValueError(f"{first.path}: {first.message}")


def _raise_missing_image_dimensions() -> None:
    """Raise the standard missing-dimensions error for pixel boundaries.

    Raises:
        ValueError: Always raised with guidance for pixel validation.
    """

    raise ValueError(
        "image_width and image_height are required for complete validation of pixel Image Region boundaries. "
        "Use ignore_dimensions=True for structural validation without image dimensions."
    )


def _normalize_dimension(value: float | int | None, field_name: str) -> float | int | None:
    """Normalize and validate an optional image dimension.

    Args:
        value: Candidate dimension value.
        field_name: Name used in error messages.

    Returns:
        A positive finite dimension, or None.

    Raises:
        ValueError: If a provided dimension is not positive and finite.
    """

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{field_name} must be a number.")
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")
    return value


def _infer_region_dimension(regions: list[ImageRegion], field_name: str) -> float | int | None:
    """Infer a shared dimension from child regions.

    Args:
        regions: Regions to inspect.
        field_name: Region attribute to infer.

    Returns:
        The shared dimension, or None when no region provides one.

    Raises:
        ValueError: If child regions provide conflicting dimensions.
    """

    values = {value for region in regions if (value := getattr(region, field_name)) is not None}
    if not values:
        return None
    if len(values) > 1:
        raise ValueError(f"{field_name} must match across all Image Region entries.")
    return values.pop()


def _uses_pixel_unit(region: ImageRegion) -> bool:
    """Return whether a region currently uses pixel boundary units.

    Args:
        region: Region to inspect.

    Returns:
        True when the typed or raw boundary unit is `pixel`.
    """

    boundary = region.boundary
    unit = getattr(boundary, "unit", None)
    if unit == "pixel":
        return True
    raw = getattr(boundary, "raw", None)
    return isinstance(raw, Mapping) and raw.get("rbUnit") == "pixel"
