"""File loading and optional external-tool wrappers for metadata input."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from .iptc_registry import DEFAULT_IPTC_REGISTRY, IptcPropertyRegistry, namespace_registration_for_path
from .models import NormalizedMetadata
from .normalizer import normalize_metadata
from .region import ImageRegionList
from .spec import DEFAULT_STANDARD, Standard
from .xmp import extract_xmp_packet, parse_xmp, xmp_image_region_data

ToolName = Literal["exiftool", "exiv2"]
# Exiv2 exits with this code when a file has no Exif block, even if the requested output was printed.
_EXIV2_NO_EXIF_EXIT_CODE = 253
_EXIV2_IMAGE_SIZE = re.compile(r"^Image size\s*:\s*(\d+)\s*x\s*(\d+)", re.MULTILINE)
LANG_ALT_KEY_RE = re.compile(r"^([a-z]{2,3}(-[A-Za-z]{2,8})?|x-default)$")
IPTC_EXT_NS = "http://iptc.org/std/Iptc4xmpExt/2008-02-29/"
# ExifTool does not define the IPTC 2026.1 Image Region fields yet; this config adds them.
EXIFTOOL_CONFIG = Path(__file__).with_name("data") / "exiftool_iptc_2026.config"
BUILT_IN_REGION_KEYS = {"rId", "name", "regionBoundary", "rCtype", "rRole", "rMemberOf"}


class MetadataToolWarning(RuntimeError):
    """Raised when ExifTool reports a warning or error while writing metadata.

    ExifTool can exit successfully while skipping values it cannot write, so
    warnings are treated as failures by default. The image may already have
    been modified when this is raised.

    Attributes:
        completed: The finished ExifTool process, including stdout and stderr.
        messages: The `Warning:`/`Error:` lines reported by ExifTool.
    """

    def __init__(self, completed: subprocess.CompletedProcess[str], messages: list[str]) -> None:
        super().__init__("ExifTool reported a metadata problem: " + "; ".join(messages))
        self.completed = completed
        self.messages = messages


def _guess_format(path: Path) -> str:
    """Infer the built-in loader format from the file suffix.

    Args:
        path: Input path.

    Returns:
        One of `json`, `xmp`, or `image`.
    """

    suffix = path.suffix.casefold()
    if suffix == ".json":
        return "json"
    if suffix in {".xmp", ".xml"}:
        return "xmp"
    return "image"


def load_metadata_file(
    path: str | Path, *, input_format: str = "auto", standard: Standard = DEFAULT_STANDARD
) -> NormalizedMetadata:
    """Load metadata from JSON, XMP/XML, or an image file with embedded XMP.

    This is the built-in loader path used when the CLI is not explicitly routed
    through exiftool or exiv2. It returns normalized metadata regardless of the
    input file type so the validator can stay format-agnostic.

    Args:
        path: Metadata or image file path.
        input_format: Explicit format (`json`, `xmp`, `xml`, `image`) or
            `auto` to infer from the suffix.
        standard: Validation profile stored with the loaded data, `"2025.1"`
            (default) or `"2026.1-draft"`. Reading keeps all content either way.

    Returns:
        Normalized metadata.

    Raises:
        OSError: If the file cannot be read.
        json.JSONDecodeError: If JSON input is invalid.
        xml.etree.ElementTree.ParseError: If XMP/XML input is invalid.
    """

    file_path = Path(path)
    if input_format == "auto":
        input_format = _guess_format(file_path)

    if input_format == "json":
        # JSON is read as UTF-8 per the modern JSON specification. The project
        # does not attempt to support locale-dependent "ANSI" encodings.
        with file_path.open("r", encoding="utf-8") as handle:
            return normalize_metadata(json.load(handle), source_format="json", standard=standard)

    if input_format in {"xmp", "xml"}:
        # XMP sidecars are XML documents. parse_xmp extracts only the Image
        # Region portion and normalize_metadata canonicalizes the tag names.
        return normalize_metadata(
            parse_xmp(file_path.read_text(encoding="utf-8")), source_format="xmp", standard=standard
        )

    # Fallback image support scans for an embedded XMP packet. If callers want a
    # full metadata-tool parser, they can use --tool exiftool or --tool exiv2.
    data = file_path.read_bytes()
    xmp_packet = extract_xmp_packet(data)
    if xmp_packet is None:
        return NormalizedMetadata(source_format="image", raw=None).with_standard(standard)
    return normalize_metadata(parse_xmp(xmp_packet), source_format="embedded-xmp", standard=standard)


def parse_metadata_text(
    text: str, *, source_format: str = "auto", standard: Standard = DEFAULT_STANDARD
) -> NormalizedMetadata:
    """Parse metadata text produced by common tools.

    exiftool usually gives JSON when invoked by run_metadata_tool, while exiv2
    commonly gives flat key/value text. This helper accepts both so tests and
    callers can feed captured tool output directly.

    Args:
        text: Captured metadata text.
        source_format: Parser hint such as `exiftool-json`, `exiv2`, `xmp`,
            `xml`, `json`, or `auto`.
        standard: Validation profile stored with the parsed data.

    Returns:
        Normalized metadata.

    Raises:
        json.JSONDecodeError: If JSON-like input is invalid.
        xml.etree.ElementTree.ParseError: If XML-like input is invalid.
    """

    stripped = text.strip()
    if not stripped:
        return NormalizedMetadata(source_format=source_format, raw=text).with_standard(standard)

    if (source_format in {"auto", "json"} or source_format.endswith("-json")) and stripped[0] in "[{":
        # exiftool -j emits a JSON array with one object per source file.
        return normalize_metadata(json.loads(stripped), source_format="json", standard=standard)

    if source_format in {"auto", "xmp", "xml"} and "<" in stripped[:100]:
        # Some tools can emit raw XMP/XML; treat that like a sidecar packet.
        return normalize_metadata(parse_xmp(stripped), source_format="xmp", standard=standard)

    # Last resort: parse simple key/value lines such as exiv2 -pa output.
    return normalize_metadata(_parse_key_value_lines(stripped), source_format=source_format, standard=standard)


def run_metadata_tool(
    path: str | Path,
    tool: ToolName,
    *,
    executable: str | Path | None = None,
    standard: Standard = DEFAULT_STANDARD,
) -> NormalizedMetadata:
    """Run an installed metadata tool and normalize its output.

    The executable parameter lets the CLI use paths from command-line flags or
    iptc-iris.toml. If it is omitted, PATH lookup preserves the original simple
    behavior.

    Args:
        path: Image file path to inspect.
        tool: Metadata tool to run (`exiftool` or `exiv2`).
        executable: Optional command or executable path. When omitted, PATH is
            searched for the selected tool.
        standard: Validation profile stored with the loaded data.

    Returns:
        Normalized metadata parsed from the tool output.

    Raises:
        FileNotFoundError: If the selected tool is not found on PATH.
        subprocess.CalledProcessError: If the external tool exits with a
            non-zero status.
        json.JSONDecodeError: If ExifTool JSON output is invalid.
        xml.etree.ElementTree.ParseError: If tool output is parsed as invalid
            XML.
    """

    resolved_executable = str(executable) if executable is not None else shutil.which(tool)
    if resolved_executable is None:
        raise FileNotFoundError(f"{tool!r} was not found on PATH")

    file_path = str(path)
    if tool == "exiftool":
        # -struct keeps structured XMP values nested, which is easier and more
        # reliable to normalize than flattened tag strings.
        completed = _run_exiftool(resolved_executable, ["-j", "-G1", "-struct", _exiftool_file_arg(path)])
        return parse_metadata_text(completed.stdout, source_format="exiftool-json", standard=standard)

    # exiv2 -pa joins the items of XMP arrays with ", ", which cannot be split
    # reliably, and does not print the image size. Image Regions are therefore
    # read from the raw XMP packet (-pX) and the image size from the summary (-ps).
    packet = _run_exiv2(resolved_executable, ["-pX", file_path])
    data = xmp_image_region_data(packet) if packet.strip() else {}
    # The summary still lists the image size when the file has no Exif block, but
    # Exiv2 then exits with code 253 ("No Exif data found in the file").
    summary = _run_exiv2(resolved_executable, ["-ps", file_path], allowed_exit_codes=(0, _EXIV2_NO_EXIF_EXIT_CODE))
    size = _EXIV2_IMAGE_SIZE.search(summary)
    if size is not None and int(size.group(1)) > 0 and int(size.group(2)) > 0:
        data["imageWidth"] = int(size.group(1))
        data["imageHeight"] = int(size.group(2))
    return normalize_metadata(data, source_format="exiv2", standard=standard)


def _depth_order_to_write(
    path: str | Path,
    tool: ToolName,
    executable: str,
    metadata: NormalizedMetadata,
    image_regions: list[dict[str, Any]],
) -> list[str] | None:
    """Return the Image Region Depth Order to write, or None to leave the file's value unchanged.

    A depth order supplied by the caller is written as given. Otherwise the
    file's existing depth order is read and every Region Identifier that is
    not among the written regions is removed, because IPTC requires the depth
    order to reference existing regions only. A renamed region cannot be
    recognised here; its old identifier is removed as well.

    Exiv2 deletes keys by prefix, so removing `Xmp.iptcExt.ImageRegion` also
    removes `Xmp.iptcExt.ImageRegionDepthOrder`. With Exiv2 the remaining
    depth order is therefore always written again.
    """

    if metadata.image_regions.depth_order is not None:
        return metadata.image_regions.depth_order
    try:
        existing = run_metadata_tool(path, tool, executable=executable).image_regions.depth_order
    except (subprocess.CalledProcessError, ValueError, ET.ParseError):
        # The file's metadata cannot be read; the write itself reports real problems.
        return None
    if not isinstance(existing, list):
        return None
    region_ids = {region.get("rId") for region in image_regions if isinstance(region, Mapping)}
    kept = [r_id for r_id in existing if isinstance(r_id, str) and r_id in region_ids]
    if kept == existing and tool != "exiv2":
        return None
    return kept


def _run_exiv2(executable: str, arguments: list[str], *, allowed_exit_codes: tuple[int, ...] = (0,)) -> str:
    """Run Exiv2 and return its standard output decoded as UTF-8.

    Raises:
        subprocess.CalledProcessError: If Exiv2 exits with a code outside
            `allowed_exit_codes`.
    """

    command = [executable, *arguments]
    completed = subprocess.run(
        command,
        input="",
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode not in allowed_exit_codes:
        raise subprocess.CalledProcessError(completed.returncode, command, completed.stdout, completed.stderr)
    return completed.stdout


def write_image_regions(
    path: str | Path,
    regions: NormalizedMetadata | ImageRegionList | list[dict[str, Any]] | dict[str, Any],
    *,
    executable: str | Path | None = None,
    tool: ToolName = "exiftool",
    keep_original: bool = False,
    validate: bool = True,
    registry: IptcPropertyRegistry | None = None,
    fail_on_warning: bool = True,
    standard: Standard | None = None,
) -> subprocess.CompletedProcess[str]:
    """Write canonical Image Region metadata back to an image with ExifTool or Exiv2.

    Args:
        path: Image file path to update.
        regions: Canonical metadata, an `ImageRegionList`, a list of canonical
            Image Region dictionaries, or one canonical Image Region dictionary.
        executable: Optional metadata tool executable path. When omitted, PATH
            is searched for the selected tool.
        tool: Metadata writer, either `exiftool` (default) or `exiv2`.
        keep_original: Keep ExifTool's original backup file when true.
        validate: Reject metadata with validation errors before writing.
        registry: Optional IPTC property registry used to map additional
            ImageRegion metadata when writing with Exiv2.
        fail_on_warning: Raise `MetadataToolWarning` when ExifTool reports a
            warning, because ExifTool may skip values and still succeed.
        standard: Validation profile used before writing. When omitted, the
            standard carried by `NormalizedMetadata`/`ImageRegionList` input is
            used; plain dictionaries and lists use `"2025.1"`. With
            `validate=True`, draft content is refused under `"2025.1"`.

    Returns:
        Completed metadata tool process.

    Raises:
        FileNotFoundError: If the metadata tool cannot be found.
        ValueError: If validation fails.
        subprocess.CalledProcessError: If the tool exits with a non-zero status.
        MetadataToolWarning: If ExifTool reports a warning and
            `fail_on_warning` is true.
    """

    if tool == "exiv2":
        return _write_image_regions_exiv2(
            path,
            regions,
            executable=executable,
            keep_original=keep_original,
            validate=validate,
            registry=registry,
            standard=standard,
        )

    resolved_executable = str(executable) if executable is not None else shutil.which("exiftool")
    if resolved_executable is None:
        raise FileNotFoundError("'exiftool' was not found on PATH")

    metadata = _coerce_image_region_metadata(regions, standard)
    if validate:
        result = metadata.validation_result()
        if result.errors:
            first = result.errors[0]
            raise ValueError(f"{first.path}: {first.message}")

    image_regions = _image_regions_for_exiftool(regions, metadata)
    # -E decodes HTML entities in values, which lets an argument-file line
    # carry line breaks. ExifTool's JSON import would avoid the escaping, but it
    # silently drops fields it does not know, while the inline structure
    # syntax reports them as warnings. Image Regions are XMP only, which is
    # always UTF-8, so no IPTC-IIM CodedCharacterSet is written.
    arguments = ["-E", "-struct"]
    if not keep_original:
        arguments.append("-overwrite_original")
    if image_regions:
        # ExifTool decodes the whole argument and then each structure field,
        # so structure values are entity-encoded twice.
        arguments.append(_exiftool_entities(_exiftool_entities(format_exiftool_image_region_arg(image_regions))))
    else:
        arguments.append("-XMP-iptcExt:ImageRegion=")
    depth_order = _depth_order_to_write(path, "exiftool", resolved_executable, metadata, image_regions)
    arguments.extend(_exiftool_depth_order_args(depth_order))
    arguments.append(_exiftool_file_arg(path))
    completed = _run_exiftool(resolved_executable, arguments)

    messages = _exiftool_problem_messages(completed.stderr)
    if messages and fail_on_warning:
        raise MetadataToolWarning(completed, messages)
    return completed


def _write_image_regions_exiv2(
    path: str | Path,
    regions: NormalizedMetadata | ImageRegionList | list[dict[str, Any]] | dict[str, Any],
    *,
    executable: str | Path | None = None,
    keep_original: bool = False,
    validate: bool = True,
    registry: IptcPropertyRegistry | None = None,
    standard: Standard | None = None,
) -> subprocess.CompletedProcess[str]:
    """Write canonical Image Region metadata back to an image with Exiv2."""

    registry = registry or DEFAULT_IPTC_REGISTRY
    resolved_executable = str(executable) if executable is not None else shutil.which("exiv2")
    if resolved_executable is None:
        raise FileNotFoundError("'exiv2' was not found on PATH")

    metadata = _coerce_image_region_metadata(regions, standard)
    if validate:
        result = metadata.validation_result()
        if result.errors:
            first = result.errors[0]
            raise ValueError(f"{first.path}: {first.message}")

    file_path = Path(path)
    if keep_original:
        shutil.copy2(file_path, Path(str(file_path) + "_original"))

    image_regions = _image_regions_for_exiftool(regions, metadata)
    _raise_if_unregistered_region_extras(image_regions, registry)
    commands = _exiv2_namespace_commands(image_regions, registry)
    commands.append("-Mdel Xmp.iptcExt.ImageRegion")
    if image_regions:
        commands.append('-Mset Xmp.iptcExt.ImageRegion XmpText type="Bag"')
        for index, region in enumerate(image_regions, start=1):
            _append_exiv2_region_commands(commands, index, region, registry)
    _append_exiv2_depth_order(
        commands, _depth_order_to_write(file_path, "exiv2", resolved_executable, metadata, image_regions)
    )

    command = [resolved_executable, *commands, str(file_path)]
    return subprocess.run(
        command,
        input="",
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _run_exiftool(executable: str, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    """Run ExifTool with the bundled config and arguments passed as UTF-8 on stdin.

    On Windows, ExifTool decodes command-line arguments with the ANSI code
    page, which replaces non-ASCII text with `?`. Arguments are therefore
    passed as an argument file on stdin (`-@ -`), together with
    `-charset filename=utf8` so non-ASCII file names work. `-config` must be
    the first command-line argument; it replaces a user's default
    `.ExifTool_config` for this call.

    Raises:
        ValueError: If an argument contains a line break, which an ExifTool
            argument file cannot represent.
        subprocess.CalledProcessError: If ExifTool exits with a non-zero status.
    """

    lines = ["-charset", "filename=utf8", *arguments]
    for line in lines:
        if "\n" in line or "\r" in line:
            raise ValueError(f"ExifTool argument must not contain a line break: {line!r}")
    return subprocess.run(
        [executable, "-config", str(EXIFTOOL_CONFIG), "-@", "-"],
        input="".join(f"{line}\n" for line in lines),
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PERL_BADLANG": "0"},
    )


def _exiftool_entities(text: str) -> str:
    """Encode text for ExifTool's -E option and for one argument-file line.

    Argument-file lines end at a line break and are stripped at both ends, so
    line breaks, tabs, and trailing spaces are written as character entities.
    """

    encoded = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    encoded = encoded.replace("\r", "&#xd;").replace("\n", "&#xa;").replace("\t", "&#x9;")
    stripped = encoded.rstrip(" ")
    return stripped + "&#x20;" * (len(encoded) - len(stripped))


def _exiftool_depth_order_args(depth_order: Any) -> list[str]:
    """Return ExifTool arguments replacing XMP-iptcExt:ImageRegionDepthOrder.

    A missing depth order (None) leaves an existing property in the file
    untouched; an empty list removes it.
    """

    if depth_order is None:
        return []
    tag = "-XMP-iptcExt:ImageRegionDepthOrder"
    values = [value for value in depth_order if value not in (None, "")] if isinstance(depth_order, list) else []
    if not values:
        return [f"{tag}="]
    return [f"{tag}={_exiftool_entities(str(value))}" for value in values]


def _exiftool_file_arg(path: str | Path) -> str:
    """Return an absolute image path; argument-file lines starting with '#' are comments."""

    return os.fspath(Path(path).absolute())


def _exiftool_problem_messages(stderr: str) -> list[str]:
    """Return ExifTool warning and error lines, ignoring its file count summary."""

    return [line.strip() for line in stderr.splitlines() if line.strip().startswith(("Warning:", "Error:"))]


def format_exiftool_image_region_arg(image_regions: list[dict[str, Any]]) -> str:
    """Return the ExifTool `-XMP:ImageRegion=...` argument for canonical regions."""

    exiftool_regions = canonical_to_exiftool_image_regions(image_regions)
    return f"-XMP:ImageRegion={_format_exiftool_struct_value(exiftool_regions)}"


def _format_exiftool_struct_value(value: Any) -> str:
    """Format a value in ExifTool's inline structure syntax.

    Strings are escaped with ExifTool's `|` escape character and otherwise
    written verbatim, so quotes and backslashes are preserved.
    """

    if isinstance(value, dict):
        fields = ", ".join(f"{key}= {_format_exiftool_struct_value(child)}" for key, child in value.items())
        return "{" + fields + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_format_exiftool_struct_value(child) for child in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, str):
        return _escape_exiftool_string(value)
    return str(value)


def canonical_to_exiftool_image_regions(image_regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert canonical Image Region JSON keys to ExifTool struct keys."""

    return [_canonical_region_to_exiftool(region) for region in image_regions]


