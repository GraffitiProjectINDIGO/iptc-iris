"""Data models returned by normalization and validation operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .region import ImageRegionList
    from .spec import Standard

Severity = Literal["error", "warning", "info"]


@dataclass(slots=True)
class NormalizedMetadata:
    """Canonical typed metadata shape.

    The rest of the package accepts many external representations: canonical
    IPTC-style JSON, ExifTool structured JSON, Exiv2 flat key/value output, and
    XMP/XML structures. Normalization reduces all of those into this small
    shape so validation does not need to know where the metadata came from.

    Attributes:
        image_regions: Typed Image Region list.
        image_width: Optional source image width.
        image_height: Optional source image height.
        source_format: Label describing the input source.
        raw: Original unnormalized input.
    """

    image_regions: ImageRegionList = field(default_factory=lambda: _empty_image_region_list())
    image_width: float | None = None
    image_height: float | None = None
    source_format: str = "unknown"
    raw: Any = None

    def as_dict(self) -> dict[str, Any]:
        """Return the public JSON-style form used by callers and tests.

        Returns:
            Canonical metadata dictionary.

        Raises:
            ValueError: If a contained region cannot be exported because it is
                malformed.
        """

        data: dict[str, Any] = {"imageRegion": self.image_regions.as_dict_list()}
        if self.image_regions.depth_order is not None:
            data["imageRegionDepthOrder"] = self.image_regions.depth_order
        if self.image_width is not None:
            data["imageWidth"] = self.image_width
        if self.image_height is not None:
            data["imageHeight"] = self.image_height
        return data

    def as_diagnostic_dict(self) -> dict[str, Any]:
        """Return metadata while preserving malformed Image Region entries.

        Returns:
            Canonical metadata dictionary using a non-strict Image Region export
            suitable for diagnostics and editor UIs.
        """

        data: dict[str, Any] = {"imageRegion": self.image_regions.as_diagnostic_dict_list()}
        if self.image_regions.depth_order is not None:
            data["imageRegionDepthOrder"] = self.image_regions.depth_order
        if self.image_width is not None:
            data["imageWidth"] = self.image_width
        if self.image_height is not None:
            data["imageHeight"] = self.image_height
        return data

    @property
    def standard(self) -> Standard:
        """Return the validation profile of the contained Image Regions."""

        return self.image_regions.standard

    def with_standard(self, standard: Standard) -> NormalizedMetadata:
        """Return a copy that validates against another standard profile."""

        regions = self.image_regions.with_standard(standard)
        if regions is self.image_regions:
            return self
        return NormalizedMetadata(
            image_regions=regions,
            image_width=self.image_width,
            image_height=self.image_height,
            source_format=self.source_format,
            raw=self.raw,
        )

    def validate(self, *, ignore_dimensions: bool = False, standard: Standard | None = None) -> list[ValidationIssue]:
        """Return validation issues for this normalized metadata document.

        Args:
            ignore_dimensions: Skip missing image-dimension checks for pixel
                boundaries.
            standard: Validate against this profile instead of the data's own.

        Returns:
            Validation issues for the metadata document.

        Raises:
            ValueError: If pixel validation requires missing image dimensions.
        """

        if not self.image_regions and self.image_regions.depth_order is None:
            return [
                ValidationIssue(
                    "warning",
                    "NO_IMAGE_REGION",
                    "imageRegion",
                    "No IPTC Image Region entries found.",
                )
            ]
        return self.image_regions.validate(ignore_dimensions=ignore_dimensions, standard=standard)

    def validation_result(self, *, ignore_dimensions: bool = False, standard: Standard | None = None) -> ValidationResult:
        """Return validation issues wrapped in a result convenience object.

        Args:
            ignore_dimensions: Skip missing image-dimension checks for pixel
                boundaries.
            standard: Validate against this profile instead of the data's own.

        Returns:
            Validation result object.

        Raises:
            ValueError: If pixel validation requires missing image dimensions.
        """

        if not self.image_regions and self.image_regions.depth_order is None:
            return ValidationResult(
                issues=[
                    ValidationIssue(
                        "warning",
                        "NO_IMAGE_REGION",
                        "imageRegion",
                        "No IPTC Image Region entries found.",
                    )
                ]
            )
        return self.image_regions.validation_result(ignore_dimensions=ignore_dimensions, standard=standard)

    @property
    def errors(self) -> list[ValidationIssue]:
        """Return validation errors for this normalized metadata document."""

        if not self.image_regions and self.image_regions.depth_order is None:
            return []
        return self.image_regions.errors

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Return validation warnings for this normalized metadata document."""

        if not self.image_regions and self.image_regions.depth_order is None:
            return [
                ValidationIssue(
                    "warning",
                    "NO_IMAGE_REGION",
                    "imageRegion",
                    "No IPTC Image Region entries found.",
                )
            ]
        return self.image_regions.warnings

    @property
    def valid(self) -> bool:
        """Return whether this normalized metadata document has no validation errors."""

        if not self.image_regions and self.image_regions.depth_order is None:
            return True
        return self.image_regions.valid


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One validation finding tied to a stable JSON-style path.

    Attributes:
        severity: Issue severity: `error`, `warning`, or `info` (a hint, e.g. deprecated usage).
        code: Stable machine-readable issue code.
        path: JSON-style path to the affected field.
        message: Human-readable diagnostic message.
    """

    severity: Severity
    code: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationOverviewIssue:
    """One image/list-level validation finding with affected members.

    Overview issues summarize findings that belong to the image-region list as
    a whole, while `ValidationIssue` remains tied to a concrete JSON path. This
    is useful for logs, summaries, and other consumers that need one message per
    logical problem without losing the affected paths and indexes.

    Attributes:
        severity: Issue severity: `error`, `warning`, or `info` (a hint, e.g. deprecated usage).
        code: Stable machine-readable issue code.
        message: Human-readable diagnostic message.
        paths: JSON-style paths affected by this overview issue.
        indexes: Image Region indexes affected by this overview issue.
    """

    severity: Severity
    code: str
    message: str
    paths: tuple[str, ...] = ()
    indexes: tuple[int, ...] = ()


@dataclass(slots=True)
class ValidationResult:
    """Collected validation findings plus convenience views.

    Attributes:
        issues: Collected validation issues.
        overview_issues: Image/list-level summaries of grouped validation issues.
    """

    issues: list[ValidationIssue] = field(default_factory=list)
    overview_issues: list[ValidationOverviewIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        """Return only error-severity validation issues.

        Returns:
            Validation issues whose severity is `error`.
        """

        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Return only warning-severity validation issues.

        Returns:
            Validation issues whose severity is `warning`.
        """

        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def infos(self) -> list[ValidationIssue]:
        """Return only info-severity validation issues.

        Info issues are hints, such as deprecated but still valid usage. They
        never make metadata invalid.

        Returns:
            Validation issues whose severity is `info`.
        """

        return [issue for issue in self.issues if issue.severity == "info"]

    @property
    def overview_errors(self) -> list[ValidationOverviewIssue]:
        """Return only error-severity overview issues.

        Returns:
            Overview issues whose severity is `error`.
        """

        return [issue for issue in self.overview_issues if issue.severity == "error"]

    @property
    def overview_warnings(self) -> list[ValidationOverviewIssue]:
        """Return only warning-severity overview issues.

        Returns:
            Overview issues whose severity is `warning`.
        """

        return [issue for issue in self.overview_issues if issue.severity == "warning"]

    @property
    def valid(self) -> bool:
        """Return whether the result contains no errors.

        Returns:
            True when no error-severity issues are present.
        """

        return not self.errors and not self.overview_errors

    def add(self, severity: Severity, code: str, path: str, message: str) -> None:
        """Append a new issue while keeping issue construction centralized."""

        self.issues.append(ValidationIssue(severity, code, path, message))

    def add_overview(
        self,
        severity: Severity,
        code: str,
        message: str,
        *,
        paths: tuple[str, ...] = (),
        indexes: tuple[int, ...] = (),
    ) -> None:
        """Append a new overview issue while keeping construction centralized."""

        self.overview_issues.append(ValidationOverviewIssue(severity, code, message, paths, indexes))

    def as_dict(self) -> dict[str, Any]:
        """Return a stable machine-readable validation payload."""

        data: dict[str, Any] = {
            "valid": self.valid,
            "issues": [
                {
                    "severity": issue.severity,
                    "code": issue.code,
                    "path": issue.path,
                    "message": issue.message,
                }
                for issue in self.issues
            ],
        }
        if self.overview_issues:
            data["overviewIssues"] = [
                {
                    "severity": issue.severity,
                    "code": issue.code,
                    "message": issue.message,
                    "paths": list(issue.paths),
                    "indexes": list(issue.indexes),
                }
                for issue in self.overview_issues
            ]
        return data


@dataclass(frozen=True, slots=True)
class ValidationRun:
    """Parsed metadata plus validation result for one input path.

    Attributes:
        path: Input path.
        metadata: Parsed normalized metadata.
        result: Validation result for the metadata.
    """

    path: Path
    metadata: NormalizedMetadata
    result: ValidationResult


def _empty_image_region_list():
    """Create an empty region list without triggering validation imports.

    Returns:
        Empty `ImageRegionList` instance.
    """

    from .region import ImageRegionList

    return ImageRegionList(validate=False)
