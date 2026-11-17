"""Console, JSON, and JSONC renderers for validation output."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .fixer import FIXABLE_BY_REMOVAL_ERROR_CODES
from .models import NormalizedMetadata, ValidationResult, ValidationRun
from .region import ImageRegion, ImageRegionList

COLOR_CODES = {
    "error": "\033[31m",
    "warning": "\033[33m",
    "info": "\033[36m",
}
SEVERITY_RANK = {"error": 3, "warning": 2, "info": 1}
JSON_COLOR_CODES = {
    "key": "\033[36m",
    "string": "\033[32m",
    "number": "\033[32m",
    "literal": "\033[32m",
    "unknown": "\033[37m",
}
RESET_COLOR = "\033[0m"
NATIVE_IMAGE_REGION_KEYS = {
    "imageRegion",
    "regionBoundary",
    "rbShape",
    "rbUnit",
    "rbX",
    "rbY",
    "rbW",
    "rbH",
    "rbRx",
    "rbVertices",
    "rbCoordinates",
    "rbMbPartDetails",
    "rbMbPdPartIndex",
    "rbMbPdPartId",
    "rbMbPdPartName",
    "rbMbPdPartDescription",
    "rId",
    "name",
    "rCtype",
    "rRole",
    "rMemberOf",
    "identifiers",
    "role",
    "cvTermId",
    "cvTermName",
    "personInImage",
    "imageSupplierImageId",
}


def format_validation(value: Any, *, ignore_dimensions: bool = False) -> str:
    """Return standard JSON validation output for metadata, regions, or a result.

    Args:
        value: Metadata, region list, region, or existing validation result.
        ignore_dimensions: Skip missing image-dimension checks for pixel
            boundaries.

    Returns:
        Pretty-printed JSON validation result.

    Raises:
        TypeError: If `value` is not a supported renderable type.
        ValueError: If pixel validation requires missing image dimensions.
    """

    result = _validation_result_for_value(value, ignore_dimensions=ignore_dimensions)
    return json.dumps(result.as_dict(), indent=2, ensure_ascii=False)


def format_image_region(value: Any, *, color: bool = False, ignore_dimensions: bool = False) -> str:
    """Return visual Image Region JSON for a region, region list, or metadata object.

    Args:
        value: Metadata, region list, or region.
        color: Whether to include ANSI color codes.
        ignore_dimensions: Skip missing image-dimension checks for pixel
            boundaries.

    Returns:
        Formatted Image Region JSON text.

    Raises:
        TypeError: If `value` is not a supported renderable type.
        ValueError: If pixel validation requires missing image dimensions.
    """

    payload, issues, root_path = _image_region_payload_and_issues(value, ignore_dimensions=ignore_dimensions)
    return format_json(payload, color=color, issues=issues, root_path=root_path)


def format_annotated_image_region(value: Any, *, color: bool = False, ignore_dimensions: bool = False) -> str:
    """Return JSONC-style Image Region output with validation comments.

    Args:
        value: Metadata, region list, or region.
        color: Whether to include ANSI color codes.
        ignore_dimensions: Skip missing image-dimension checks for pixel
            boundaries.

    Returns:
        JSONC-style text with validation comments.

    Raises:
        TypeError: If `value` is not a supported renderable type.
        ValueError: If pixel validation requires missing image dimensions.
    """

    payload, issues, root_path = _image_region_payload_and_issues(value, ignore_dimensions=ignore_dimensions)
    return format_annotated_json(payload, issues=issues, color=color, root_path=root_path)


def print_human_runs(runs: list[ValidationRun], *, color: bool) -> None:
    """Print human validation output for one or more files.

    Args:
        runs: Validation runs to print.
        color: Whether to include ANSI color codes.
    """

    for index, run in enumerate(runs):
        if index:
            print()
        print(f"{run.path}:")
        _print_human_result(run.result, color=color)


def format_validation_runs(runs: list[ValidationRun]) -> str:
    """Return standard JSON validation output with paths included.

    Args:
        runs: Validation runs to render.

    Returns:
        Pretty-printed JSON text.
    """

    if len(runs) == 1:
        return json.dumps(_validation_run_as_dict(runs[0]), indent=2, ensure_ascii=False)

    return json.dumps(
        [_validation_run_as_dict(run) for run in runs],
        indent=2,
        ensure_ascii=False,
    )


def format_image_region_runs(runs: list[ValidationRun], *, color: bool) -> str:
    """Return visual Image Region JSON for one or more files.

    Args:
        runs: Validation runs to render.
        color: Whether to include ANSI color codes.

    Returns:
        Formatted Image Region JSON text with file paths.
    """

    if len(runs) == 1:
        return format_json(
            _image_region_run_as_dict(runs[0]),
            color=color,
            issues=_image_region_issues_for_run(runs[0], "file.imageRegion"),
            root_path="file",
        )

    return format_json(
        [_image_region_run_as_dict(run) for run in runs],
        color=color,
        issues=_multi_file_image_region_issues(runs),
        root_path="files",
    )


def format_annotated_image_region_runs(runs: list[ValidationRun], *, color: bool) -> str:
    """Return JSONC-style Image Region output with validation comments.

    Args:
        runs: Validation runs to render.
        color: Whether to include ANSI color codes.

    Returns:
        JSONC-style text with validation comments and file paths.
    """

    if len(runs) == 1:
        return format_annotated_json(
            _image_region_run_as_dict(runs[0]),
            issues=_image_region_issues_for_run(runs[0], "file.imageRegion"),
            color=color,
            root_path="file",
        )

    return format_annotated_json(
        [_image_region_run_as_dict(run) for run in runs],
        issues=_multi_file_image_region_issues(runs),
        color=color,
        root_path="files",
    )


def write_annotated_output(target: str, output: str) -> None:
    """Write JSONC-style output to stdout or a .jsonc file.

    Args:
        target: `-` for stdout or a file path.
        output: JSONC-style text to write.

    Raises:
        OSError: If file output cannot be written.
    """

    print("iptc-iris: warning: annotated output is JSONC-style text, not standard JSON.", file=sys.stderr)
    if target == "-":
        print(output)
        return

    path = Path(target)
    path.write_text(output + "\n", encoding="utf-8")


def use_color(mode: str) -> bool:
    """Resolve the --color mode into a boolean for the current stdout.

    Args:
        mode: One of `auto`, `always`, or `never`.

    Returns:
        True when output should include ANSI color codes.
    """

    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty()


def format_json(value: Any, *, color: bool, issues: list[Any] | None = None, root_path: str = "imageRegion") -> str:
    """Format visual JSON with optional issue-aware field coloring.

    Args:
        value: JSON-compatible value to render.
        color: Whether to include ANSI color codes.
        issues: Optional validation issues used for field coloring.
        root_path: JSON-style root path for issue matching.

    Returns:
        Formatted JSON-like text.
    """

    issue_colors = _issue_colors(issues or []) if color else {}
    return _format_json_value(
        value,
        color=color,
        issue_colors=issue_colors,
        path=root_path,
        level=0,
        native=True,
    )


def format_annotated_json(value: Any, *, issues: list[Any], color: bool, root_path: str) -> str:
    """Format JSONC-style output with inline validation comments.

    Args:
        value: JSON-compatible value to render.
        issues: Validation issues to attach as comments.
        color: Whether to include ANSI color codes.
        root_path: JSON-style root path for issue matching.

    Returns:
        JSONC-style formatted text.
    """

    issue_map = _issues_by_path(issues)
    issue_colors = _issue_colors(issues) if color else {}
    missing_comments = _missing_field_comments(value, issue_map, root_path)
    inline_comments = _inline_field_comments(issue_map, missing_comments)
    return _format_json_value(
        value,
        color=color,
        issue_colors=issue_colors,
        issue_comments=inline_comments,
        missing_comments=missing_comments,
        path=root_path,
        level=0,
        native=True,
    )


def _print_human_result(result: ValidationResult, *, color: bool = False) -> None:
    """Print the compact human validation summary for one file."""

    if result.valid:
        print("IPTC Image Region metadata is valid.")
    else:
        print("IPTC Image Region metadata is invalid.")
        fixable_note = _fixable_note(result)
        if fixable_note is not None:
            print(fixable_note)
    covered_paths = set()
    for issue in result.overview_issues:
        covered_paths.update(issue.paths)
        if issue.paths:
            path = ", ".join(_color_field(path, issue.severity, enabled=color) for path in issue.paths)
        else:
            path = _color_field("imageRegion", issue.severity, enabled=color)
        print(f"{issue.severity.upper():7} {issue.code:24} {path}: {issue.message}")
    for issue in result.issues:
        if issue.path in covered_paths:
            continue
        path = _color_field(issue.path, issue.severity, enabled=color)
        print(f"{issue.severity.upper():7} {issue.code:24} {path}: {issue.message}")


def _fixable_note(result: ValidationResult) -> str | None:
    """Return a short note about safe cleanup fixes.

    Args:
        result: Validation result to inspect.

    Returns:
        Human-readable fixability note, or None when no safe cleanup fix is
        detected.
    """

    errors = result.errors
    if not errors:
        return None

    fixable_errors = [issue for issue in errors if issue.code in FIXABLE_BY_REMOVAL_ERROR_CODES]
    if not fixable_errors:
        return None
    if len(fixable_errors) == len(errors):
        return "Fixable: yes; all errors can be resolved by removing unsupported boundary or vertex fields."
    return "Fixable: partially; some errors can be resolved by removing unsupported boundary or vertex fields."


def _validation_result_for_value(value: Any, *, ignore_dimensions: bool) -> ValidationResult:
    """Return a validation result for any public renderable value.

    Args:
        value: Metadata, region list, region, or existing validation result.
        ignore_dimensions: Whether to skip missing image-dimension checks.

    Returns:
        Validation result for the supplied value.

    Raises:
        TypeError: If the value type cannot be validated by the renderer.
    """

    if isinstance(value, ValidationResult):
        return value
    if isinstance(value, NormalizedMetadata):
        return value.validation_result(ignore_dimensions=ignore_dimensions)
    if isinstance(value, ImageRegionList):
        return value.validation_result(ignore_dimensions=ignore_dimensions)
    if isinstance(value, ImageRegion):
        return ValidationResult(issues=value.validate("imageRegion[0]", ignore_dimensions=ignore_dimensions))
    raise TypeError("value must be NormalizedMetadata, ImageRegionList, ImageRegion, or ValidationResult.")


def _image_region_payload_and_issues(
    value: Any, *, ignore_dimensions: bool
) -> tuple[dict[str, Any] | list[dict[str, Any]], list[Any], str]:
    """Build the rendered Image Region payload and matching issues.

    Args:
        value: Metadata, region list, or region to render.
        ignore_dimensions: Whether to skip missing image-dimension checks.

    Returns:
        A tuple of payload, validation issues, and root issue path.

    Raises:
        TypeError: If the value type cannot be rendered as Image Region data.
    """

    if isinstance(value, NormalizedMetadata):
        regions = value.image_regions
        return (
            [_image_region_as_visual_dict(region) for region in regions],
            value.validate(ignore_dimensions=ignore_dimensions),
            "imageRegion",
        )
    if isinstance(value, ImageRegionList):
        return (
            [_image_region_as_visual_dict(region) for region in value],
            value.validate(ignore_dimensions=ignore_dimensions),
            "imageRegion",
        )
    if isinstance(value, ImageRegion):
        return (
            _image_region_as_visual_dict(value),
            value.validate("imageRegion[0]", ignore_dimensions=ignore_dimensions),
            "imageRegion[0]",
        )
    raise TypeError("value must be NormalizedMetadata, ImageRegionList, or ImageRegion.")


def _validation_run_as_dict(run: ValidationRun) -> dict[str, Any]:
    """Convert one validation run into the public --json object shape."""

    return {
        "path": str(run.path),
        **run.result.as_dict(),
    }


def _image_region_run_as_dict(run: ValidationRun) -> dict[str, Any]:
    """Convert one run into the public --image-region object shape."""

    return {
        "path": str(run.path),
        "imageRegion": [_image_region_as_visual_dict(region) for region in run.metadata.image_regions],
    }


def _image_region_as_visual_dict(region) -> dict[str, Any]:
    """Convert a region for diagnostic rendering, including invalid geometry fields."""

    return region.as_diagnostic_dict()


def _image_region_issues_for_run(run: ValidationRun, prefix: str) -> list[Any]:
    """Rewrite issue paths to match wrapped --image-region output."""

    issues: list[Any] = []
    for issue in run.result.issues:
        if not issue.path.startswith("imageRegion"):
            continue
        copied = type(issue)(
            severity=issue.severity,
            code=issue.code,
            path=f"{prefix}{issue.path.removeprefix('imageRegion')}",
            message=issue.message,
        )
        issues.append(copied)
    return issues


def _multi_file_image_region_issues(runs: list[ValidationRun]) -> list[Any]:
    """Rewrite issue paths for the multi-file --image-region list shape."""

    issues: list[Any] = []
    for index, run in enumerate(runs):
        issues.extend(_image_region_issues_for_run(run, f"files[{index}].imageRegion"))
    return issues


def _color_field(value: str, severity: str, *, enabled: bool) -> str:
    """Color a validation path according to severity."""

    if not enabled:
        return value
    color = COLOR_CODES.get(severity)
    if color is None:
        return value
    return f"{color}{value}{RESET_COLOR}"


def _format_json_value(
    value: Any,
    *,
    color: bool,
    issue_colors: dict[str, str],
    path: str,
    level: int,
    native: bool,
    issue_comments: dict[str, list[Any]] | None = None,
    missing_comments: dict[str, list[Any]] | None = None,
) -> str:
    """Recursively format JSON/JSONC while tracking validation paths."""

    if isinstance(value, list):
        if not value:
            return _with_inline_comment("[]", _inline_issue_comment(issue_comments, path))
        lines = ["["]
        for index, item in enumerate(value):
            suffix = "," if index < len(value) - 1 else ""
            item_path = f"{path}[{index}]"
            rendered = _format_json_value(
                item,
                color=color,
                issue_colors=issue_colors,
                path=item_path,
                level=level + 1,
                native=native,
                issue_comments=issue_comments,
                missing_comments=missing_comments,
            )
            lines.append(f"{_indent(level + 1)}{rendered}{suffix}")
        lines.append(f"{_indent(level)}]")
        return _with_inline_comment("\n".join(lines), _inline_issue_comment(issue_comments, path))

    if isinstance(value, dict):
        if not value:
            return _with_inline_comment("{}", _inline_issue_comment(issue_comments, path))
        lines = ["{"]
        if missing_comments:
            lines.extend(_issue_comment_lines(missing_comments, path, level + 1))
        items = list(value.items())
        for index, (key, child) in enumerate(items):
            suffix = "," if index < len(items) - 1 else ""
            child_path = f"{path}.{key}"
            child_native = native and (key in NATIVE_IMAGE_REGION_KEYS or key == "path")
            key_kind = "key" if child_native else "unknown"
            rendered_key = _format_json_scalar(
                str(key),
                color=color,
                syntax_kind=key_kind,
                issue_color=_issue_color_for_path(issue_colors, child_path),
            )
            rendered_child = _format_json_value(
                child,
                color=color,
                issue_colors=issue_colors,
                path=child_path,
                level=level + 1,
                native=child_native,
                issue_comments=issue_comments,
                missing_comments=missing_comments,
            )
            lines.append(f"{_indent(level + 1)}{rendered_key}: {rendered_child}{suffix}")
        lines.append(f"{_indent(level)}}}")
        return _with_inline_comment("\n".join(lines), _inline_issue_comment(issue_comments, path))

    rendered_scalar = _format_json_scalar(
        value,
        color=color,
        syntax_kind=_json_scalar_kind(value) if native else "unknown",
        issue_color=_issue_color_for_path(issue_colors, path),
    )
    return _with_inline_comment(rendered_scalar, _inline_issue_comment(issue_comments, path))


def _format_json_scalar(value: Any, *, color: bool, syntax_kind: str, issue_color: str | None = None) -> str:
    """Render one scalar and apply syntax or issue coloring."""

    rendered = json.dumps(value, ensure_ascii=False)
    if not color:
        return rendered
    color_code = issue_color or JSON_COLOR_CODES[syntax_kind]
    return f"{color_code}{rendered}{RESET_COLOR}"


def _json_scalar_kind(value: Any) -> str:
    """Choose the syntax-color bucket for a scalar JSON value."""

    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    return "literal"


def _issue_colors(issues: list[Any]) -> dict[str, str]:
    """Map validation issue paths to ANSI colors, with errors taking priority."""

    colors: dict[str, str] = {}
    for issue in issues:
        if not (
            issue.path.startswith("imageRegion") or issue.path.startswith("file.") or issue.path.startswith("files[")
        ):
            continue
        color = COLOR_CODES.get(issue.severity)
        if color is None:
            continue
        existing = colors.get(issue.path)
        existing_rank = next((SEVERITY_RANK[name] for name, code in COLOR_CODES.items() if code == existing), 0)
        if existing_rank >= SEVERITY_RANK.get(issue.severity, 0):
            continue
        colors[issue.path] = color
    return colors


def _issue_color_for_path(issue_colors: dict[str, str], path: str) -> str | None:
    """Return the effective issue color for a path, including ancestor paths.

    Args:
        issue_colors: Mapping of issue paths to ANSI colors.
        path: Rendered JSON path.

    Returns:
        Error color when the path or an ancestor has an error, warning color
        when only warning matches exist, or None.
    """

    matched_color: str | None = None
    for issue_path, color in issue_colors.items():
        if not _path_is_self_or_descendant(path, issue_path):
            continue
        if color == COLOR_CODES["error"]:
            return color
        matched_color = color
    return matched_color


def _path_is_self_or_descendant(path: str, issue_path: str) -> bool:
    """Return whether a rendered path matches an issue path or its descendants.

    Args:
        path: Rendered JSON path.
        issue_path: Validation issue path.

    Returns:
        True when `path` is the same field or is below `issue_path`.
    """

    return path == issue_path or path.startswith(f"{issue_path}.") or path.startswith(f"{issue_path}[")


def _issues_by_path(issues: list[Any]) -> dict[str, list[Any]]:
    """Group validation issues by path for annotation lookup."""

    by_path: dict[str, list[Any]] = {}
    for issue in issues:
        by_path.setdefault(issue.path, []).append(issue)
    return by_path


def _issue_comment_lines(issue_comments: dict[str, list[Any]], path: str, level: int) -> list[str]:
    """Build standalone JSONC comment lines for missing-field issues."""

    comments = []
    for issue in issue_comments.get(path, []):
        comments.append(f"{_indent(level)}// {issue.severity.upper()} {issue.code}: {issue.message}")
    return comments


def _inline_field_comments(
    issue_comments: dict[str, list[Any]],
    missing_comments: dict[str, list[Any]],
) -> dict[str, list[Any]]:
    """Return only issues that can be attached to an existing rendered value."""

    missing_issue_ids = {id(issue) for issues in missing_comments.values() for issue in issues}
    return {
        path: [issue for issue in issues if id(issue) not in missing_issue_ids]
        for path, issues in issue_comments.items()
        if any(id(issue) not in missing_issue_ids for issue in issues)
    }


def _inline_issue_comment(issue_comments: dict[str, list[Any]] | None, path: str) -> str | None:
    """Build the trailing JSONC comment for one existing field path."""

    if not issue_comments:
        return None
    issues = issue_comments.get(path)
    if not issues:
        return None
    return " ".join(f"// {issue.severity.upper()} {issue.code}: {issue.message}" for issue in issues)


def _missing_field_comments(value: Any, issue_comments: dict[str, list[Any]], root_path: str) -> dict[str, list[Any]]:
    """Attach missing-field comments to the nearest existing parent object."""

    object_paths = _collect_object_paths(value, root_path)
    missing: dict[str, list[Any]] = {}
    for path, issues in issue_comments.items():
        parent_path = path.rsplit(".", 1)[0] if "." in path else ""
        if parent_path in object_paths and _missing_field_issues(issues):
            missing.setdefault(parent_path, []).extend(_missing_field_issues(issues))
    return missing


def _missing_field_issues(issues: list[Any]) -> list[Any]:
    """Select issue codes that refer to fields absent from the data."""

    return [
        issue
        for issue in issues
        if issue.code in {"MISSING_BOUNDARY_FIELD", "MISSING_VERTEX_COORDINATE", "MISSING_REGION_BOUNDARY"}
    ]


def _collect_object_paths(value: Any, path: str) -> set[str]:
    """Collect paths for every rendered object so missing fields have anchors."""

    paths: set[str] = set()
    if isinstance(value, dict):
        paths.add(path)
        for key, child in value.items():
            paths.update(_collect_object_paths(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.update(_collect_object_paths(child, f"{path}[{index}]"))
    return paths


def _with_inline_comment(rendered: str, comment: str | None) -> str:
    """Append a JSONC comment to the last line of a rendered value."""

    if comment is None:
        return rendered
    lines = rendered.splitlines()
    lines[-1] = f"{lines[-1]} {comment}"
    return "\n".join(lines)


def _indent(level: int) -> str:
    """Return the fixed two-space indentation used by custom formatters."""

    return "  " * level