def _parse_key_value_lines(text: str) -> dict[str, Any]:
    """Parse the simple key/value text shape emitted by tools such as exiv2.

    Args:
        text: Flat key/value metadata output.

    Returns:
        Mapping of metadata keys to scalar values.
    """

    values: dict[str, Any] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key: str
        value: str
        # exiv2 -pa lines commonly look like:
        #   Xmp.foo.Tag XmpText 5 value
        # split(None, 3) preserves the value column even when it contains
        # spaces or lang="..." markers.
        parts = stripped.split(None, 3)
        if len(parts) == 4:
            key, value = parts[0], parts[3]
        elif "=" in stripped:
            key, value = stripped.split("=", 1)
        else:
            if len(parts) >= 2:
                key, value = parts[0], parts[-1]
            else:
                continue
        value = value.strip()
        if _is_structure_marker(value):
            continue
        if len(parts) == 4 and parts[1] in {"XmpSeq", "XmpBag"} and key.endswith("ImageRegionDepthOrder"):
            values[key.strip()] = [item.strip() for item in value.split(", ") if item.strip()]
            continue
        _merge_parsed_value(values, key.strip(), _coerce_scalar(value))
    return values


def _merge_parsed_value(target: dict[str, Any], key: str, value: Any) -> None:
    """Merge duplicate flat metadata keys without dropping earlier values."""

    if key not in target:
        target[key] = value
        return
    current = target[key]
    if isinstance(current, list):
        current.append(value)
    else:
        target[key] = [current, value]


