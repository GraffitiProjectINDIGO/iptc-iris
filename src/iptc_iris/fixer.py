"""Safe non-destructive fixes for normalized IPTC Image Region metadata."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .models import NormalizedMetadata, ValidationResult
from .region import ImageRegion, ImageRegionList

FIXABLE_BY_REMOVAL_ERROR_CODES = frozenset(
    {
        "FORBIDDEN_BOUNDARY_FIELD",
        "UNKNOWN_BOUNDARY_FIELD",
        "UNKNOWN_VERTEX_FIELD",
    }
)
_PATH_PART = re.compile(r"(?P<name>[^\[\]]+)(?:\[(?P<index>\d+)])?")


@dataclass(frozen=True)
class FixAction:
    """One safe fix action applied to Image Region metadata.

    Attributes:
        action: Fix action name.
        path: JSON-style path that was changed.
        code: Validation issue code that caused the fix.
        message: Human-readable fix description.
    """

    action: str
    path: str
    code: str
    message: str


@dataclass(frozen=True)
class FixResult:
    """Result of a safe-fix attempt.

    Attributes:
        metadata: Fixed metadata when every error was safely fixable.
        fixes: Applied fix actions.
        original_validation: Validation result before fixes.
        fixed_validation: Validation result after fixes, when fixes were applied.
    """

    metadata: NormalizedMetadata | None
    fixes: list[FixAction]
    original_validation: ValidationResult
    fixed_validation: ValidationResult | None

    @property
    def fixed(self) -> bool:
        """Return whether fixed metadata is available.

        Returns:
            True when safe fixes were applied and no validation errors remain.
        """

        return (
            self.metadata is not None
            and bool(self.fixes)
            and self.fixed_validation is not None
            and self.fixed_validation.valid
        )


def safe_fix_metadata(metadata: NormalizedMetadata) -> FixResult:
    """Remove unsupported boundary/vertex fields when all errors are safe to fix.

    Args:
        metadata: Metadata to inspect and fix.

    Returns:
        Fix result. Already-valid metadata is returned unchanged with no fix
        actions. `metadata` is None when no safe complete fix is available.
    """

    original_validation = metadata.validation_result(ignore_dimensions=True)
    errors = original_validation.errors
    if not errors:
        return FixResult(
            metadata=metadata,
            fixes=[],
            original_validation=original_validation,
            fixed_validation=original_validation,
        )

    fixable_errors = [issue for issue in errors if issue.code in FIXABLE_BY_REMOVAL_ERROR_CODES]
    if len(fixable_errors) != len(errors):
        return FixResult(metadata=None, fixes=[], original_validation=original_validation, fixed_validation=None)

    payload = {"imageRegion": [_region_to_fixable_dict(region) for region in metadata.image_regions]}
    fixes: list[FixAction] = []
    for issue in fixable_errors:
        if _remove_path(payload, issue.path):
            fixes.append(
                FixAction(
                    action="remove",
                    path=issue.path,
                    code=issue.code,
                    message=f"Removed unsupported field at {issue.path}.",
                )
            )

    if not fixes:
        return FixResult(metadata=None, fixes=[], original_validation=original_validation, fixed_validation=None)

    fixed_metadata = NormalizedMetadata(
        image_regions=ImageRegionList.from_raw(
            payload["imageRegion"],
            standard=metadata.standard,
            image_width=metadata.image_width,
            image_height=metadata.image_height,
            allow_malformed=True,
            validate=False,
        ),
        image_width=metadata.image_width,
        image_height=metadata.image_height,
        source_format=metadata.source_format,
        raw=metadata.raw,
    )
    fixed_validation = fixed_metadata.validation_result(ignore_dimensions=True)
    if fixed_validation.errors:
        return FixResult(
            metadata=None,
            fixes=fixes,
            original_validation=original_validation,
            fixed_validation=fixed_validation,
        )
    return FixResult(
        metadata=fixed_metadata,
        fixes=fixes,
        original_validation=original_validation,
        fixed_validation=fixed_validation,
    )


def _region_to_fixable_dict(region: ImageRegion) -> dict[str, Any]:
    """Return a mutable raw/canonical region dictionary suitable for fixes.

    Args:
        region: Region to serialize for fixing.

    Returns:
        Mutable region dictionary.
    """

    if isinstance(region.raw, Mapping):
        return dict(region.raw)
    return region.as_dict()


def _remove_path(payload: dict[str, Any], path: str) -> bool:
    """Remove the field at a JSON-style validation path.

    Args:
        payload: Mutable payload containing `imageRegion`.
        path: Validation issue path.

    Returns:
        True when a field was removed.
    """

    tokens = _path_tokens(path)
    if not tokens:
        return False

    current: Any = payload
    for token in tokens[:-1]:
        if isinstance(token, int):
            if not isinstance(current, list) or token >= len(current):
                return False
            current = current[token]
        else:
            if not isinstance(current, dict) or token not in current:
                return False
            current = current[token]

    last = tokens[-1]
    if isinstance(last, str) and isinstance(current, dict) and last in current:
        del current[last]
        return True
    return False


def _path_tokens(path: str) -> list[str | int]:
    """Tokenize a validation path such as `imageRegion[0].regionBoundary.rbE`.

    Args:
        path: JSON-style validation path.

    Returns:
        Path tokens with list indexes converted to integers.
    """

    tokens: list[str | int] = []
    for part in path.split("."):
        position = 0
        while position < len(part):
            match = _PATH_PART.match(part, position)
            if match is None:
                return []
            tokens.append(match.group("name"))
            index = match.group("index")
            if index is not None:
                tokens.append(int(index))
            position = match.end()
    return tokens
