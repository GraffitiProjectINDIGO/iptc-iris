"""Command-line interface for validating IPTC Image Region metadata."""

from __future__ import annotations

import argparse
import glob
import json
import sys
import tomllib
from collections.abc import Mapping
from importlib import metadata
from pathlib import Path
from typing import Any

from .config import ToolConfig, ValidationConfig
from .fixer import FixResult, safe_fix_metadata
from .io import load_metadata_file, run_metadata_tool
from .models import NormalizedMetadata, ValidationIssue, ValidationRun
from .normalizer import normalize_metadata
from .region import ImageRegionList
from .render import (
    format_annotated_image_region_runs,
    format_image_region_runs,
    format_validation_runs,
    print_human_runs,
    use_color,
    write_annotated_output,
)
from .spec import (
    DEFAULT_STANDARD,
    IPTC_PHOTO_METADATA_STANDARD_URL,
    IPTC_PHOTO_METADATA_STANDARD_VERSION,
    IPTC_STANDARDS,
    Standard,
)


class _VersionedHelpParser(argparse.ArgumentParser):
    """Argument parser that prints the package version before top-level help."""

    def format_help(self) -> str:
        """Return formatted help with a version header.

        Returns:
            Help text prefixed with the current package version.
        """

        return f"iptc-iris {_package_version()}\n{super().format_help()}"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point used by the installed imgregion script."""

    parser = _VersionedHelpParser(
        prog="iptc-iris",
        description="Normalize, validate, render, and convert IPTC Image Region metadata.",
        epilog=(
            f"IPTC Photo Metadata Standard: {IPTC_PHOTO_METADATA_STANDARD_VERSION} ({IPTC_PHOTO_METADATA_STANDARD_URL})"
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_package_version()}")
    subparsers = parser.add_subparsers(dest="command", required=True, title="commands")

    validate_parser = subparsers.add_parser("validate", help="Validate IPTC Image Region metadata.")
    validate_parser.add_argument("path", type=Path, help="JSON, XMP/XML, or image file.")
    validate_parser.add_argument("--format", choices=["auto", "json", "xmp", "xml", "image"], default="auto")
    validate_parser.add_argument("--tool", choices=["exiftool", "exiv2"], help="Read metadata via an external tool.")
    validate_parser.add_argument(
        "--config", type=Path, help="Read tool paths and validation settings from this TOML file."
    )
    validate_parser.add_argument("--exiftool", help="Path or command name for exiftool.")
    validate_parser.add_argument("--exiv2", help="Path or command name for exiv2.")
    validate_parser.add_argument(
        "--standard",
        choices=IPTC_STANDARDS,
        help=(
            "IPTC standard profile used for validation "
            f"(default: [validation].standard from the config file, else {DEFAULT_STANDARD})."
        ),
    )
    output_group = validate_parser.add_mutually_exclusive_group()
    output_group.add_argument("--json", action="store_true", help="Emit machine-readable JSON validation result.")
    output_group.add_argument(
        "--image-region",
        action="store_true",
        dest="image_region",
        help="Print normalized imageRegion JSON to the console.",
    )
    validate_parser.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help=(
            "Colorize console output: auto enables color only for interactive terminals, "
            "and disables it for redirected or piped output."
        ),
    )
    validate_parser.add_argument(
        "--annotate",
        nargs="?",
        const="-",
        metavar="PATH.jsonc",
        help="Emit JSONC-style annotated imageRegion output to stdout or a .jsonc file.",
    )

    convert_parser = subparsers.add_parser("convert", help="Convert IPTC Image Region units.")
    convert_parser.add_argument("path", type=Path, help="JSON, XMP/XML, or image file.")
    convert_parser.add_argument("--to", choices=["pixel", "relative"], required=True, help="Target boundary unit.")
    convert_parser.add_argument("--format", choices=["auto", "json", "xmp", "xml", "image"], default="auto")
    convert_parser.add_argument("--tool", choices=["exiftool", "exiv2"], help="Read metadata via an external tool.")
    convert_parser.add_argument(
        "--config", type=Path, help="Read tool paths and validation settings from this TOML file."
    )
    convert_parser.add_argument("--exiftool", help="Path or command name for exiftool.")
    convert_parser.add_argument("--exiv2", help="Path or command name for exiv2.")
    convert_parser.add_argument(
        "--standard",
        choices=IPTC_STANDARDS,
        help=(
            "IPTC standard profile used for validation "
            f"(default: [validation].standard from the config file, else {DEFAULT_STANDARD})."
        ),
    )
    convert_parser.add_argument(
        "--image-width",
        type=float,
        help="Image width used for conversion when metadata tools or input metadata do not provide it.",
    )
    convert_parser.add_argument(
        "--image-height",
        type=float,
        help="Image height used for conversion when metadata tools or input metadata do not provide it.",
    )
    convert_output_group = convert_parser.add_mutually_exclusive_group()
    convert_output_group.add_argument("--output", type=Path, help="Write converted JSON to this file.")
    convert_output_group.add_argument("--output-dir", type=Path, help="Write one converted JSON file per input file.")

    fix_parser = subparsers.add_parser("fix", help="Safely remove unsupported Image Region fields.")
    fix_parser.add_argument("path", type=Path, help="JSON, XMP/XML, or image file.")
    fix_parser.add_argument("--format", choices=["auto", "json", "xmp", "xml", "image"], default="auto")
    fix_parser.add_argument("--tool", choices=["exiftool", "exiv2"], help="Read metadata via an external tool.")
    fix_parser.add_argument("--config", type=Path, help="Read tool paths and validation settings from this TOML file.")
    fix_parser.add_argument("--exiftool", help="Path or command name for exiftool.")
    fix_parser.add_argument("--exiv2", help="Path or command name for exiv2.")
    fix_parser.add_argument(
        "--standard",
        choices=IPTC_STANDARDS,
        help=(
            "IPTC standard profile used for validation "
            f"(default: [validation].standard from the config file, else {DEFAULT_STANDARD})."
        ),
    )
    fix_parser.add_argument("--dry-run", action="store_true", help="Print the safe fix report without JSON output.")
    fix_output_group = fix_parser.add_mutually_exclusive_group()
    fix_output_group.add_argument("--output", type=Path, help="Write fixed JSON to this file.")
    fix_output_group.add_argument("--output-dir", type=Path, help="Write one fixed JSON file per input file.")

    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        parser.print_help()
        return 0

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code == 0:
            return 0
        raise

    if args.command in {"validate", "convert", "fix"}:
        try:
            _infer_tool_from_executable_flags(args)
            _resolve_standard(args)
        except ValueError as exc:
            print(f"iptc-iris: {exc}", file=sys.stderr)
            return 2

    if args.command == "validate":
        try:
            runs = _validate_paths(args)
        except Exception as exc:  # pragma: no cover - exercised by CLI users.
            print(f"iptc-iris: {exc}", file=sys.stderr)
            return 2

        if args.annotate is not None and not args.image_region:
            # Annotated output is a variant of the visual Image Region view, not
            # a standalone validation-result format.
            print("iptc-iris: --annotate requires --image-region", file=sys.stderr)
            return 2
        if args.annotate is not None and args.annotate != "-" and Path(args.annotate).suffix.casefold() != ".jsonc":
            # The file extension check makes it difficult to accidentally save
            # JSONC comments into a file that other tools expect to be JSON.
            print("iptc-iris: annotated output path must end with .jsonc", file=sys.stderr)
            return 2

        if args.image_region:
            _handle_image_region_output(args, runs)
        elif args.json:
            print(format_validation_runs(runs))
        else:
            print_human_runs(runs, color=use_color(args.color))
        return 0 if all(run.result.valid for run in runs) else 1

    if args.command == "convert":
        try:
            converted = _convert_paths(args)
        except Exception as exc:  # pragma: no cover - exercised by CLI users.
            print(f"iptc-iris: {exc}", file=sys.stderr)
            return 2

        if not converted:
            return 1
        try:
            _write_converted_output(args, converted)
        except Exception as exc:  # pragma: no cover - exercised by CLI users.
            print(f"iptc-iris: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.command == "fix":
        try:
            fixed = _fix_paths(args)
        except Exception as exc:  # pragma: no cover - exercised by CLI users.
            print(f"iptc-iris: {exc}", file=sys.stderr)
            return 2

        if not fixed:
            return 1
        if args.dry_run:
            _print_fix_report(fixed)
        else:
            try:
                _write_fixed_output(args, fixed)
            except Exception as exc:  # pragma: no cover - exercised by CLI users.
                print(f"iptc-iris: {exc}", file=sys.stderr)
                return 2
        return 0

    return 2  # pragma: no cover - argparse requires a supported subcommand.


def _handle_image_region_output(args: argparse.Namespace, runs: list[ValidationRun]) -> None:
    """Render --image-region output in plain, colored, or annotated form."""

    if args.annotate is None:
        print(format_image_region_runs(runs, color=use_color(args.color)))
        return

    # Console annotations are visual and may contain ANSI colors. File
    # annotations are always plain JSONC so editors/parsers do not see escape
    # sequences.
    output = format_annotated_image_region_runs(runs, color=use_color(args.color) and args.annotate == "-")
    write_annotated_output(args.annotate, output)


def _validate_paths(args: argparse.Namespace) -> list[ValidationRun]:
    """Load and validate every path matched by the CLI path argument."""

    runs: list[ValidationRun] = []
    for path in _expand_paths(args.path):
        for entry_path, metadata_path in _load_entries(args, path):
            runs.append(ValidationRun(path=entry_path, metadata=metadata_path, result=metadata_path.validation_result()))
    return runs


def _convert_paths(args: argparse.Namespace) -> list[dict[str, object]]:
    """Load, validate, and convert every path matched by the CLI path argument.

    Args:
        args: Parsed convert command arguments.

    Returns:
        Converted payload objects.

    Raises:
        FileNotFoundError: If a wildcard path matches no files.
        ValueError: If dimensions are missing or output options are invalid.
    """

    prepared: list[tuple[Path, NormalizedMetadata]] = []
    has_errors = False
    for path in _expand_paths(args.path):
        for entry_path, loaded_metadata in _load_entries(args, path):
            metadata = _metadata_with_cli_dimensions(loaded_metadata, args)
            result = metadata.validation_result()
            if result.errors:
                _print_conversion_errors(entry_path, result.errors)
                has_errors = True
            prepared.append((entry_path, metadata))

    if has_errors:
        return []

    converted: list[dict[str, object]] = []
    for path, metadata in prepared:
        width, height = _conversion_dimensions(metadata, args)
        converted_regions = metadata.image_regions.change_unit(args.to, image_width=width, image_height=height)
        converted.append(_metadata_payload(path, converted_regions))
    return converted


def _fix_paths(args: argparse.Namespace) -> list[tuple[Path, FixResult]]:
    """Load and safely fix every path matched by the CLI path argument.

    Args:
        args: Parsed fix command arguments.

    Returns:
        Output-ready fix results paired with input paths, or an empty list when
        any matched file has no complete safe fix.

    Raises:
        FileNotFoundError: If a wildcard path matches no files.
        ValueError: If output options are invalid.
    """

    fixed: list[tuple[Path, FixResult]] = []
    unavailable = False
    for path in _expand_paths(args.path):
        for entry_path, metadata_path in _load_entries(args, path):
            result = safe_fix_metadata(metadata_path)
            if result.metadata is not None and (result.fixed or result.original_validation.valid):
                fixed.append((entry_path, result))
            else:
                _print_fix_unavailable(entry_path, result)
                unavailable = True
    if unavailable:
        return []
    return fixed


def _print_fix_unavailable(path: Path, result: FixResult) -> None:
    """Print why no safe complete fix output is available.

    Args:
        path: Input path.
        result: Safe-fix attempt result.
    """

    if result.original_validation.valid:
        print(f"{path}: No validation errors were found. No output will be produced.", file=sys.stderr)
        return
    print(f"{path}: no complete safe fix available; no output written.", file=sys.stderr)
    remaining_errors = (
        result.fixed_validation.errors if result.fixed_validation is not None else result.original_validation.errors
    )
    for issue in remaining_errors:
        print(f"{issue.severity.upper():7} {issue.code:24} {issue.path}: {issue.message}", file=sys.stderr)


def _print_fix_report(fixed: list[tuple[Path, FixResult]]) -> None:
    """Print the safe fixes that would be or were applied.

    Args:
        fixed: Successful fix results paired with input paths.
    """

    for index, (path, result) in enumerate(fixed):
        if index:
            print()
        print(f"{path}:")
        if not result.fixes:
            print("NOOP    VALID                    imageRegion: No validation errors were found; no fixes needed.")
            continue
        for fix in result.fixes:
            print(f"{fix.action.upper():7} {fix.code:24} {fix.path}: {fix.message}")


def _write_fixed_output(args: argparse.Namespace, fixed: list[tuple[Path, FixResult]]) -> None:
    """Write fixed Image Region JSON to stdout or files.

    Args:
        args: Parsed fix command arguments.
        fixed: Successful fix results paired with input paths.

    Raises:
        OSError: If output files cannot be written.
    """

    payloads = [_fixed_payload(path, result) for path, result in fixed]
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for payload in payloads:
            source = Path(str(payload["path"]))
            output_path = args.output_dir / f"{source.stem}.image-region.fixed.json"
            output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return

    output = _single_or_batch_payload(payloads)
    text = json.dumps(output, indent=2, ensure_ascii=False)
    if args.output is not None:
        _write_output_file(args.output, text)
        return
    print(text)


def _fixed_payload(path: Path, result: FixResult) -> dict[str, object]:
    """Return the public fixed JSON payload for one file.

    Args:
        path: Input path.
        result: Successful fix result.

    Returns:
        JSON-compatible fixed payload.

    Raises:
        ValueError: If the result does not contain fixed metadata.
    """

    if result.metadata is None:
        raise ValueError("fixed metadata is not available")
    payload = _metadata_payload(path, result.metadata.image_regions)
    payload["fixes"] = [
        {
            "action": fix.action,
            "path": fix.path,
            "code": fix.code,
            "message": fix.message,
        }
        for fix in result.fixes
    ]
    return payload


def _metadata_payload(path: Path, regions: ImageRegionList) -> dict[str, object]:
    """Return canonical JSON payload fields shared by fix and convert output."""

    payload: dict[str, object] = {
        "path": str(path),
        "imageRegion": regions.as_dict_list(),
    }
    if regions.image_width is not None:
        payload["imageWidth"] = regions.image_width
    if regions.image_height is not None:
        payload["imageHeight"] = regions.image_height
    return payload


def _single_or_batch_payload(payloads: list[dict[str, object]]) -> dict[str, object]:
    """Return a single payload or a batch envelope for multiple payloads."""

    if len(payloads) == 1:
        return payloads[0]
    return {"files": payloads}


def _metadata_with_cli_dimensions(metadata: NormalizedMetadata, args: argparse.Namespace) -> NormalizedMetadata:
    """Return metadata with CLI dimensions applied when provided.

    Args:
        metadata: Loaded metadata.
        args: Parsed CLI arguments containing optional dimensions.

    Returns:
        Original metadata or a dimension-completed copy.
    """

    if args.image_width is None and args.image_height is None:
        return metadata
    width = args.image_width if args.image_width is not None else metadata.image_width
    height = args.image_height if args.image_height is not None else metadata.image_height
    regions = ImageRegionList(
        metadata.image_regions.as_list(),
        image_width=width,
        image_height=height,
        depth_order=metadata.image_regions.depth_order,
        standard=metadata.standard,
        validate=False,
    )
    return NormalizedMetadata(
        image_regions=regions,
        image_width=width,
        image_height=height,
        source_format=metadata.source_format,
        raw=metadata.raw,
    )


def _conversion_dimensions(metadata: NormalizedMetadata, args: argparse.Namespace) -> tuple[float, float]:
    """Resolve image dimensions used for unit conversion.

    Args:
        metadata: Loaded metadata.
        args: Parsed CLI arguments containing optional dimension overrides.

    Returns:
        Image width and height.

    Raises:
        ValueError: If either dimension is missing.
    """

    width = args.image_width if args.image_width is not None else metadata.image_width
    height = args.image_height if args.image_height is not None else metadata.image_height
    if width is None:
        width = metadata.image_regions.image_width
    if height is None:
        height = metadata.image_regions.image_height
    if width is None or height is None:
        raise ValueError(
            "--image-width and --image-height are required when metadata has no image dimensions. "
            "For image files, try --tool exiftool or --tool exiv2 to read dimensions from file metadata."
        )
    return float(width), float(height)


def _print_conversion_errors(path: Path, issues: list[ValidationIssue]) -> None:
    """Print blocking conversion validation errors to stderr.

    Args:
        path: Input path.
        issues: Error-severity validation issues.
    """

    print(f"{path}: Image Region metadata is invalid; conversion skipped.", file=sys.stderr)
    for issue in issues:
        print(f"{issue.severity.upper():7} {issue.code:24} {issue.path}: {issue.message}", file=sys.stderr)


def _write_converted_output(args: argparse.Namespace, converted: list[dict[str, object]]) -> None:
    """Write converted Image Region JSON to stdout or files.

    Args:
        args: Parsed convert command arguments.
        converted: Converted payloads.

    Raises:
        OSError: If output files cannot be written.
    """

    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for item in converted:
            source = Path(str(item["path"]))
            output_path = args.output_dir / f"{source.stem}.image-region.{args.to}.json"
            output_path.write_text(json.dumps(item, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return

    output = _single_or_batch_payload(converted)
    text = json.dumps(output, indent=2, ensure_ascii=False)
    if args.output is not None:
        _write_output_file(args.output, text)
        return
    print(text)


def _write_output_file(path: Path, text: str) -> None:
    """Write a `--output` file after validating that its directory exists.

    Args:
        path: Output file path.
        text: Text content without the final newline.

    Raises:
        ValueError: If the output parent directory does not exist.
        OSError: If the file cannot be written.
    """

    parent = path.parent
    if not parent.exists():
        raise ValueError(f"--output directory does not exist: {parent}")
    if not parent.is_dir():
        raise ValueError(f"--output parent is not a directory: {parent}")
    path.write_text(text + "\n", encoding="utf-8")


def _load_entries(args: argparse.Namespace, path: Path) -> list[tuple[Path, NormalizedMetadata]]:
    """Load a path, expanding imgregion batch JSON files into entries.

    Args:
        args: Parsed command arguments.
        path: Input path.

    Returns:
        Loaded metadata entries paired with their source paths.
    """

    if args.tool or not _could_be_json(args, path):
        return [(path, _load_path(args, path))]

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    batch_entries = _batch_entries(data, path, args.standard)
    if batch_entries is not None:
        return batch_entries
    return [(path, normalize_metadata(data, source_format="json", standard=args.standard))]


def _could_be_json(args: argparse.Namespace, path: Path) -> bool:
    """Return whether a path should be inspected for batch JSON."""

    if args.format == "json":
        return True
    return args.format == "auto" and path.suffix.casefold() == ".json"


def _batch_entries(
    data: Any, path: Path, standard: Standard = DEFAULT_STANDARD
) -> list[tuple[Path, NormalizedMetadata]] | None:
    """Return entries from an imgregion batch JSON object.

    Args:
        data: Parsed JSON data.
        path: JSON file path used for fallback entry labels.
        standard: Standard profile stored with each entry.

    Returns:
        Batch entries, or None when the object is not an imgregion batch.

    Raises:
        ValueError: If a `files` member is present but malformed.
    """

    if not isinstance(data, Mapping) or "files" not in data:
        return None

    files = data["files"]
    if not isinstance(files, list):
        raise ValueError("batch JSON field 'files' must be a list")

    entries: list[tuple[Path, NormalizedMetadata]] = []
    for index, item in enumerate(files):
        if not isinstance(item, Mapping):
            raise ValueError("batch JSON entries must be objects")
        entry_path = Path(str(item.get("path", f"{path}#{index}")))
        entries.append((entry_path, _metadata_from_batch_item(item, standard)))
    return entries


def _metadata_from_batch_item(item: Mapping[str, Any], standard: Standard = DEFAULT_STANDARD) -> NormalizedMetadata:
    """Normalize one object from an imgregion batch JSON file."""

    data: dict[str, Any] = {"imageRegion": item.get("imageRegion", [])}
    if "imageWidth" in item:
        data["imageWidth"] = item["imageWidth"]
    if "imageHeight" in item:
        data["imageHeight"] = item["imageHeight"]
    return normalize_metadata(data, source_format="batch-json", standard=standard)


def _load_path(args: argparse.Namespace, path: Path) -> NormalizedMetadata:
    """Load one path either through an external metadata tool or built-ins."""

    if args.tool:
        return _load_with_tool(args, path)
    return load_metadata_file(path, input_format=args.format, standard=args.standard)


def _infer_tool_from_executable_flags(args: argparse.Namespace) -> None:
    """Use a tool executable flag as an implicit --tool selection."""

    if args.tool:
        return
    if args.exiftool and args.exiv2:
        raise ValueError("--tool is required when both --exiftool and --exiv2 are provided")
    if args.exiftool:
        args.tool = "exiftool"
    elif args.exiv2:
        args.tool = "exiv2"


def _resolve_standard(args: argparse.Namespace) -> None:
    """Resolve the standard profile: --standard, then [validation].standard, then the default.

    Raises:
        ValueError: If the config file contains an invalid standard.
    """

    if args.standard is None:
        args.standard = ValidationConfig.load(args.config).standard or DEFAULT_STANDARD


def _expand_paths(path: Path) -> list[Path]:
    """Expand wildcard paths on platforms/shells that do not do it for us."""

    pattern = str(path)
    if not _has_wildcard(pattern):
        return [path]

    matches = sorted(Path(match) for match in glob.glob(pattern, recursive=True))
    files = [match for match in matches if match.is_file()]
    if not files:
        raise FileNotFoundError(f"No files match {pattern!r}")
    return files


def _has_wildcard(value: str) -> bool:
    """Return whether a path string contains glob wildcard characters."""

    return any(character in value for character in "*?[")


def _load_with_tool(args: argparse.Namespace, path: Path):
    """Load one file through the selected external metadata tool."""

    tool_config = ToolConfig.load(args.config)
    return run_metadata_tool(
        path, args.tool, executable=_tool_executable(args.tool, args, tool_config), standard=args.standard
    )


def _tool_executable(tool: str, args: argparse.Namespace, tool_config: ToolConfig) -> str | None:
    """Resolve command-line executable overrides before config values."""

    if tool == "exiftool" and args.exiftool:
        return args.exiftool
    if tool == "exiv2" and args.exiv2:
        return args.exiv2
    return tool_config.executable_for(tool)


def _package_version() -> str:
    """Return the installed package version or the development pyproject version.

    Returns:
        Package version string.
    """

    try:
        return metadata.version("iptc-iris")
    except metadata.PackageNotFoundError:
        pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
        with pyproject_path.open("rb") as handle:
            data = tomllib.load(handle)
        return str(data["project"]["version"])


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