def _coerce_image_region_metadata(
    regions: NormalizedMetadata | ImageRegionList | list[dict[str, Any]] | dict[str, Any],
    standard: Standard | None = None,
) -> NormalizedMetadata:
    """Return a NormalizedMetadata object for supported Image Region inputs.

    An explicit `standard` overrides the standard carried by typed input;
    plain dictionaries and lists without one use the default standard.
    """

    if isinstance(regions, NormalizedMetadata):
        return regions if standard is None else regions.with_standard(standard)
    if isinstance(regions, ImageRegionList):
        return NormalizedMetadata(image_regions=regions if standard is None else regions.with_standard(standard))
    profile = DEFAULT_STANDARD if standard is None else standard
    if isinstance(regions, dict) and "imageRegion" in regions:
        return normalize_metadata(regions, source_format="api", standard=profile)
    if isinstance(regions, dict):
        return normalize_metadata({"imageRegion": [regions]}, source_format="api", standard=profile)
    return normalize_metadata({"imageRegion": regions}, source_format="api", standard=profile)


def _image_regions_for_exiftool(
    regions: NormalizedMetadata | ImageRegionList | list[dict[str, Any]] | dict[str, Any],
    metadata: NormalizedMetadata,
) -> list[dict[str, Any]]:
    """Return canonical region dictionaries in the caller-provided write shape."""

    if isinstance(regions, NormalizedMetadata | ImageRegionList):
        return metadata.image_regions.as_dict_list()
    if isinstance(regions, dict) and "imageRegion" in regions:
        image_regions = regions.get("imageRegion", [])
        return copy.deepcopy(image_regions) if isinstance(image_regions, list) else []
    if isinstance(regions, dict):
        return [copy.deepcopy(regions)]
    return copy.deepcopy(regions)


