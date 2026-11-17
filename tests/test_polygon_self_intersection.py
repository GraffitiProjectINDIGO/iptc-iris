import math
import random
import time

from iptc_iris.geometry.polygon import (
    _adjacent_edges,
    _same_point,
    _segments_intersect,
    polygon_points_self_intersect,
)


def exhaustive_self_intersect(points):
    """Reference: compare every pair of non-adjacent edges."""

    if len(points) >= 2 and _same_point(points[0], points[-1]):
        points = points[:-1]
    if len(points) < 3:
        return False
    edge_count = len(points)
    for first in range(edge_count):
        for second in range(first + 1, edge_count):
            if _adjacent_edges(first, second, edge_count):
                continue
            if _segments_intersect(
                points[first], points[(first + 1) % edge_count], points[second], points[(second + 1) % edge_count]
            ):
                return True
    return False


def wobbly_ring(count, seed=0, jitter=0.0):
    rng = random.Random(seed)
    return [
        (
            1000
            + 800 * math.cos(2 * math.pi * i / count) * (1 + 0.05 * math.sin(40 * math.pi * i / count))
            + jitter * rng.random(),
            1000 + 600 * math.sin(2 * math.pi * i / count) + jitter * rng.random(),
        )
        for i in range(count)
    ]


def test_same_result_as_exhaustive_check_on_random_and_degenerate_polygons():
    cases = []
    for count in (3, 4, 5, 8, 20, 60):
        for seed in range(150):
            rng = random.Random(seed * 1000 + count)
            # Small integer grids produce many touching, collinear and duplicate-vertex cases.
            cases.append([(rng.randint(0, 6), rng.randint(0, 6)) for _ in range(count)])
    for seed in range(30):
        ring = [(round(x, 2), round(y, 2)) for x, y in wobbly_ring(300, seed, jitter=1.0)]
        cases.append(ring)
        crossed = list(ring)
        crossed[5], crossed[7] = crossed[7], crossed[5]
        cases.append(crossed)
    cases += [
        [(0, 0), (4, 0), (4, 4), (2, 0), (0, 4)],  # vertex touching an edge
        [(0, 0), (4, 0), (4, 4), (4, 2), (0, 4)],  # collinear back-tracking
        [(0, 0), (4, 0), (4, 4), (0, 4), (0, 0)],  # explicitly closed square
        [(0, 0), (4, 4), (4, 0), (0, 4)],  # bow tie
    ]
    intersecting = 0
    for points in cases:
        expected = exhaustive_self_intersect(points)
        intersecting += expected
        assert polygon_points_self_intersect(points) == expected, points
    assert 0 < intersecting < len(cases)


def test_large_simple_polygon_is_checked_quickly():
    ring = wobbly_ring(20000)
    start = time.perf_counter()
    assert polygon_points_self_intersect(ring) is False
    assert time.perf_counter() - start < 2.0

    crossed = list(ring)
    crossed[10000], crossed[10002] = crossed[10002], crossed[10000]
    assert polygon_points_self_intersect(crossed) is True
