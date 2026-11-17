"""Create typed Image Region geometry objects directly in Python.

Run from the repository root:

    python examples/create_image_region.py
"""

from __future__ import annotations

from iptc_iris import ImageRegion, ImageRegionList, NormalizedMetadata, RectangleBoundary


def main() -> int:
    region = ImageRegion(
        r_id="created-region-1",
        name={"x-default": "Created rectangle"},
        boundary=RectangleBoundary(
            unit="relative",
            x=0.1,
            y=0.2,
            width=0.3,
            height=0.4,
        ),
    )
    metadata = NormalizedMetadata(image_regions=ImageRegionList(region))

    print(f"valid: {metadata.valid}")
    print(metadata.as_dict())
    return 0 if metadata.valid else 1


if __name__ == "__main__":
    main()