def _append_exiv2_region_commands(
    commands: list[str],
    index: int,
    region: dict[str, Any],
    registry: IptcPropertyRegistry,
) -> None:
    """Append Exiv2 modify commands for one canonical Image Region."""

    base = f"Xmp.iptcExt.ImageRegion[{index}]"
    commands.append(f'-Mset {base} XmpText type="Struct"')
    for key, value in region.items():
        if key == "rId":
            _append_exiv2_scalar(commands, f"{base}/Iptc4xmpExt:rId", value)
        elif key == "rMemberOf":
            _append_exiv2_scalar(commands, f"{base}/Iptc4xmpExt:rMemberOf", value)
        elif key == "name":
            _append_exiv2_lang_alt(commands, f"{base}/Iptc4xmpExt:Name", value)
        elif key == "regionBoundary":
            _append_exiv2_boundary(commands, f"{base}/Iptc4xmpExt:RegionBoundary", value)
        elif key == "rCtype":
            _append_exiv2_entity_bag(commands, f"{base}/Iptc4xmpExt:rCtype", value, registry)
        elif key == "rRole":
            _append_exiv2_entity_bag(commands, f"{base}/Iptc4xmpExt:rRole", value, registry)
        else:
            child_path = _exiv2_child_path(base, key, registry)
            if child_path:
                _append_exiv2_value(commands, child_path, value, registry=registry, registry_key=key)


