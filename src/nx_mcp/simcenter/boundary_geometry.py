"""Geometric checks for linear faces covering an axis-aligned rectangular patch.

This does not validate volume topology or arbitrary curved boundaries. Callers
must resolve native face indices and verify mesh identity before passing nodes.
"""

import math
from collections import defaultdict


def inspect_rectangular_patch(polygons, *, plane_x_mm, minimum_yz_mm, maximum_yz_mm):
    tolerance = 1e-7
    dimensions = [plane_x_mm, *minimum_yz_mm, *maximum_yz_mm]
    if len(dimensions) != 5 or any(
        type(v) not in (int, float) or not math.isfinite(v) for v in dimensions
    ):
        raise ValueError("Finite millimeter plane and two-dimensional bounds required")
    ymin, zmin = minimum_yz_mm
    ymax, zmax = maximum_yz_mm
    if ymax <= ymin or zmax <= zmin or not 1 <= len(polygons) <= 10000:
        raise ValueError("Positive rectangle and 1..10000 faces required")
    coordinates = {}
    edges = defaultdict(list)
    faces = set()
    area = 0.0
    for index, polygon in enumerate(polygons):
        if len(polygon) not in (3, 4):
            raise ValueError("Only linear triangular or quadrilateral faces are supported")
        ids = []
        for node in polygon:
            label, xyz = node["label"], node["xyz"]
            if (
                type(label) is not int
                or label <= 0
                or len(xyz) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in xyz)
            ):
                raise ValueError("Positive node labels and finite coordinates required")
            if label in coordinates and any(
                abs(a - b) > tolerance for a, b in zip(coordinates[label], xyz, strict=True)
            ):
                raise ValueError("Inconsistent coordinates for one node label")
            coordinates[label] = tuple(xyz)
            if (
                abs(xyz[0] - plane_x_mm) > tolerance
                or not ymin - tolerance <= xyz[1] <= ymax + tolerance
                or not zmin - tolerance <= xyz[2] <= zmax + tolerance
            ):
                raise ValueError("Selected node is outside the expected rectangular plane")
            ids.append(label)
        key = tuple(sorted(ids))
        if len(set(ids)) != len(ids) or key in faces:
            raise ValueError("Duplicate face or repeated face node")
        faces.add(key)
        cy = sum(coordinates[n][1] for n in ids) / len(ids)
        cz = sum(coordinates[n][2] for n in ids) / len(ids)
        ids.sort(key=lambda n: math.atan2(coordinates[n][2] - cz, coordinates[n][1] - cy))
        turns = []
        for k in range(len(ids)):
            a, b, c = [coordinates[ids[(k + j) % len(ids)]] for j in range(3)]
            turns.append((b[1] - a[1]) * (c[2] - b[2]) - (b[2] - a[2]) * (c[1] - b[1]))
        if any(turn <= 0 for turn in turns):
            raise ValueError("Degenerate or non-convex face")
        for a, b in zip(ids, ids[1:] + ids[:1], strict=True):
            pa, pb = coordinates[a], coordinates[b]
            area += (pa[1] * pb[2] - pb[1] * pa[2]) / 2
            edges[tuple(sorted((a, b)))].append((index, a, b))
    adjacent = defaultdict(set)
    exterior = []
    for edge, occurrences in edges.items():
        if len(occurrences) == 2:
            left, right = occurrences
            if left[1:] != right[1:][::-1]:
                raise ValueError("Adjacent face orientations overlap")
            adjacent[left[0]].add(right[0])
            adjacent[right[0]].add(left[0])
        elif len(occurrences) == 1:
            a, b = [coordinates[n] for n in edge]
            if not any(
                abs(a[axis] - value) <= tolerance and abs(b[axis] - value) <= tolerance
                for axis, value in ((1, ymin), (1, ymax), (2, zmin), (2, zmax))
            ):
                raise ValueError("Interior free edge: incomplete or nonconforming patch")
            exterior.append(math.dist(a, b))
        else:
            raise ValueError("Nonmanifold patch edge")
    visited, queue = {0}, [0]
    while queue:
        node = queue.pop()
        for other in adjacent[node] - visited:
            visited.add(other)
            queue.append(other)
    expected_area = (ymax - ymin) * (zmax - zmin)
    expected_perimeter = 2 * (ymax - ymin + zmax - zmin)
    if (
        len(visited) != len(polygons)
        or not math.isclose(area, expected_area, rel_tol=1e-6, abs_tol=1e-8)
        or not math.isclose(sum(exterior), expected_perimeter, rel_tol=1e-6, abs_tol=1e-8)
    ):
        raise ValueError(
            "Patch connectivity, area or perimeter differs from the expected rectangle"
        )
    return {
        "state": "rectangular_patch_verified",
        "face_count": len(polygons),
        "node_count": len(coordinates),
        "area_mm2": area,
        "expected_area_mm2": expected_area,
        "perimeter_mm": sum(exterior),
        "plane_x_mm": plane_x_mm,
        "minimum_yz_mm": list(minimum_yz_mm),
        "maximum_yz_mm": list(maximum_yz_mm),
        "coordinate_tolerance_mm": tolerance,
        "area_perimeter_relative_tolerance": 1e-6,
        "connected_components": 1,
        "interior_free_edges": 0,
        "scope": "Linear rectangular surface patch; not volume validity",
    }
