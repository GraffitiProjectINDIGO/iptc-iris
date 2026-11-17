"""Check one or more files with the Python API and render/store output.

Run from the repository root:

    python examples/check_files_and_render_output.py
"""

from __future__ import annotations

from pathlib import Path
from tempfile import gettempdir

from iptc_iris import (
    format_annotated_image_region,
    format_image_region,
    format_validation,
    load_metadata_file,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DATA = REPO_ROOT / "example_data"
OUTPUT_DIR = Path(gettempdir()) / "iptc-iris-api-render-example"


def check_one_file(path: Path) -> bool:
    """Load one file, validate it, render output, and store rendered files."""

    metadata = load_metadata_file(path)
    result = metadata.validation_result(ignore_dimensions=True)

    print(f"\n== {path.name} ==")
    print(f"regions parsed: {len(metadata.image_regions)}")
    print(f"valid: {result.valid}")
    for issue in result.issues:
        print(f"{issue.severity.upper():7} {issue.code:24} {issue.path}: {issue.message}")

    validation_json = format_validation(metadata, ignore_dimensions=True)
    image_region_json = format_image_region(metadata, color=False, ignore_dimensions=True)
    annotated_jsonc = format_annotated_image_region(metadata, color=False, ignore_dimensions=True)

    print("\nvalidation JSON:")
    print(validation_json)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = path.name.replace(".", "-")
    validation_path = OUTPUT_DIR / f"{stem}.validation.json"
    image_region_path = OUTPUT_DIR / f"{stem}.image-region.json"
    annotated_path = OUTPUT_DIR / f"{stem}.image-region.jsonc"

    validation_path.write_text(validation_json + "\n", encoding="utf-8")
    image_region_path.write_text(image_region_json + "\n", encoding="utf-8")
    annotated_path.write_text(annotated_jsonc + "\n", encoding="utf-8")

    print("\nstored output:")
    print(validation_path)
    print(image_region_path)
    print(annotated_path)

    return result.valid


def check_multiple_files(paths: list[Path]) -> bool:
    """Run the same API flow for several files."""

    print("\n== multiple files ==")
    valid_by_path = {path: check_one_file(path) for path in paths}

    print("\nsummary:")
    for path, valid in valid_by_path.items():
        print(f"{path.name}: {'valid' if valid else 'invalid'}")

    return all(valid_by_path.values())


def main() -> int:
    single_file = EXAMPLE_DATA / "regions-with-errors.json"
    # JSON files are part of the repository. Image files are checked too when you
    # place some in example_data/, for example IPTC's published example photos.
    files = sorted(EXAMPLE_DATA.glob("*.json")) + sorted(EXAMPLE_DATA.glob("*.jpg"))

    check_one_file(single_file)
    check_multiple_files(files)
    return 0


if __name__ == "__main__":
    main()