def _append_exiv2_depth_order(commands: list[str], depth_order: Any) -> None:
    """Append Exiv2 commands replacing Iptc4xmpExt:ImageRegionDepthOrder.

    A missing depth order (None) leaves an existing property in the file
    untouched; an empty list removes it.
    """

    if depth_order is None:
        return
    path = "Xmp.iptcExt.ImageRegionDepthOrder"
    commands.append(f"-Mdel {path}")
    values = depth_order if isinstance(depth_order, list) else []
    _append_exiv2_array_scalars(commands, path, values, array_type="Seq")


def _append_exiv2_boundary(commands: list[str], path: str, boundary: Any) -> None:
    """Append Exiv2 commands for an IPTC RegionBoundary struct."""

    if not isinstance(boundary, dict):
        return

    commands.append(f'-Mset {path} XmpText type="Struct"')
    mapping = {
        "rbShape": "rbShape",
        "rbUnit": "rbUnit",
        "rbX": "rbX",
        "rbY": "rbY",
        "rbW": "rbW",
        "rbH": "rbH",
        "rbRx": "rbRx",
        "rbCoordinates": "rbCoordinates",
    }
    for key, tag in mapping.items():
        if key in boundary:
            _append_exiv2_scalar(commands, f"{path}/Iptc4xmpExt:{tag}", boundary[key])

    vertices = boundary.get("rbVertices")
    if isinstance(vertices, list) and vertices:
        vertices_path = f"{path}/Iptc4xmpExt:rbVertices"
        commands.append(f'-Mset {vertices_path} XmpText type="Seq"')
        for index, vertex in enumerate(vertices, start=1):
            if not isinstance(vertex, dict):
                continue
            vertex_path = f"{vertices_path}[{index}]"
            commands.append(f'-Mset {vertex_path} XmpText type="Struct"')
            if "rbX" in vertex:
                _append_exiv2_scalar(commands, f"{vertex_path}/Iptc4xmpExt:rbX", vertex["rbX"])
            if "rbY" in vertex:
                _append_exiv2_scalar(commands, f"{vertex_path}/Iptc4xmpExt:rbY", vertex["rbY"])

    part_details = boundary.get("rbMbPartDetails")
    if isinstance(part_details, list) and part_details:
        details_path = f"{path}/Iptc4xmpExt:rbMbPartDetails"
        commands.append(f'-Mset {details_path} XmpText type="Bag"')
        for index, detail in enumerate(part_details, start=1):
            if not isinstance(detail, dict):
                continue
            detail_path = f"{details_path}[{index}]"
            commands.append(f'-Mset {detail_path} XmpText type="Struct"')
            for key in ("rbMbPdPartIndex", "rbMbPdPartId", "rbMbPdPartName", "rbMbPdPartDescription"):
                if key in detail:
                    _append_exiv2_scalar(commands, f"{detail_path}/Iptc4xmpExt:{key}", detail[key])


