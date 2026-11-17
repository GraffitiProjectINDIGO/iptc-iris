"""Use direct class initialization for geometry, regions, lists, units, and validation.

Run from the repository root:

    python examples/direct_class_initialization.py
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from iptc_iris import (
    CircleBoundary,
    ImageRegion,
    ImageRegionList,
    NormalizedMetadata,
    PolygonBoundary,
    RectangleBoundary,
    ValidationIssue,
    Vertex,
)

IMAGE_WIDTH = 1000
IMAGE_HEIGHT = 800


def print_title(title: str) -> None:
    print(f"\n== {title} ==")


def print_issues(issues: list[ValidationIssue]) -> None:
    if not issues:
        print("no validation issues")
        return
    for issue in issues:
        print(f"{issue.severity.upper():7} {issue.code:24} {issue.path}: {issue.message}")


def expect_failure(label: str, action: Callable[[], Any]) -> None:
    try:
        action()
    except ValueError as error:
        print(f"{label}: {error}")
    else:
        raise AssertionError(f"{label}: expected ValueError")


def create_geometries() -> tuple[RectangleBoundary, CircleBoundary, PolygonBoundary]:
    print_title("Geometry Objects")

    rectangle = RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4)
    circle = CircleBoundary(unit="pixel", x=500, y=300, radius=40)
    polygon = PolygonBoundary(
        unit="relative",
        vertices=[
            Vertex(x=0.1, y=0.1),
            Vertex(x=0.3, y=0.1),
            Vertex(x=0.2, y=0.3),
        ],
    )

    print(rectangle.as_dict())
    print(circle.as_dict())
    print(polygon.as_dict())

    print("pixel circle without dimensions:")
    print_issues(circle.validate())

    print("pixel circle with dimensions:")
    print_issues(circle.validate(image_width=IMAGE_WIDTH, image_height=IMAGE_HEIGHT))

    expect_failure(
        "invalid relative rectangle",
        lambda: RectangleBoundary(unit="relative", x=0.95, y=0.2, width=0.1, height=0.2),
    )

    return rectangle, circle, polygon


def create_regions(rectangle: RectangleBoundary) -> tuple[ImageRegion, ImageRegion]:
    print_title("ImageRegion Objects")

    relative_region = ImageRegion(
        r_id="relative-region",
        name={"x-default": "Relative rectangle"},
        boundary=rectangle,
    )
    pixel_region = ImageRegion(
        r_id="pixel-region",
        name={"x-default": "Pixel rectangle"},
        image_width=IMAGE_WIDTH,
        image_height=IMAGE_HEIGHT,
        boundary=RectangleBoundary(unit="pixel", x=10, y=20, width=100, height=80),
    )
    deferred_region = ImageRegion(
        r_id="deferred-region",
        boundary=RectangleBoundary(unit="pixel", x=250, y=120, width=180, height=140),
        defer_dimensions=True,
    )

    print(f"relative valid: {relative_region.valid}")
    print(f"pixel valid: {pixel_region.valid}")
    expect_failure("pixel region without dimensions", lambda: ImageRegion(boundary=pixel_region.boundary))
    expect_failure("deferred region before dimensions", lambda: deferred_region.validate())

    completed_region = deferred_region.with_dimensions(image_width=IMAGE_WIDTH, image_height=IMAGE_HEIGHT)
    print(f"deferred after with_dimensions valid: {completed_region.valid}")

    return relative_region, pixel_region


def create_region_list(relative_region: ImageRegion, pixel_region: ImageRegion) -> ImageRegionList:
    print_title("ImageRegionList")

    regions = ImageRegionList([relative_region, pixel_region], image_width=IMAGE_WIDTH, image_height=IMAGE_HEIGHT)
    regions.add_region(
        ImageRegion(
            r_id="added-deferred-region",
            boundary=RectangleBoundary(unit="pixel", x=500, y=120, width=180, height=140),
            defer_dimensions=True,
        )
    )

    metadata = NormalizedMetadata(image_regions=regions)
    result = metadata.validation_result()
    print(f"region count: {len(regions)}")
    print(f"metadata valid: {result.valid}")
    print(metadata.as_dict())

    expect_failure(
        "duplicate region id",
        lambda: regions.add_region(
            ImageRegion(
                r_id="pixel-region",
                boundary=RectangleBoundary(unit="relative", x=0.4, y=0.4, width=0.1, height=0.1),
            )
        ),
    )

    return regions


def convert_units(regions: ImageRegionList) -> None:
    print_title("Unit Conversion")

    relative_regions = regions.change_unit("relative")
    pixel_regions = relative_regions.change_unit("pixel")

    print(relative_regions.as_dict_list()[0]["regionBoundary"])
    print(pixel_regions.as_dict_list()[0]["regionBoundary"])

    expect_failure(
        "change_unit without dimensions",
        lambda: ImageRegionList(
            ImageRegion(
                boundary=RectangleBoundary(unit="relative", x=0.1, y=0.2, width=0.3, height=0.4),
            )
        ).change_unit("pixel"),
    )


def validation_failures() -> None:
    print_title("Validation Failures")

    expect_failure(
        "pixel region outside image",
        lambda: ImageRegionList(
            ImageRegion(
                boundary=RectangleBoundary(unit="pixel", x=950, y=20, width=100, height=80),
                defer_dimensions=True,
            ),
            image_width=IMAGE_WIDTH,
            image_height=IMAGE_HEIGHT,
        ),
    )

    malformed = ImageRegionList.from_raw(
        [
            {
                "rId": 123,
                "regionBoundary": {
                    "rbShape": "rectangle",
                    "rbUnit": "relative",
                    "rbX": 0.1,
                    "rbY": 0.2,
                },
            }
        ],
        allow_malformed=True,
        validate=False,
    )
    print_issues(malformed.validate(ignore_dimensions=True))


def main() -> int:
    rectangle, _circle, _polygon = create_geometries()
    relative_region, pixel_region = create_regions(rectangle)
    regions = create_region_list(relative_region, pixel_region)
    convert_units(regions)
    validation_failures()
    return 0


if __name__ == "__main__":
    main()
