"""Load Image Region metadata from a file and validate it.

Run from the repository root:

    python examples/load_and_validate_file.py
"""

from __future__ import annotations

from pathlib import Path

from iptc_iris import load_metadata_file

EXAMPLE_FILE = Path(__file__).resolve().parents[1] / "example_data" / "regions-with-errors.json"


def main() -> int:
    metadata = load_metadata_file(EXAMPLE_FILE)
    result = metadata.validation_result()

    print(f"file: {EXAMPLE_FILE}")
    print(f"regions parsed: {len(metadata.image_regions)}")
    print(f"valid: {result.valid}")
    for issue in result.issues:
        print(f"{issue.severity.upper():7} {issue.code:24} {issue.path}: {issue.message}")

    return 0


if __name__ == "__main__":
    main()