def _append_exiv2_entity_bag(
    commands: list[str],
    path: str,
    value: Any,
    registry: IptcPropertyRegistry,
) -> None:
    """Append Exiv2 commands for IPTC Entity bags such as rRole and rCtype."""

    entities = value if isinstance(value, list) else [value]
    entities = [entity for entity in entities if isinstance(entity, dict)]
    if not entities:
        return

    commands.append(f'-Mset {path} XmpText type="Bag"')
    for index, entity in enumerate(entities, start=1):
        entity_path = f"{path}[{index}]"
        commands.append(f'-Mset {entity_path} XmpText type="Struct"')
        for key, child in entity.items():
            child_path = _exiv2_struct_child_path(entity_path, key, registry)
            if child_path:
                _append_exiv2_value(commands, child_path, child, registry=registry)


def _append_exiv2_value(
    commands: list[str],
    path: str,
    value: Any,
    *,
    registry: IptcPropertyRegistry | None = None,
    registry_key: str | None = None,
) -> None:
    """Append Exiv2 commands for a generic XMP value."""

    if value is None or value == "":
        return
    registry = registry or DEFAULT_IPTC_REGISTRY
    prop = registry.get(registry_key or "") if registry_key else None
    if isinstance(value, dict):
        if (prop is not None and prop.writer_type == "LangAlt") or _is_lang_alt_dict(value):
            _append_exiv2_lang_alt(commands, path, value)
            return
        commands.append(f'-Mset {path} XmpText type="Struct"')
        for key, child in value.items():
            child_path = _exiv2_struct_child_path(path, key, registry)
            if child_path:
                _append_exiv2_value(commands, child_path, child, registry=registry)
        return
    if isinstance(value, list):
        if not value:
            return
        if all(not isinstance(item, dict) for item in value):
            _append_exiv2_bag_scalars(commands, path, value)
            return
        commands.append(f'-Mset {path} XmpText type="Bag"')
        for index, item in enumerate(value, start=1):
            item_path = f"{path}[{index}]"
            if isinstance(item, dict):
                commands.append(f'-Mset {item_path} XmpText type="Struct"')
                for key, child in item.items():
                    child_path = _exiv2_struct_child_path(item_path, key, registry)
                    if child_path:
                        _append_exiv2_value(commands, child_path, child, registry=registry)
            else:
                _append_exiv2_scalar(commands, item_path, item)
        return
    _append_exiv2_scalar(commands, path, value)


def _append_exiv2_lang_alt(commands: list[str], path: str, value: Any) -> None:
    """Append Exiv2 commands for an XMP LangAlt value."""

    if isinstance(value, dict):
        items = [(language, text) for language, text in value.items() if text not in (None, "")]
    else:
        items = [("x-default", value)] if value not in (None, "") else []
    for language, text in items:
        commands.append(f'-Mset {path} LangAlt lang="{language}" {text}')


