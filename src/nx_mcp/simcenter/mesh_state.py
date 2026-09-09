"""Exact labelled mesh state; deliberately excludes CAD, physics and solver settings."""

import hashlib
import json
import math
import re

from nx_mcp.runtime import NXToolError

SCOPE = "node_labels_coordinates_and_ordered_element_connectivity_shape_mesh_collector"


def digest(nodes, elements, *, units, owner_path):
    """Stream canonical ordered records; reject incomplete or ambiguous topology."""
    hasher = hashlib.sha256()

    def emit(row):
        hasher.update(json.dumps(row, separators=(",", ":"), allow_nan=False).encode())
        hasher.update(b"\n")

    emit([1, SCOPE, units, "fem_part_absolute"])
    labels = set()
    previous = 0
    node_count = element_count = 0
    for label, xyz in nodes:
        if type(label) is not int or label <= previous or len(xyz) != 3:
            raise ValueError("Node labels must be strictly increasing positive integers with xyz")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in xyz):
            raise ValueError("Node coordinates must be finite")
        emit(["node", label, [float(v if v else 0).hex() for v in xyz]])
        labels.add(label)
        previous = label
        node_count += 1
    previous = 0
    for label, shape, mesh, collector, connectivity in elements:
        if type(label) is not int or label <= previous:
            raise ValueError("Element labels must be strictly increasing positive integers")
        if any(not isinstance(v, str) or not v for v in (shape, mesh, collector)):
            raise ValueError("Element shape, mesh and collector identity are required")
        if not connectivity or any(type(n) is not int or n not in labels for n in connectivity):
            raise ValueError("Element connectivity refers to an unknown node")
        emit(["element", label, shape, mesh, collector, connectivity])
        previous = label
        element_count += 1
    return {
        "adapter": 1,
        "scope": SCOPE,
        "owner_path": owner_path,
        "units": units,
        "coordinate_frame": "fem_part_absolute",
        "counts": {"nodes": node_count, "elements": element_count},
        "sha256": hasher.hexdigest(),
        "coordinate_encoding": "exact float64 hex; signed zero normalized",
        "full_model_freshness": "not_verified",
        "excluded": [
            "CAD geometry",
            "mesh controls",
            "material assignments/properties",
            "loads and boundary conditions",
            "solver element formulation",
            "solution settings",
            "external dependencies",
        ],
    }


def capture(fem, *, maximum_entities=200000):
    """Inspect a FEM prototype; dispose both label maps on every exit path."""
    if type(maximum_entities) is not int or not 1 <= maximum_entities <= 1000000:
        raise ValueError("maximum_entities must be an integer in 1..1000000")
    import NXOpen as nx

    if fem.PartUnits != nx.BasePart.Units.Millimeters:
        raise NXToolError("NX_SIM_UNITS", "Mesh state currently requires a millimeter FEM")
    nodes = elements = None
    try:
        nodes = fem.BaseFEModel.FenodeLabelMap
        elements = fem.BaseFEModel.FeelementLabelMap
        expected = {"nodes": nodes.NumNodes, "elements": elements.NumElements}
        if min(expected.values()) < 0 or sum(expected.values()) > maximum_entities:
            raise NXToolError(
                "NX_SIM_INSPECTION_LIMIT",
                "Mesh exceeds the requested entity inspection budget",
                details={"counts": expected, "maximum_entities": maximum_entities},
            )

        def node_rows():
            label = 0
            for _ in range(expected["nodes"]):
                label = nodes.AskNextNodeLabel(label)
                node = nodes.GetNode(label)
                point = node.Coordinates
                yield int(label), [point.X, point.Y, point.Z]

        def element_rows():
            label = 0
            for _ in range(expected["elements"]):
                label = elements.AskNextElementLabel(label)
                element = elements.GetElement(label)
                mesh = element.Mesh
                yield (
                    int(label),
                    str(element.Shape),
                    mesh.JournalIdentifier,
                    mesh.MeshCollector.JournalIdentifier,
                    [int(n.Label) for n in element.GetNodes()],
                )

        result = digest(node_rows(), element_rows(), units="mm", owner_path=fem.FullPath)
        if result["counts"] != expected or expected != {
            "nodes": nodes.NumNodes,
            "elements": elements.NumElements,
        }:
            raise ValueError("Mesh counts changed during inspection")
        return result
    finally:
        try:
            if elements is not None:
                elements.Dispose()
        finally:
            if nodes is not None:
                nodes.Dispose()


def compare(expected, actual):
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        return {"state": "not_verified", "reason": "mesh_state_missing"}
    for value in (expected, actual):
        if (
            value.get("adapter") != 1
            or value.get("scope") != SCOPE
            or not re.fullmatch(r"[0-9a-f]{64}", str(value.get("sha256", "")))
            or not isinstance(value.get("owner_path"), str)
            or not value["owner_path"]
            or value.get("units") != "mm"
            or value.get("coordinate_frame") != "fem_part_absolute"
            or not isinstance(value.get("counts"), dict)
            or set(value["counts"]) != {"nodes", "elements"}
            or any(type(n) is not int or n < 0 for n in value["counts"].values())
        ):
            return {"state": "not_verified", "reason": "unsupported_or_incomplete_mesh_state"}
    if any(expected.get(k) != actual.get(k) for k in ("owner_path", "units", "coordinate_frame")):
        return {"state": "not_verified", "reason": "mesh_context_differs"}
    if expected["sha256"] == actual["sha256"] and expected["counts"] != actual["counts"]:
        return {"state": "not_verified", "reason": "mesh_counts_digest_conflict"}
    return {
        "state": "matches" if expected["sha256"] == actual["sha256"] else "changed",
        "scope": SCOPE,
        "full_model_freshness": "not_verified",
    }
