"""Validate, safely fix, and convert Image Region metadata with the Python API.

Run from the repository root:

    python examples/workflow_validate_fix_convert.py
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import gettempdir

from iptc_iris import NormalizedMetadata, load_metadata_file, safe_fix_metadata

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DATA = REPO_ROOT / "example_data"
OUTPUT_DIR = Path(gettempdir()) / "iptc-iris-api-workflow-example"


def write_metadata(path: Path, metadata: NormalizedMetadata) -> None:
    """Write canonical normalized metadata as UTF-8 JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(metadata.as_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def validate_fix_convert(path: Path, *, image_width: int, image_height: int) -> NormalizedMetadata | None:
    """Validate a file, apply safe fixes when possible, and convert to pixels."""

    metadata = load_metadata_file(path)
    validation = metadata.validation_result(ignore_dimensions=True)

    print(f"\n== {path.name} ==")
    print(f"valid before fix: {validation.valid}")
    for issue in validation.errors:
        print(f"error {issue.code}: {issue.path}")

    working_metadata = metadata
    if not validation.valid:
        fix = safe_fix_metadata(metadata)
        if not fix.fixed or fix.metadata is None:
            print("no complete safe fix available; conversion skipped")
            return None

        working_metadata = fix.metadata
        fixed_path = OUTPUT_DIR / f"{path.stem}.fixed.json"
        write_metadata(fixed_path, working_metadata)
        print(f"fixed metadata: {fixed_path}")
        for action in fix.fixes:
            print(f"{action.action} {action.path}")

    converted_regions = working_metadata.image_regions.change_unit(
        "pixel",
        image_width=image_width,
        image_height=image_height,
    )
    converted_metadata = NormalizedMetadata(
        image_regions=converted_regions,
        image_width=image_width,
        image_height=image_height,
        source_format=working_metadata.source_format,
        raw=working_metadata.raw,
    )
    converted_path = OUTPUT_DIR / f"{path.stem}.pixel.json"
    write_metadata(converted_path, converted_metadata)
    print(f"pixel metadata: {converted_path}")
    print(f"valid after conversion: {converted_metadata.valid}")
    return converted_metadata


def process_one_file() -> None:
    """Run the workflow for a single metadata file."""

    validate_fix_convert(
        EXAMPLE_DATA / "regions-fixable.json",
        image_width=1000,
        image_height=800,
    )


def process_folder() -> None:
    """Run the same workflow for every JSON metadata file in a folder."""

    print("\n== folder workflow ==")
    for path in sorted(EXAMPLE_DATA.glob("*.json")):
        validate_fix_convert(path, image_width=1000, image_height=800)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    process_one_file()
    process_folder()
    return 0


if __name__ == "__main__":
    main()