def _append_exiv2_bag_scalars(commands: list[str], path: str, values: list[Any]) -> None:
    """Append Exiv2 commands for a bag of scalar values."""

    _append_exiv2_array_scalars(commands, path, values, array_type="Bag")


def _append_exiv2_array_scalars(
    commands: list[str], path: str, values: list[Any], *, array_type: Literal["Bag", "Seq"]
) -> None:
    """Append Exiv2 commands for an XMP array of scalar values.

    Items are written with explicit one-based indexes. Exiv2's `add` command
    creates a separate datum per call, which collapses to the last value in the
    written XMP, so `set` followed by `add` must not be used for arrays.
    """

    clean_values = [value for value in values if value not in (None, "")]
    if not clean_values:
        return
    commands.append(f'-Mset {path} XmpText type="{array_type}"')
    for index, value in enumerate(clean_values, start=1):
        _append_exiv2_scalar(commands, f"{path}[{index}]", value)


def _append_exiv2_scalar(commands: list[str], path: str, value: Any, *, value_type: str = "XmpText") -> None:
    """Append an Exiv2 scalar set command."""

    if value is None or value == "":
        return
    commands.append(f"-Mset {path} {value_type} {value}")


def _exiv2_child_path(parent: str, key: str, registry: IptcPropertyRegistry) -> str:
    """Return an Exiv2 child path for an Image Region metadata key."""

    key = str(key)
    registry_path = registry.exiv2_path(key)
    if registry_path is not None:
        return f"{parent}/{registry_path}"
    if ":" in key and not key.startswith("XMP-"):
        return f"{parent}/{key}"
    return f"{parent}/Iptc4xmpExt:{key}"


def _exiv2_struct_child_path(parent: str, key: str, registry: IptcPropertyRegistry) -> str:
    """Return an Exiv2 child path for a nested struct field."""

    key = str(key)
    if key in {"identifiers", "Identifier"}:
        return f"{parent}/xmp:Identifier"
    if key in {"name", "Name"}:
        return f"{parent}/Iptc4xmpExt:Name"
    if key in {"role", "Role"}:
        return f"{parent}/Iptc4xmpExt:Role"
    return _exiv2_child_path(parent, key, registry)


def _exiv2_namespace_commands(image_regions: list[dict[str, Any]], registry: IptcPropertyRegistry) -> list[str]:
    """Return Exiv2 namespace registrations needed by region metadata."""

    namespaces: dict[str, str] = {"Iptc4xmpExt": IPTC_EXT_NS}
    for region in image_regions:
        for key, _value in _walk_region_extra_values(region):
            path = registry.exiv2_path(str(key))
            if path is None and isinstance(key, str) and ":" in key and not key.startswith("XMP-"):
                path = key
            if path is None:
                continue
            registration = namespace_registration_for_path(path)
            if registration is not None and registration[0].startswith("Iptc4xmp"):
                prefix, uri = registration
                namespaces[prefix] = uri
    return [f"-Mreg {prefix} {uri}" for prefix, uri in namespaces.items()]


def _raise_if_unregistered_region_extras(
    image_regions: list[dict[str, Any]],
    registry: IptcPropertyRegistry,
) -> None:
    """Reject additional ImageRegion fields that cannot be written from registry data."""

    for index, region in enumerate(image_regions):
        for key in region:
            if key in BUILT_IN_REGION_KEYS:
                continue
            if registry.get(str(key)) is None:
                raise ValueError(
                    f"imageRegion[{index}].{key}: no IPTC registry entry for additional ImageRegion metadata"
                )


def _walk_region_extra_values(region: Mapping[str, Any]) -> list[tuple[str, Any]]:
    """Return non-built-in region key/value pairs recursively."""

    items: list[tuple[str, Any]] = []
    for key, value in region.items():
        if key in BUILT_IN_REGION_KEYS:
            continue
        items.append((str(key), value))
        if isinstance(value, Mapping):
            items.extend(_walk_region_extra_values(value))
        elif isinstance(value, list):
            for child in value:
                if isinstance(child, Mapping):
                    items.extend(_walk_region_extra_values(child))
    return items


def _canonical_region_to_exiftool(region: dict[str, Any]) -> dict[str, Any]:
    """Convert one canonical Image Region object to ExifTool's struct spelling."""

    out: dict[str, Any] = {}
    for key, value in region.items():
        if key == "rId":
            out["RId"] = value
        elif key == "rMemberOf":
            out["RMemberOf"] = value
        elif key == "name":
            out["Name"] = value
        elif key == "regionBoundary":
            out["RegionBoundary"] = _canonical_boundary_to_exiftool(value)
        elif key == "rCtype":
            out["RCtype"] = _canonical_entity_list_to_exiftool(value)
        elif key == "rRole":
            out["RRole"] = _canonical_entity_list_to_exiftool(value)
        else:
            out[key] = _canonical_value_to_exiftool(value)
    return _flatten_lang_alt_fields(out)


