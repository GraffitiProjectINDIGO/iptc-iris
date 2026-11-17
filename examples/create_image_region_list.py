"""Create and manage an ImageRegionList.

Run from the repository root:

    python examples/create_image_region_list.py
"""

from __future__ import annotations

from iptc_iris import ImageRegion, ImageRegionList, NormalizedMetadata, RectangleBoundary


def main() -> int:
    regions = ImageRegionList(
        ImageRegion(
            image_width=1000,
            image_height=800,
            r_id="region-1",
            boundary=RectangleBoundary(unit="pixel", x=10, y=20, width=100, height=80),
            defer_dimensions=True,
        ),
        image_width=1000,
        image_height=800,
    )
    regions.add_region(
        ImageRegion(
            r_id="region-2",
            boundary=RectangleBoundary(unit="pixel", x=250, y=120, width=180, height=140),
            defer_dimensions=True,
        )
    )

    regions.add_region(
        ImageRegion(
            r_id="region-3",
            boundary=RectangleBoundary(unit="pixel", x=500, y=120, width=180, height=140),
            defer_dimensions=True,
        )
    )

    print(f"regions before delete: {len(regions)}")
    print(f"found region-2: {regions.get_region('region-2') is not None}")
    regions.delete_region("region-1")
    print(f"regions after delete: {len(regions)}")

    metadata = NormalizedMetadata(image_regions=regions)
    result = metadata.validation_result()
    print(f"valid: {result.valid}")
    print(metadata.as_dict())
    print(result.valid)

    regions_2 = ImageRegionList(
        ImageRegion(
            r_id="region-1",
            boundary=RectangleBoundary(unit="relative", x=0.6, y=0.4, width=0.1, height=0.1),
            defer_dimensions=True,
        ),
        image_width=1000,
        image_height=800,
    )
    regions_2.add_region(
        ImageRegion(
            r_id="region-2",
            boundary=RectangleBoundary(unit="pixel", x=250, y=120, width=180, height=140),
            defer_dimensions=True,
        )
    )

    regions_2.add_region(
        ImageRegion(
            r_id="region-3",
            boundary=RectangleBoundary(unit="pixel", x=500, y=120, width=180, height=140),
            defer_dimensions=True,
        )
    )
    return 0


if __name__ == "__main__":
    main()
