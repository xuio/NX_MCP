"""Audit the isolated rectangular-duct tetrahedra exported by verify_fluid_mesh_quality."""

import argparse
import hashlib
import itertools
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


def audit(data):
    if data["units"] != "mm" or data["frame"] != "FEM_absolute":
        raise ValueError("Requires millimeter FEM coordinates")
    elements = data["elements"]
    if not 0 < len(elements) <= 10000:
        raise ValueError("Fixture element budget exceeded")
    nodes, faces, volumes = {}, defaultdict(list), []
    parent = list(range(len(elements)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, element in enumerate(elements):
        ns = element["nodes"]
        if len(ns) != 4 or len({n["label"] for n in ns}) != 4:
            raise ValueError("Requires four distinct nodes per linear tetrahedron")
        for n in ns:
            xyz = n["xyz"]
            if len(xyz) != 3 or not all(math.isfinite(v) for v in xyz):
                raise ValueError("Invalid node coordinates")
            if n["label"] in nodes and nodes[n["label"]] != xyz:
                raise ValueError("Conflicting coordinates for a node label")
            nodes[n["label"]] = xyz
        a, b, c, d = [n["xyz"] for n in ns]
        u, v, w = [[p[j] - a[j] for j in range(3)] for p in [b, c, d]]
        determinant = (
            u[0] * (v[1] * w[2] - v[2] * w[1])
            - u[1] * (v[0] * w[2] - v[2] * w[0])
            + u[2] * (v[0] * w[1] - v[1] * w[0])
        )
        volumes.append(abs(determinant) / 6)
        for face in itertools.combinations(sorted(n["label"] for n in ns), 3):
            faces[face].append(i)
    for owners in faces.values():
        for other in owners[1:]:
            parent[root(other)] = root(owners[0])
    boundary = [face for face, owners in faces.items() if len(owners) == 1]
    edges = Counter(edge for face in boundary for edge in itertools.combinations(face, 2))
    bounds = [min(p[j] for p in nodes.values()) for j in range(3)] + [
        max(p[j] for p in nodes.values()) for j in range(3)
    ]
    # Each boundary triangle must lie on one of the six analytic cavity planes.
    off_boundary = sum(
        not any(
            all(abs(nodes[n][axis] - limit) < 1e-7 for n in face)
            for axis, limits in enumerate([(1, 161), (1, 21), (1, 21)])
            for limit in limits
        )
        for face in boundary
    )
    result = {
        "elements": len(elements),
        "nodes": len(nodes),
        "face_connected_regions": len({root(i) for i in parent}),
        "nonmanifold_faces": sum(len(v) > 2 for v in faces.values()),
        "boundary_triangles": len(boundary),
        "nonmanifold_boundary_edges": sum(v != 2 for v in edges.values()),
        "boundary_triangles_off_expected_planes": off_boundary,
        "bounds_mm": bounds,
        "summed_tetra_volume_mm3": math.fsum(volumes),
        "minimum_tetra_volume_mm3": min(volumes),
        "degenerate_elements": sum(v <= 1e-12 for v in volumes),
    }
    result["volume_relative_error"] = abs(result["summed_tetra_volume_mm3"] - 64000) / 64000
    result["passed"] = (
        result["face_connected_regions"] == 1
        and result["nonmanifold_faces"] == 0
        and result["nonmanifold_boundary_edges"] == 0
        and off_boundary == 0
        and result["degenerate_elements"] == 0
        and result["volume_relative_error"] < 1e-8
        and all(abs(a - b) < 1e-7 for a, b in zip(bounds, [1, 1, 1, 161, 21, 21], strict=True))
    )
    result["scope"] = (
        "Rectangular cavity connectivity and geometric coverage checks; not a general intersection test or CFD convergence test"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    result = audit(json.loads(raw))
    result["input_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
