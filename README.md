# IPTC-IRIS

**IPTC-IRIS (IPTC - Image Region Integrity System)**: validation, normalisation,
and reasoning for IPTC Image Region metadata.

> IPTC-IRIS is an independent open-source project. It is not an official IPTC
> product and has not been endorsed by IPTC. See [Relationship to IPTC](#relationship-to-iptc).

[![pypi](https://img.shields.io/pypi/v/iptc-iris)](https://pypi.org/project/iptc-iris/)
![Python Version 3.11,3.12,3.13,3.14](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue?style=flat&logo=python&logoColor=white)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)


[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![pep8](https://img.shields.io/badge/code%20style-pep8-orange.svg)](https://www.python.org/dev/peps/pep-0008/)
![PyPI - Types](https://img.shields.io/pypi/types/iptc-iris)

[![Tests](https://github.com/GraffitiProjectINDIGO/iptc-iris/actions/workflows/tests.yml/badge.svg)](https://github.com/GraffitiProjectINDIGO/iptc-iris/actions/workflows/tests.yml)
&emsp;&emsp;


Project documentation for installing, using, and validating IPTC Image Region metadata with IPTC-IRIS.

| | Name |
| --- | --- |
| PyPI package | `pip install iptc-iris` |
| Python import | `import iptc_iris` |
| Command line | `iptc-iris validate photo.jpg` |

`iptc-iris` normalizes IPTC Image Region metadata from common tool outputs and validates it against the IPTC Photo Metadata Image Region rules.

It also provides a Python API for creating IPTC-conformant Image Regions directly and changing Image Region units.

Supported input forms:

- Canonical IPTC JSON, for example `{"imageRegion": [...]}`
- ExifTool-style JSON, including structured `ImageRegion` values
- Exiv2-style flat keys such as `Xmp.iptcExt.ImageRegion[1]/RegionBoundary/rbShape`
- XMP sidecar files or embedded XMP packets found inside image files

The validator targets Python 3.11, 3.12, 3.13, and 3.14 and has no runtime dependencies.

## What You Can Do

- Normalize IPTC Image Region metadata from JSON, XMP sidecars, embedded XMP
  packets, ExifTool JSON, and Exiv2-style flat tag output.
- Validate Image Region structure, geometry fields, units, dimensions,
  duplicate identifiers, duplicate names, and Entity array shapes.
- Create IPTC-conformant Image Regions directly with the Python API using typed
  rectangle, circle, polygon, point, multipoint, linestring, multilinestring,
  multipolygon, vertex, region, and region-list classes.
- Convert region geometry between relative and pixel units when image
  dimensions are available.
- Load metadata from files or route images through ExifTool/Exiv2 when full
  metadata extraction is needed.
- Render normalized Image Region JSON, annotated JSONC-style output with
  validation comments, or machine-readable validation results.
- Use the CLI for single files, wildcard paths, JSON output, colorized terminal
  output, and annotated `.jsonc` files.

## Install for Development

```powershell
python -m pip install -e .[develop]
```

The same checks as in the GitHub workflow can then be run locally:

```powershell
python -m pytest
python -m ruff check
python -m ruff format --check
python -m pyright
```

Ruff and pyright are pinned in the `develop` extra, so local runs and CI report
the same results. The workflow additionally runs the tests on Linux, macOS, and
Windows with Python 3.11 to 3.14.

Tests that call ExifTool or Exiv2 are skipped unless the tools are on `PATH`
(see [External Metadata Tools](#external-metadata-tools)). They write into a
small self-made JPEG, so no image files are needed.

The repository contains no third-party images. A few tests and examples also
read real-world example photos, such as IPTC's published Photo Metadata example
images, when they are placed in `example_data/` (for example
`photo-4iptc-heads.jpg` and `photo-stalactite-stalagmite.jpg`); otherwise they
are skipped. Image files in `example_data/` are ignored by git.

## External Metadata Tools

`iptc-iris` can parse `.xmp` sidecars directly and has a lightweight fallback
that scans image files for an embedded XMP packet. This is not a full
RAW/TIFF/HEIF/PNG metadata parser. For reliable metadata extraction from image
container formats, install either ExifTool or Exiv2 and use the CLI or API
wrappers.

Common install options:

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install libimage-exiftool-perl exiv2
```

```bash
# macOS with Homebrew
brew install exiftool exiv2
```

```powershell
# Windows with Chocolatey for ExifTool
choco install exiftool -y
```

For Windows Exiv2, download a Windows build from the Exiv2 downloads page,
extract it, and use the path to `bin\exiv2.exe`. For Windows ExifTool, the
official zip also works; keep the `exiftool_files` folder next to
`exiftool.exe`.

Useful upstream pages:

- https://exiftool.org/install.html
- https://exiv2.org/download.html

### Choosing the Engine in Python

The Python API needs no configuration file. Every call states which engine it
uses, and every setting is a function argument:

| Task | Function | Engine |
| --- | --- | --- |
| Read JSON, XMP sidecars, or embedded XMP | `load_metadata_file(path)` | built-in parser, no external tool |
| Read an image through a metadata tool | `run_metadata_tool(path, tool)` | `tool="exiftool"` or `tool="exiv2"` |
| Write Image Regions into an image | `write_image_regions(path, regions, tool=...)` | `tool="exiftool"` (default) or `tool="exiv2"` |

`executable=` selects the program. When it is omitted, the tool is looked up on
`PATH` by name (`exiftool` or `exiv2`); when it is given, that command or path
is used as is:

```python
from iptc_iris import load_metadata_file, run_metadata_tool, write_image_regions

# Built-in reader, no external tool.
metadata = load_metadata_file("photo.xmp")

# ExifTool or Exiv2 from PATH.
metadata = run_metadata_tool("photo.jpg", "exiftool")
metadata = run_metadata_tool("photo.jpg", "exiv2")

# A tool that is not on PATH.
metadata = run_metadata_tool("photo.jpg", "exiv2", executable=r"C:\Tools\exiv2\bin\exiv2.exe")

# Writing chooses its engine the same way; ExifTool is the default.
write_image_regions("photo.jpg", metadata)
write_image_regions("photo.jpg", metadata, tool="exiv2", executable=r"C:\Tools\exiv2\bin\exiv2.exe")
```

Reading and writing are independent: an application can read with one tool and
write with the other. A missing tool raises `FileNotFoundError`.

The validation standard is also an argument (`standard=`) and not a global
setting; see [Standard Profiles](#standard-profiles).

`run_metadata_tool()` accepts one file path. For multiple images, iterate in
Python:

```python
from pathlib import Path

from iptc_iris import run_metadata_tool

for image_path in Path("images").glob("*.jpg"):
    metadata = run_metadata_tool(image_path, "exiftool")
    print(image_path, metadata.valid)
```

### Writing Image Regions

`write_image_regions()` writes Image Regions back into an image with ExifTool
(default) or Exiv2:

```python
from iptc_iris import MetadataToolWarning, load_metadata_file, write_image_regions

metadata = load_metadata_file("regions.json")
try:
    write_image_regions("photo.jpg", metadata, tool="exiftool")
except MetadataToolWarning as warning:
    print("ExifTool reported:", warning.messages)
```

- The regions are validated first; validation errors raise `ValueError` before
  the tool runs. Pass `validate=False` to skip this. Validation uses the data's
  standard or `standard=`; draft content under `"2025.1"` is refused (see
  [Standard Profiles](#standard-profiles)).
- The complete `Iptc4xmpExt:ImageRegion` list in the file is replaced. Other
  metadata is left untouched. `keep_original=True` keeps a backup copy.
- A depth order in the metadata (see
  [Image Region Depth Order](#image-region-depth-order)) is written as given;
  an empty list removes it. If the metadata has no depth order, the file's
  existing one is kept, but Region Identifiers of regions that are no longer
  written are removed from it, because the depth order may only reference
  existing regions. A renamed region cannot be recognised this way; use
  `ImageRegionList.rename_region()` and pass the depth order to keep its
  position.
- Only XMP is written. No legacy IPTC-IIM block is created or changed.

**ExifTool configuration.** ExifTool (checked with 13.58) does not define the
IPTC 2026.1 Image Region fields yet. Without help it silently drops
`rbCoordinates`, `rbMbPartDetails`, and the new `rbShape` values, and refuses
`rMemberOf` and `ImageRegionDepthOrder`. `iptc-iris` therefore ships an ExifTool
config file that extends ExifTool's own `ImageRegion` definition, and passes it
with `-config` whenever it reads or writes with ExifTool. Its path is available
as `iptc_iris.io.EXIFTOOL_CONFIG` if you want to use it with ExifTool directly:

```powershell
exiftool -config "<path to exiftool_iptc_2026.config>" -j -struct -XMP-iptcExt:ImageRegion photo.jpg
```

Because ExifTool accepts only one config file, a personal `.ExifTool_config` is
not loaded for the calls that `iptc-iris` makes.

**Warnings.** ExifTool may skip a value it cannot write and still report
success. `write_image_regions()` therefore raises `MetadataToolWarning` (a
`RuntimeError`) by default when ExifTool prints a `Warning:` or `Error:` line.
`warning.messages` lists them and `warning.completed` holds the finished
process. The image may already have been modified when this is raised. Pass
`fail_on_warning=False` to accept warnings; they remain in `completed.stderr`.
This check applies to ExifTool only.

**Character encoding.** ExifTool arguments, including the file name, are passed
as a UTF-8 argument file on standard input instead of on the command line. This
keeps non-ASCII text, emoji, line breaks, and non-ASCII file names intact on
Windows, where command-line arguments are otherwise converted to the ANSI code
page. Exiv2 handles UTF-8 arguments itself.

**Exiv2 notes.** When reading with Exiv2, Image Regions are taken from the raw
XMP packet (`exiv2 -pX`) and the image size from the summary (`exiv2 -ps`).
`exiv2 -pa` is not used for regions because it joins the items of XMP lists
with commas. ExifTool and Exiv2 therefore return the same data. When writing,
Exiv2 removes trailing spaces from text values; ExifTool keeps them.

## CLI

```powershell
iptc-iris validate metadata.json
iptc-iris validate sidecar.xmp --json
iptc-iris validate photo.jpg
iptc-iris validate "*.json"
iptc-iris validate photo.jpg --image-region
iptc-iris validate photo.jpg --image-region --annotate
iptc-iris validate photo.jpg --image-region --annotate regions.jsonc
iptc-iris validate photo.jpg --color always
iptc-iris convert metadata.json --to pixel --image-width 1000 --image-height 800
iptc-iris convert photo.jpg --to relative --tool exiftool
iptc-iris fix metadata.json
iptc-iris validate photo.jpg --standard 2026.1-draft
```

`validate`, `convert`, and `fix` validate against the published standard
`2025.1` unless `--standard 2026.1-draft` is given (see
[Standard Profiles](#standard-profiles)) or a default is set in the
[configuration file](#configuration-file-iptc-iristoml).

The path argument supports wildcards, including on Windows shells that do not
expand them automatically. Human output is grouped by file. `--json` always
includes a `path` field; with multiple files it returns a list of validation
results. `--image-region` always includes `path` and `imageRegion`; with
multiple files it returns a list of those objects.

To print only the normalized Image Region array to the console, use
`--image-region`. This output uses standard ANSI JSON syntax colors when color
is enabled:

```powershell
iptc-iris validate metadata.json --image-region
iptc-iris validate metadata.json --image-region --color always
```

To show validation messages directly next to the affected Image Region fields,
add `--annotate`. This emits JSONC-style text with `//` comments and is not
standard JSON. If a path is provided, it must end with `.jsonc`; written files
are plain JSONC without ANSI color codes:

```powershell
iptc-iris validate metadata.json --image-region --annotate
iptc-iris validate metadata.json --image-region --annotate regions.jsonc
```

Human-readable validation output colorizes fields with errors in red and
warnings in yellow when stdout is an interactive terminal. Image Region JSON
output colorizes field names and values; fields with validation errors are red
and fields with warnings are yellow. Extra, currently unchecked Image Region
metadata fields are white. Use `--color always` or `--color never` to override
this behavior.

### Choosing the Engine on the Command Line

Without options, the CLI reads JSON and XMP files and the embedded XMP packet of
images with its built-in parser. `--tool` reads through ExifTool or Exiv2 from
`PATH` instead:

```powershell
iptc-iris validate photo.jpg --tool exiftool
iptc-iris validate photo.jpg --tool exiv2
```

If a tool is not on `PATH`, pass its executable. Supplying `--exiftool` or
`--exiv2` also selects that tool, so `--tool` is only needed when both paths are
given:

```powershell
iptc-iris validate photo.jpg --exiftool "C:\Tools\exiftool\exiftool.exe"
iptc-iris validate photo.jpg --exiv2 "C:\Tools\exiv2\bin\exiv2.exe"
```

Tool paths that are used on every run can be stored in the configuration file.

### Configuration File (`iptc-iris.toml`)

The CLI can read default settings from an optional `iptc-iris.toml` file, so
machine-specific options do not have to be repeated on every command. It is
read from the current working directory, or from the file given with
`--config`. A missing file is not an error; the built-in defaults are used.

```toml
[tools]
# Executables used when a tool is selected with --tool.
exiftool = "C:/Tools/exiftool/exiftool.exe"
exiv2 = "C:/Tools/exiv2/bin/exiv2.exe"

[validation]
# Standard profile for validate, convert, and fix: "2025.1" (default) or "2026.1-draft".
standard = "2026.1-draft"
```

```powershell
iptc-iris validate photo.jpg --tool exiftool --config .\iptc-iris.toml
```

Every setting is optional. Command-line options take precedence over the file,
and the file takes precedence over the built-in defaults:

| Setting | Command-line option | Config key | Default |
| --- | --- | --- | --- |
| ExifTool executable | `--exiftool` | `[tools] exiftool` | `exiftool` on `PATH` |
| Exiv2 executable | `--exiv2` | `[tools] exiv2` | `exiv2` on `PATH` |
| Validation standard | `--standard` | `[validation] standard` | `2025.1` |

The file only selects *which* executable is used. A tool is still only used
when it is chosen with `--tool`, `--exiftool`, or `--exiv2`.

The file is used by the command line only. The Python API never reads it; there,
the same settings are passed as `tool=`, `executable=`, and `standard=` (see
[Choosing the Engine in Python](#choosing-the-engine-in-python)). The file is
separate from `pyproject.toml` because it holds local machine settings, not
package metadata.

### Convert Units

Use `iptc-iris convert` to convert Image Region boundaries between `relative`
and `pixel` units. Conversion is strict: the command validates all matched Image
Regions first, and if any file has validation errors no converted output is
written.

```powershell
iptc-iris convert metadata.json --to pixel --image-width 1000 --image-height 800
iptc-iris convert metadata.json --to relative --image-width 1000 --image-height 800
iptc-iris convert photo.jpg --to relative --tool exiftool
```

If image dimensions are already present in the metadata, they are used
automatically. Otherwise pass `--image-width` and `--image-height`. These
dimensions are required whenever actual pixel/relative conversion is needed.
For image files, using `--tool exiftool` or `--tool exiv2` may provide image
dimensions from the file metadata even when the embedded XMP packet does not
contain them.

By default, converted output is written to stdout as canonical normalized JSON:

```json
{
  "path": "metadata.json",
  "imageRegion": []
}
```

For a single input file, write JSON to a specific path:

```powershell
iptc-iris convert metadata.json --to pixel --image-width 1000 --image-height 800 --output converted.json
```

For wildcard input, `--output` writes one batch JSON file that can be passed to
the next `iptc-iris` command:

```powershell
iptc-iris convert "*.json" --to relative --image-width 1000 --image-height 800 --output converted.json
```

The batch shape is:

```json
{
  "files": [
    {
      "path": "metadata.json",
      "imageRegion": []
    }
  ]
}
```

Use `--output-dir` when you want one JSON file per input file instead:

```powershell
iptc-iris convert "*.json" --to relative --image-width 1000 --image-height 800 --output-dir converted
```

`convert` does not write metadata back into image files and has no `--inplace`
mode. Updating image metadata is intentionally kept separate because it is a
destructive, tool-specific operation that needs explicit backup and write-policy
decisions.

### Fix Safe Cleanup Issues

Use `iptc-iris fix` to remove unsupported boundary or vertex fields when every
validation error is safely fixable by removal:

```powershell
iptc-iris fix metadata.json
iptc-iris fix metadata.json --output fixed.json
iptc-iris fix "*.json" --output fixed.json
iptc-iris fix "*.json" --output-dir fixed
iptc-iris fix metadata.json --dry-run
```

The first version is intentionally conservative. It only fixes:

- `UNKNOWN_BOUNDARY_FIELD`
- `UNKNOWN_VERTEX_FIELD`
- `FORBIDDEN_BOUNDARY_FIELD`

It does not change `rbShape`, infer geometry, add missing coordinates, convert
units, or write metadata back into image files. Already-valid input is written
back as canonical JSON with an empty `fixes` list, which makes `fix` useful as
an idempotent step in a processing chain. If the metadata has any non-fixable
error, `fix` exits non-zero and produces no JSON output or output file.
Diagnostic details are written to stderr instead.

For wildcard input, `--output` writes a single batch JSON file using the same
`{"files": [...]}` shape shown above. `validate`, `fix`, and `convert` can read
that batch file directly. Use `--output-dir` when you want one JSON file per
input file instead.

### CLI Workflows

The commands are designed to be chained conservatively:

1. `validate` first.
2. `fix` writes canonical JSON when the input is valid or every error is safely
   fixable.
3. `convert` changes units, starting from valid metadata or from the output of
   `fix`.

`fix` and `convert` only write JSON. They never write metadata back into image
files; use `write_image_regions()` from the
[Python API](#writing-image-regions) for that.

For one metadata file, validate, fix into a new JSON file, convert units from
that file, and validate the result. This runs as shown from the repository root
(`output/` is ignored by git):

```powershell
mkdir output

iptc-iris validate example_data\regions-fixable.json
iptc-iris fix example_data\regions-fixable.json --output output\regions.fixed.json
iptc-iris convert output\regions.fixed.json --to pixel --image-width 1000 --image-height 800 --output output\regions.pixel.json
iptc-iris validate output\regions.pixel.json
```

For image files, read through ExifTool or Exiv2 when the built-in embedded-XMP
reader is not enough:

```powershell
iptc-iris validate photo.jpg --tool exiftool
iptc-iris convert photo.jpg --to relative --tool exiftool --output output\photo.relative.json
```

For a folder, use wildcards and write one batch JSON file for the next step in
the chain:

```powershell
iptc-iris validate "metadata\*.json"
iptc-iris fix "metadata\*.json" --output output\fixed.json
iptc-iris convert output\fixed.json --to pixel --image-width 1000 --image-height 800 --output output\pixel.json
iptc-iris validate output\pixel.json
```

With several inputs, `fix` is all or nothing: if any file has an error that
cannot be fixed safely, it writes no output at all, exits non-zero, and lists
the remaining errors on stderr. Correct or remove those files first; the
`validate` step shows which ones they are. The same applies to `convert`, which
skips the whole batch if any file is invalid. Use `--output-dir` instead of
`--output` to get one JSON file per input.

## Python API

```python
from iptc_iris import RectangleBoundary, load_metadata_file

metadata = load_metadata_file("metadata.json")
result = metadata.validation_result()

region = metadata.image_regions[0]
if isinstance(region.boundary, RectangleBoundary):
    print(region.boundary.width, region.boundary.height)

if not result.valid:
    for issue in result.errors:
        print(issue.path, issue.message)
```

`load_metadata_file()` returns `NormalizedMetadata`, which exposes
`validate()`, `validation_result()`, `valid`, `errors`, and `warnings`.
Validation issues have the severity `error` (invalid), `warning` (valid, but
not recommended), or `info` (a hint such as deprecated usage; never affects
`valid`). `ValidationResult.infos` lists the info issues.
Geometry boundaries are represented by typed classes such as `RectangleBoundary`,
`CircleBoundary`, `PolygonBoundary`, `PointBoundary`, `LineStringBoundary`, and
`MultiPolygonBoundary`.

### Creating Image Regions

Use the typed geometry classes to create IPTC-conformant Image Region objects
directly in Python. Relative units use values in the `0..1` range:

```python
from iptc_iris import ImageRegion, RectangleBoundary

region = ImageRegion(
    r_id="region-1",
    name={"x-default": "Face"},
    boundary=RectangleBoundary(
        unit="relative",
        x=0.1,
        y=0.2,
        width=0.3,
        height=0.4,
    ),
)

assert region.valid
```

Circle and vertex-based polygon boundaries use the same pattern:

```python
from iptc_iris import CircleBoundary, ImageRegion, PolygonBoundary, Vertex

circle_region = ImageRegion(
    r_id="region-2",
    boundary=CircleBoundary(unit="relative", x=0.5, y=0.5, radius=0.2),
)

polygon_region = ImageRegion(
    r_id="region-3",
    boundary=PolygonBoundary(
        unit="relative",
        vertices=[
            Vertex(x=0.1, y=0.1),
            Vertex(x=0.4, y=0.1),
            Vertex(x=0.3, y=0.5),
        ],
    ),
)
```

The IPTC Boundary Coordinates shapes (2026.1 draft) use `rbCoordinates` through
`PointBoundary`, `MultiPointBoundary`, `LineStringBoundary`,
`MultiLineStringBoundary`, `PolygonBoundary`, and `MultiPolygonBoundary`. The
classes can always be built; a region list only accepts them with
`standard="2026.1-draft"` (see [Standard Profiles](#standard-profiles)):

```python
from iptc_iris import (
    ImageRegion,
    LineStringBoundary,
    MultiPolygonBoundary,
    PointBoundary,
    PolygonBoundary,
)

point_region = ImageRegion(
    r_id="region-4",
    boundary=PointBoundary(unit="relative", coordinates=[0.25, 0.75]),
)

line_region = ImageRegion(
    r_id="region-5",
    boundary=LineStringBoundary(unit="relative", coordinates=[[0.1, 0.2], [0.4, 0.6]]),
)

polygon_with_hole = ImageRegion(
    r_id="region-6",
    boundary=PolygonBoundary(
        unit="relative",
        coordinates=[
            [[0.1, 0.1], [0.8, 0.1], [0.8, 0.8], [0.1, 0.8], [0.1, 0.1]],
            [[0.3, 0.3], [0.5, 0.3], [0.5, 0.5], [0.3, 0.5], [0.3, 0.3]],
        ],
    ),
)

multi_polygon_region = ImageRegion(
    r_id="region-7",
    boundary=MultiPolygonBoundary(
        unit="relative",
        coordinates=[
            [[[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3], [0.1, 0.1]]],
            [[[0.5, 0.5], [0.7, 0.5], [0.7, 0.7], [0.5, 0.7], [0.5, 0.5]]],
        ],
    ),
)
```

Group regions with `ImageRegionList`. The list validates collection-level
rules such as duplicate `rId` and duplicate names:

```python
from iptc_iris import ImageRegionList

regions = ImageRegionList(region, circle_region, polygon_region)

if not regions.valid:
    for issue in regions.errors:
        print(issue.path, issue.message)
```

Pixel regions need image dimensions. Pass them to the region itself or let an
`ImageRegionList` provide them for deferred child regions:

```python
from iptc_iris import ImageRegion, ImageRegionList, RectangleBoundary

pixel_region = ImageRegion(
    r_id="region-4",
    image_width=1000,
    image_height=800,
    boundary=RectangleBoundary(unit="pixel", x=10, y=20, width=100, height=80),
)

regions = ImageRegionList(
    ImageRegion(
        r_id="region-5",
        boundary=RectangleBoundary(unit="pixel", x=250, y=120, width=180, height=140),
        defer_dimensions=True,
    ),
    image_width=1000,
    image_height=800,
)
```

Every object can be exported as canonical Image Region JSON:

```python
print(region.as_dict())
print(regions.as_dict())
```

### Rendering

For Python API use, render regions, region lists, or normalized metadata
directly. You do not need to create a `ValidationRun`; that class is only an
internal CLI adapter for file paths.

```python
from iptc_iris import (
    ImageRegion,
    RectangleBoundary,
    format_annotated_image_region,
    format_image_region,
    format_validation,
)

region = ImageRegion(
    boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4),
)

print(format_image_region(region))
print(format_annotated_image_region(region))
print(format_validation(region))
```

The same helpers accept `ImageRegionList` and `NormalizedMetadata`:

```python
from iptc_iris import load_metadata_file

metadata = load_metadata_file("metadata.json")

print(format_image_region(metadata, color=False))
print(format_annotated_image_region(metadata, color=False))
print(format_validation(metadata))
```

### Safe Fixes

Use `safe_fix_metadata()` to remove unsupported boundary or vertex fields when
all validation errors are safely fixable. The function is non-destructive and
returns fixed metadata plus a fix report:

```python
from iptc_iris import load_metadata_file, safe_fix_metadata

metadata = load_metadata_file("metadata.json")
fix = safe_fix_metadata(metadata)

if fix.metadata is not None:
    print(fix.metadata.as_dict())
    for action in fix.fixes:
        print(action.action, action.path, action.code)
else:
    for issue in fix.original_validation.errors:
        print(issue.path, issue.message)
```

`safe_fix_metadata()` returns already-valid metadata unchanged with no fix
actions, which makes it safe to use as an idempotent normalization/fix step.
It only removes fields reported as
`UNKNOWN_BOUNDARY_FIELD`, `UNKNOWN_VERTEX_FIELD`, or
`FORBIDDEN_BOUNDARY_FIELD`. It does not change `rbShape`, infer geometry, add
missing coordinates, convert units, or write metadata back into image files.
If any non-fixable error is present, `fix.metadata` is `None` and no fixed JSON
should be written.

### Python Workflows

Use the same validate, fix, and convert chain in Python. This example writes
canonical JSON files and keeps the original metadata untouched:

```python
import json
from pathlib import Path

from iptc_iris import NormalizedMetadata, load_metadata_file, safe_fix_metadata


def write_metadata(path: Path, metadata: NormalizedMetadata) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata.as_dict(), indent=2) + "\n", encoding="utf-8")


metadata = load_metadata_file("example_data/regions-fixable.json")
validation = metadata.validation_result(ignore_dimensions=True)

if validation.valid:
    working_metadata = metadata
else:
    fix = safe_fix_metadata(metadata)
    if not fix.fixed or fix.metadata is None:
        raise ValueError("No complete safe fix is available.")
    working_metadata = fix.metadata
    write_metadata(Path("output/regions.fixed.json"), working_metadata)

pixel_regions = working_metadata.image_regions.change_unit(
    "pixel",
    image_width=1000,
    image_height=800,
)
pixel_metadata = NormalizedMetadata(
    image_regions=pixel_regions,
    image_width=1000,
    image_height=800,
)
write_metadata(Path("output/regions.pixel.json"), pixel_metadata)
```

For folders, iterate over the files and apply the same function to each path:

```python
from pathlib import Path

for path in Path("example_data").glob("*.json"):
    metadata = load_metadata_file(path)
    print(path, metadata.validation_result(ignore_dimensions=True).valid)
```

A runnable version is available in
`examples/workflow_validate_fix_convert.py`; the same chain on the command line
is shown in [CLI Workflows](#cli-workflows).

### Pixel Dimensions

Relative Image Region coordinates are self-contained, but pixel coordinates need
the image size for complete validation. A pixel `ImageRegion` therefore requires
`image_width` and `image_height` when created directly:

```python
from iptc_iris import ImageRegion, RectangleBoundary

region = ImageRegion(
    r_id="region-1",
    image_width=1000,
    image_height=800,
    boundary=RectangleBoundary(unit="pixel", x=10, y=20, width=100, height=80),
)

assert region.valid
```

If an `ImageRegionList` should provide the image size, create the child region
with `defer_dimensions=True`:

```python
from iptc_iris import ImageRegion, ImageRegionList, RectangleBoundary

regions = ImageRegionList(
    ImageRegion(
        r_id="region-1",
        boundary=RectangleBoundary(unit="pixel", x=10, y=20, width=100, height=80),
        defer_dimensions=True,
    ),
    image_width=1000,
    image_height=800,
)

assert regions[0].valid
```

`defer_dimensions=True` only relaxes construction. Calling `valid`,
`errors`, `warnings`, or `validate()` on the deferred region still requires
dimensions until they are supplied by a list or by creating a copy:

```python
from iptc_iris import ImageRegion, RectangleBoundary


region = ImageRegion(
    boundary=RectangleBoundary(unit="pixel", x=10, y=20, width=100, height=80),
    defer_dimensions=True,
)

region = region.with_dimensions(image_width=1000, image_height=800)
```

Use `allow_malformed=True` for parsed or intentionally incomplete external
metadata, not for ordinary API construction. Unit conversion with
`change_unit()` is strict: malformed regions must be repaired before they can be
converted.

### Changing Objects

Geometry objects and `ImageRegion` are immutable. To change them, use the
`with_*` helpers or `change_unit()`. These methods return a changed copy and
leave the original object unchanged:

```python
from iptc_iris import ImageRegion, RectangleBoundary

rectangle = RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4)
larger_rectangle = rectangle.with_width(0.4)

assert rectangle.width == 0.3
assert larger_rectangle.width == 0.4

pixel_rectangle = rectangle.change_unit("pixel", image_width=1000, image_height=800)
assert pixel_rectangle.unit == "pixel"
```

Available copy helpers include:

- `RectangleBoundary.with_position()`, `.with_size()`, `.with_width()`, `.with_height()`, `.with_unit()`
- `CircleBoundary.with_position()`, `.with_radius()`, `.with_unit()`
- `PolygonBoundary.with_vertices()`, `.with_coordinates()`, `.with_unit()`
- `PointBoundary.with_coordinates()`, `.with_unit()`
- `MultiPointBoundary.with_coordinates()`, `.with_unit()`
- `LineStringBoundary.with_coordinates()`, `.with_unit()`
- `MultiLineStringBoundary.with_coordinates()`, `.with_unit()`
- `MultiPolygonBoundary.with_coordinates()`, `.with_unit()`
- `Vertex.with_position()`
- `ImageRegion.with_dimensions()`
- `change_unit()` on geometry objects, `ImageRegion`, and `ImageRegionList`

`ImageRegion.with_dimensions()` is the way to complete a deferred pixel region
after creation:

```python
region = ImageRegion(
    boundary=RectangleBoundary(unit="pixel", x=10, y=20, width=100, height=80),
    defer_dimensions=True,
)

completed_region = region.with_dimensions(image_width=1000, image_height=800)

assert completed_region.valid
```

`ImageRegionList` is a mutable container for collection operations:
`add_region()` adds a region to the list after validating the resulting
collection, `delete_region()` removes one by `rId`, and `rename_region()`
changes an `rId`. These methods change the list itself. By contrast,
`ImageRegionList.change_unit()` returns a converted copy of the whole list:

```python
from iptc_iris import ImageRegionList

regions = ImageRegionList(completed_region)
relative_regions = regions.change_unit("relative")

assert regions[0].boundary.unit == "pixel"
assert relative_regions[0].boundary.unit == "relative"
```

IPTC requires references to follow a changed or removed Region Identifier.
`rename_region()` therefore also updates every `rMemberOf` that points to the
old `rId` and its entry in the Image Region Depth Order. `delete_region()`
removes the deleted `rId` from the depth order and removes `rMemberOf` from
regions that were members of the deleted region; those regions stay as
independent regions. `rename_region()` raises `ValueError` if the new `rId` is
empty or already used:

```python
from iptc_iris import ImageRegion, ImageRegionList, PointBoundary

regions = ImageRegionList(
    [
        ImageRegion(r_id="lead", boundary=PointBoundary(unit="relative", coordinates=[0.2, 0.2])),
        ImageRegion(
            r_id="member",
            r_member_of="lead",
            boundary=PointBoundary(unit="relative", coordinates=[0.6, 0.6]),
        ),
    ],
    depth_order=["member", "lead"],
    standard="2026.1-draft",
)

regions.rename_region("lead", "speaker")

assert regions[1].r_member_of == "speaker"
assert regions.depth_order == ["member", "speaker"]
```

### Multiboundary Part Details

A multipoint, multilinestring, or multipolygon boundary may describe its
individual parts with `rbMbPartDetails` (IPTC 2026.1 draft). Each entry refers
to one part through `rbMbPdPartIndex`, the zero-based position of the part in
the top-level `rbCoordinates` array, and may carry a Part Id, Part Name, and
Part Description:

```json
{
  "rbShape": "multipoint",
  "rbUnit": "relative",
  "rbCoordinates": "[[0.1,0.1],[0.5,0.5]]",
  "rbMbPartDetails": [
    {"rbMbPdPartIndex": 1, "rbMbPdPartId": "p2", "rbMbPdPartName": "Right hand"}
  ]
}
```

Part details are documentary only: they do not change the geometry, and parts
do not become Image Regions of their own. Details may be given for some parts
only.

Because the link is a position, inserting, removing, or reordering parts must
renumber every Part Index. IPTC recommends keeping each part's coordinates and
details together while editing and assigning the Part Index only when writing.
`MultiboundaryPart` is that coupled form. `parts()` returns the parts of a
boundary with their details, and `with_parts()` builds a boundary from parts in
their new order, assigning fresh Part Index values:

```python
from iptc_iris import MultiboundaryPart, MultiPointBoundary

boundary = MultiPointBoundary(
    unit="relative",
    coordinates=[[0.1, 0.1], [0.5, 0.5], [0.8, 0.2]],
    part_details=[{"rbMbPdPartIndex": 2, "rbMbPdPartName": "Third"}],
)

parts = boundary.parts()
assert parts[2].part_name == "Third"

without_first = boundary.with_parts(parts[1:])
assert without_first.part_details == [{"rbMbPdPartIndex": 1, "rbMbPdPartName": "Third"}]

added = without_first.with_parts([*without_first.parts(), MultiboundaryPart([0.9, 0.9], part_name="New")])
assert added.part_details[-1] == {"rbMbPdPartIndex": 2, "rbMbPdPartName": "New"}
```

Applications that keep regions as plain JSON can use the same logic on the raw
values with `split_multiboundary_parts()` and `join_multiboundary_parts()`:

```python
from iptc_iris import join_multiboundary_parts, split_multiboundary_parts

raw = {
    "rbCoordinates": "[[0.1,0.1],[0.5,0.5]]",
    "rbMbPartDetails": [{"rbMbPdPartIndex": 0, "rbMbPdPartId": "left"}],
}
parts = split_multiboundary_parts(raw["rbCoordinates"], raw["rbMbPartDetails"])
coordinates, details = join_multiboundary_parts(list(reversed(parts)))

assert coordinates == [[0.5, 0.5], [0.1, 0.1]]
assert details == [{"rbMbPdPartIndex": 1, "rbMbPdPartId": "left"}]
```

When existing Image Regions are combined into one multi-boundary region, IPTC
allows initialising each part's Part Id, Part Name, and Part Description from
the source region's `rId`, name, and description.

### Image Region Depth Order

`imageRegionDepthOrder` (IPTC 2026.1 draft, XMP
`Iptc4xmpExt:ImageRegionDepthOrder`) is an image-level ordered list of Region
Identifiers. The first `rId` is the region closest to the viewer. It does not
have to list every region. `iptc-iris` reads it from canonical JSON, ExifTool,
Exiv2, and XMP input and exposes it as `ImageRegionList.depth_order`:

```python
from iptc_iris import normalize_metadata

metadata = normalize_metadata(
    {
        "imageRegion": [
            {"rId": "front", "regionBoundary": {"rbShape": "point", "rbUnit": "relative", "rbCoordinates": "[0.2,0.2]"}},
            {"rId": "back", "regionBoundary": {"rbShape": "point", "rbUnit": "relative", "rbCoordinates": "[0.6,0.6]"}},
        ],
        "imageRegionDepthOrder": ["front", "back"],
    },
    standard="2026.1-draft",
)

assert metadata.valid
assert metadata.image_regions.depth_order == ["front", "back"]
assert metadata.as_dict()["imageRegionDepthOrder"] == ["front", "back"]
```

`depth_order` is `None` when the property is absent. Each value must be the
`rId` of an existing region and must not repeat. `delete_region()` and
`rename_region()` keep the depth order consistent, and both writers write it
(see [Writing Image Regions](#writing-image-regions)).

### Language Alternatives

IPTC Image Region `name` values are XMP language alternatives (`Lang Alt`).
The normalized API represents them as a mapping from language tag to text:

```python
from iptc_iris import ImageRegion, RectangleBoundary

region = ImageRegion(
    name={"x-default": "Speaker", "de": "Sprecher"},
    boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4),
)

print(region.name["x-default"])
```

The same canonical shape is used for Entity names in `rCtype` and `rRole`:

```python
r_ctype = [
    {
        "identifiers": ["http://cv.iptc.org/newscodes/imageregiontype/human"],
        "name": {"x-default": "human", "de": "Mensch"},
    }
]
```

Different metadata tools expose language alternatives differently. ExifTool
structured JSON may return a plain string such as `"Speaker"`, while Exiv2 text
output may return `lang="x-default" Speaker`. `iptc-iris` normalizes both to:

```python
{"x-default": "Speaker"}
```

Use `x-default` for the fallback display value, and add BCP 47 language tags
such as `en`, `de`, or `fr` when localized labels are available. See the IPTC
Photo Metadata specification for Image Region fields and Adobe's XMP
specification for the XMP data model and RDF serialization:

- https://www.iptc.org/std/photometadata/specification/IPTC-PhotoMetadata-2023.2.html
- https://developer.adobe.com/xmp/docs/xmp-specifications/

## Standard Profiles

The standard is a setting that travels with the data:

```python
from iptc_iris import DEFAULT_STANDARD, IPTC_STANDARDS, Standard
# Standard = Literal["2025.1", "2026.1-draft"]; DEFAULT_STANDARD = "2025.1"
```

- `"2025.1"` is the published IPTC Photo Metadata Standard and the default.
- `"2026.1-draft"` adds the draft "Extended Image Region Boundaries" features
  and must be selected explicitly.
- Reading never depends on the standard. Readers keep everything they find,
  including draft properties. The standard only affects validation and,
  through it, writing.
- Geometry classes stay neutral: a `MultiPolygonBoundary` can always be built.
  Whether it is allowed is decided where a region or region list is validated.

The standard is chosen when data is loaded and stays with it:

```python
from iptc_iris import load_metadata_file, write_image_regions

metadata = load_metadata_file("regions.json")  # standard="2025.1"
metadata.valid  # False if the file contains a multipolygon

metadata = load_metadata_file("regions.json", standard="2026.1-draft")
metadata.valid  # True
metadata.image_regions.standard  # "2026.1-draft"
```

The same `standard=` parameter exists on `normalize_metadata()`,
`parse_metadata_text()`, `run_metadata_tool()`, `ImageRegionList(...)`, and
`ImageRegionList.from_raw(...)`. `.valid`, `.errors`, and `.warnings` always
use the data's standard. To check against another standard without reloading:

```python
result = metadata.validation_result(standard="2025.1")
# "Can a 2025.1 reader use this file?"
```

Writing uses the data's standard unless it is overridden:

```python
write_image_regions("photo.jpg", metadata)  # metadata.image_regions.standard
write_image_regions("photo.jpg", regions_list, standard="2026.1-draft")  # plain dicts/lists
```

With the default `validate=True`, draft content under `"2025.1"` is refused
with `ValueError` before the metadata tool runs. Plain dictionaries and lists
without `standard=` use the default, `"2025.1"`.

Under `"2025.1"`, validation reports draft content as an error:

```text
ERROR  NOT_IN_STANDARD  imageRegion[0].regionBoundary.rbShape:
       multipolygon is not part of IPTC Photo Metadata 2025.1; it is defined by the
       2026.1 draft. Use standard="2026.1-draft" to allow it.
```

This applies to the shapes `point`, `multipoint`, `linestring`,
`multilinestring`, and `multipolygon`; to `rbCoordinates`, including polygons
with holes; and to `rbMbPartDetails`, `rMemberOf`, and `imageRegionDepthOrder`.
The `rbVertices` deprecation hint only appears under the draft, because in
2025.1 `rbVertices` is the only polygon form.

On the command line, use `--standard` with `validate`, `convert`, or `fix`:

```powershell
iptc-iris validate photo.jpg --standard 2026.1-draft
```

or set a default with `[validation] standard` in the
[configuration file](#configuration-file-iptc-iristoml); the option takes
precedence. The Python API does not read the configuration file; pass
`standard=` there.

When writing, depth order pruning stays active under `"2025.1"` as well. It does
not add anything new to the file; it only keeps an existing
`imageRegionDepthOrder` consistent with the written regions.

When 2026.1 is published, a `"2026.1"` profile will be added and become the
default. `"2026.1-draft"` will remain as an alias for a while so existing code
keeps working.

## Validation Scope

The package validates the IPTC Image Region structure. Features marked as
2026.1 draft below are only accepted with `standard="2026.1-draft"` (see
[Standard Profiles](#standard-profiles)):

- `imageRegion` must be a list when present.
- Every region must include one `regionBoundary`.
- `rbShape` must be `rectangle`, `circle`, `polygon`, `point`,
  `multipoint`, `linestring`, `multilinestring`, or `multipolygon`.
- `rbUnit` must be `pixel` or `relative`.
- Rectangle boundaries require `rbX`, `rbY`, `rbW`, and `rbH`.
- Circle boundaries require `rbX`, `rbY`, and `rbRx`.
- Polygon boundaries require either `rbVertices` or `rbCoordinates`, but not
  both; every `rbVertices` vertex requires `rbX` and `rbY`. `rbVertices` is
  deprecated since IPTC 2026.1; under `"2026.1-draft"` it is reported as an
  `info` issue (`DEPRECATED_POLYGON_VERTICES`) that names the replacement.
- Point, multipoint, linestring, multilinestring, and multipolygon boundaries
  require `rbCoordinates`.
- Shape-specific fields from other shapes are rejected.
- Unknown fields inside `regionBoundary` and polygon vertices are rejected.
- Coordinates and dimensions must be numeric, non-negative where appropriate,
  and positive for size/radius fields.
- Relative units must stay within `0..1`; if image dimensions are available,
  pixel units are checked against image width and height.
- Polygon arrays must be closed, have at least three distinct vertices, and must not self-intersect.
- Polygon inner boundaries must stay inside the outer boundary and must not
  intersect it. Inner boundaries must not intersect each other. Boundary touches
  are reported as warnings where IPTC says they should not occur.
- The polygons of a multipolygon must not have overlapping interior areas.
  Holes are not part of a polygon's area, so a polygon may lie inside another
  polygon's hole. Shared boundary vertices or edges are allowed.
- A multipoint must not contain the same point twice, and a multilinestring
  must not contain the same linestring twice, also not in reverse order.
- `rbMbPartDetails` is only allowed for multipoint, multilinestring, and
  multipolygon. Every entry needs a non-negative integer `rbMbPdPartIndex` that
  identifies an existing part, and the same index must not occur twice. Part
  Id, Part Name, and Part Description must be strings.
- `imageRegionDepthOrder` must be a list of Region Identifiers of existing
  regions, without duplicates.
- Region identifiers (`rId`) must be unique. Region names should be unique and duplicate names are reported as warnings.
- Optional `rMemberOf` is a single string referencing another region's `rId`
  in the same image. Self-references and membership cycles are errors. Missing
  targets produce warnings and are ignored when checking relationships; their
  original values are preserved for export. Membership is semantic and imposes
  no geometric constraints. The Python field is `ImageRegion.r_member_of`.
  JSON/XMP and ExifTool/Exiv2 input names are recognized, and both writers emit
  the field (support in the installed metadata tool may vary).
- `rCtype` and `rRole` are checked as Entity arrays. IPTC recommends NewsCodes for these values, but does not make those controlled vocabularies mandatory.

The implementation is based on the IPTC Photo Metadata Standard 2025.1, especially sections 11.20 and 12.6-12.8.
The point, multipoint, linestring, multilinestring, and multipolygon shapes,
polygon holes, `rbCoordinates`, `rbMbPartDetails`, `rMemberOf`, and
`imageRegionDepthOrder` follow the draft "Extended Image Region Boundaries"
submission for version 2026.1 and may change until that version is published:

- https://www.iptc.org/std/photometadata/specification/IPTC-PhotoMetadata-2025.1.html
- https://iptc.org/standards/photo-metadata/iptc-standard/

## Relationship to IPTC

IPTC-IRIS is an independent open-source project. It is not developed or
published by the IPTC (International Press Telecommunications Council), has not
been endorsed by IPTC, and is not an official reference implementation of the
IPTC Photo Metadata Standard (PMS). "IPTC" in the name only refers to the PMS
this package implements.

The maintainers have contributed to the development of the extended Image
Regions specification through discussions with IPTC and implementation
feedback. This involvement does not make IPTC-IRIS authoritative: where this
package and the published PMS differ, the specification applies.

## License

This project is licensed under the MIT License. See [LICENSE](https://github.com/GraffitiProjectINDIGO/iptc-iris/blob/main/LICENSE).

## Development Note

Parts of this package were developed with assistance from AI tools. The project
maintainers are responsible for reviewing, testing, and maintaining the code.