def _canonical_boundary_to_exiftool(boundary: Any) -> Any:
    """Convert canonical Region Boundary keys to ExifTool spelling."""

    if not isinstance(boundary, dict):
        return boundary

    mapping = {
        "rbShape": "RbShape",
        "rbUnit": "RbUnit",
        "rbX": "RbX",
        "rbY": "RbY",
        "rbW": "RbW",
        "rbH": "RbH",
        "rbRx": "RbRx",
        "rbVertices": "RbVertices",
        "rbCoordinates": "RbCoordinates",
        "rbMbPartDetails": "RbMbPartDetails",
    }
    out: dict[str, Any] = {}
    for key, value in boundary.items():
        key_text = str(key)
        target = mapping.get(key_text, key_text)
        if key_text == "rbVertices" and isinstance(value, list):
            out[target] = [_canonical_vertex_to_exiftool(vertex) for vertex in value]
        elif key_text == "rbMbPartDetails" and isinstance(value, list):
            out[target] = [_canonical_multiboundary_part_detail_to_exiftool(detail) for detail in value]
        else:
            out[target] = _canonical_value_to_exiftool(value)
    return out


def _canonical_vertex_to_exiftool(vertex: Any) -> Any:
    """Convert one canonical polygon vertex to ExifTool spelling."""

    if not isinstance(vertex, dict):
        return vertex
    return {
        ("RbX" if key == "rbX" else "RbY" if key == "rbY" else key): _canonical_value_to_exiftool(value)
        for key, value in vertex.items()
    }


def _canonical_multiboundary_part_detail_to_exiftool(detail: Any) -> Any:
    """Convert one Multiboundary Part Details struct to ExifTool spelling."""

    if not isinstance(detail, dict):
        return detail
    mapping = {
        "rbMbPdPartIndex": "RbMbPdPartIndex",
        "rbMbPdPartId": "RbMbPdPartId",
        "rbMbPdPartName": "RbMbPdPartName",
        "rbMbPdPartDescription": "RbMbPdPartDescription",
    }
    return {mapping.get(key, key): _canonical_value_to_exiftool(value) for key, value in detail.items()}


def _canonical_entity_list_to_exiftool(value: Any) -> Any:
    """Convert canonical Entity-like structs to ExifTool spelling."""

    if isinstance(value, list):
        return [_canonical_entity_to_exiftool(item) for item in value]
    return _canonical_entity_to_exiftool(value)


def _canonical_entity_to_exiftool(value: Any) -> Any:
    """Convert one canonical Entity-like struct to ExifTool spelling."""

    if not isinstance(value, dict):
        return value

    out: dict[str, Any] = {}
    for key, child in value.items():
        if key == "identifiers":
            out["Identifier"] = child
        elif key == "name":
            out["Name"] = child
        elif key == "role":
            out["Role"] = child
        else:
            out[key] = _canonical_value_to_exiftool(child)
    return out


def _canonical_value_to_exiftool(value: Any) -> Any:
    """Recursively convert nested canonical values where their role is generic."""

    if isinstance(value, list):
        return [_canonical_value_to_exiftool(item) for item in value]
    if isinstance(value, dict):
        if _is_entity_dict(value):
            return _canonical_entity_to_exiftool(value)
        return {key: _canonical_value_to_exiftool(child) for key, child in value.items()}
    return value


def _flatten_lang_alt_fields(data: Any) -> Any:
    """Flatten LangAlt dict values into ExifTool struct language keys."""

    if isinstance(data, list):
        return [_flatten_lang_alt_fields(item) for item in data]
    if not isinstance(data, dict):
        return data

    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict) and _is_lang_alt_dict(value):
            for language, text in value.items():
                out[f"{key}-{language}"] = _flatten_lang_alt_fields(text)
        else:
            out[key] = _flatten_lang_alt_fields(value)
    return out


def _is_lang_alt_dict(value: dict[str, Any]) -> bool:
    """Return whether a dict looks like an XMP LangAlt value."""

    return bool(value) and all(isinstance(key, str) and LANG_ALT_KEY_RE.match(key) for key in value)


def _is_entity_dict(value: dict[str, Any]) -> bool:
    """Return whether a dict looks like an IPTC entity struct."""

    return any(key in value for key in ("Identifier", "identifiers", "Role", "role"))


def _escape_exiftool_string(value: str) -> str:
    """Escape one string for ExifTool's struct assignment syntax."""

    if not value:
        return value
    escaped = value.replace("|", "||")
    escaped = escaped.replace(",", "|,")
    escaped = escaped.replace("]", "|]")
    escaped = escaped.replace("}", "|}")
    escaped = escaped.replace(")", "|)")
    if escaped[0] in "{[(" or escaped[0].isspace():
        escaped = "|" + escaped
    return escaped


def _is_structure_marker(value: str) -> bool:
    """Return whether a metadata-tool value only describes an XMP container."""

    return value in {'type="Struct"', 'type="Bag"', 'type="Seq"', "type='Struct'", "type='Bag'", "type='Seq'"}


def _coerce_scalar(value: str) -> Any:
    """Convert obvious numeric strings while leaving metadata text unchanged."""

    if value == "":
        return value
    try:
        if "." not in value:
            return int(value)
        return float(value)
    except ValueError:
        return value
