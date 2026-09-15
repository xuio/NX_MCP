"""Selected native tetra repair with exact boundary and rollback guards."""

import hashlib
import itertools
import json
import math

from nx_mcp.runtime import NXToolError


def boundary_digest(element_rows, coordinates):
    """Per-mesh exposed triangles, including interfaces between separate meshes."""
    faces = {}
    cells = set()
    for mesh, labels in element_rows:
        labels = tuple(sorted(labels))
        if len(labels) != 4 or len(set(labels)) != 4:
            raise ValueError("Requires nondegenerate four-node tetra connectivity")
        cell = (mesh, labels)
        if cell in cells:
            raise ValueError("Duplicate tetrahedron connectivity")
        cells.add(cell)
        for face in itertools.combinations(labels, 3):
            key = (mesh, face)
            faces[key] = faces.get(key, 0) + 1
            if faces[key] > 2:
                raise ValueError("Nonmanifold tetra face")
    boundary = sorted(key for key, count in faces.items() if count == 1)
    if not boundary:
        raise ValueError("No exposed tetra boundary")
    hasher = hashlib.sha256()
    node_labels = sorted({n for _, face in boundary for n in face})
    for label in node_labels:
        xyz = coordinates(label)
        if len(xyz) != 3 or not all(math.isfinite(v) for v in xyz):
            raise ValueError("Nonfinite boundary coordinates")
        hasher.update(json.dumps([label, [float(v if v else 0).hex() for v in xyz]]).encode())
        hasher.update(b"\n")
    for row in boundary:
        hasher.update(json.dumps(row).encode())
        hasher.update(b"\n")
    return {"sha256": hasher.hexdigest(), "triangles": len(boundary),
            "nodes": len(node_labels), "scope": "exact_per_mesh_boundary_labels_triangles_coordinates"}


def capture_boundary(fem, maximum_entities):
    from nx_mcp.simcenter.mesh_plan import mesh_counts

    counts = mesh_counts(fem)
    if sum(counts.values()) > maximum_entities:
        raise ValueError("Mesh exceeds inspection budget")
    elements = nodes = None
    try:
        elements = fem.BaseFEModel.FeelementLabelMap
        nodes = fem.BaseFEModel.FenodeLabelMap

        def rows():
            label = 0
            for _ in range(counts["elements"]):
                label = elements.AskNextElementLabel(label)
                element = elements.GetElement(label)
                yield element.Mesh.JournalIdentifier, [int(n.Label) for n in element.GetNodes()]

        def xyz(label):
            p = nodes.GetNode(label).Coordinates
            return [p.X, p.Y, p.Z]

        result = boundary_digest(rows(), xyz)
        if mesh_counts(fem) != counts:
            raise ValueError("Mesh changed during boundary inspection")
        return result
    finally:
        try:
            if nodes is not None:
                nodes.Dispose()
        finally:
            if elements is not None:
                elements.Dispose()


def validate_improvement(before, after):
    if before["settings"] != after["settings"]:
        raise ValueError("Quality criteria changed")
    a = {v["type"]: v for v in before["tests"]}
    b = {v["type"]: v for v in after["tests"]}
    if a.keys() != b.keys() or after["element_count"] <= 0:
        raise ValueError("Quality check scope changed")
    for name in a:
        if b[name]["errors"] > a[name]["errors"] or b[name]["warnings"] > a[name]["warnings"]:
            raise ValueError("A native quality test worsened")
    if b["AspectRatio"]["errors"] >= a["AspectRatio"]["errors"]:
        raise ValueError("Aspect-ratio errors did not decrease")
    for name in ("JacobianSign", "JacobianZero", "Volume"):
        if b[name]["errors"]:
            raise ValueError("Invalid tetrahedra remain")


def repair(executor, fem, labels, maximum_entities):
    import NXOpen.CAE as cae
    from NXOpen.CAE import ModelCheck as mc

    from nx_mcp.simcenter.mesh_state import capture
    from nx_mcp.simcenter.quality import check_mesh_quality, inspect_elements
    from nx_mcp.simcenter.remesh import settings
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    if type(maximum_entities) is not int or not 1 <= maximum_entities <= 2000000:
        raise NXToolError("NX_INVALID_ARGUMENT", "Inspection budget must be in 1..2000000")
    if not isinstance(fem, cae.FemPart) or executor.session.Parts.BaseWork != fem:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate a standalone FEM")
    if fem.PartUnits != executor.nxopen.BasePart.Units.Millimeters:
        raise NXToolError("NX_SIM_UNITS", "Repair requires a millimeter FEM")
    require_solver_idle()
    selected = inspect_elements(fem, labels)
    manager = fem.BaseFEModel.MeshManager
    meshes = list(manager.GetMeshes())
    original_settings = [settings(manager, m) for m in meshes]
    tags = [int(m.Tag) for m in meshes]
    original = capture(fem, maximum_entities=maximum_entities)
    boundary = capture_boundary(fem, maximum_entities)
    before = check_mesh_quality(fem, meshes)
    affected = [fem] + [p for p in executor.session.Parts
                       if isinstance(p, cae.SimPart) and p.FemPart == fem]
    part_ids = [executor._part_id(p) for p in affected]
    session = executor.session
    mark = session.SetUndoMark(executor.nxopen.Session.MarkVisibility.Visible, "NX MCP selected tetra repair")
    try:
        label_map = fem.BaseFEModel.FeelementLabelMap
        builder = result = None
        try:
            targets = [label_map.GetElement(n) for n in labels]
            builder = fem.ModelCheckMgr.CreateElementQualityCheckBuilder()
            builder.SelectionList.Add(meshes)
            result = builder.ExecuteCheck()
            builder.AttemptFixFailingSelectedElements([mc.TestValueTypes.TestType.AspectRatio], targets)
        finally:
            try:
                if result is not None:
                    result.Dispose()
            finally:
                try:
                    if builder is not None:
                        builder.Destroy()
                finally:
                    label_map.Dispose()
        current = list(manager.GetMeshes())
        if [int(m.Tag) for m in current] != tags or [settings(manager, m) for m in current] != original_settings:
            raise ValueError("Mesh identity, sizing or body association changed")
        after_boundary = capture_boundary(fem, maximum_entities)
        if boundary != after_boundary:
            raise ValueError("A mesh boundary or fan interface changed")
        after = check_mesh_quality(fem, current)
        validate_improvement(before, after)
        return {"before": before, "after": after, "boundary": boundary,
                "selected_labels": labels, "selected_count": selected["count"],
                "repair_attempted": True, "saved": False, "results_stale": True,
                "solver_launched": False, "solve_readiness": "not_established",
                "limitations": ["Boundary equality does not prove global connectivity or solver convergence.",
                                 "Remaining native quality errors still require review."]}
    except Exception as error:
        outcome = "rolled_back"
        try:
            session.UndoToMark(mark, None)
            session.DeleteUndoMark(mark, None)
            if capture(fem, maximum_entities=maximum_entities) != original:
                raise ValueError("Exact mesh rollback differs")
            if check_mesh_quality(fem, list(manager.GetMeshes())) != before:
                raise ValueError("Quality rollback differs")
        except Exception:
            outcome = "partial"
        raise NXToolError("NX_SIM_MESH_REPAIR_FAILED", str(error),
                          details={"mutation_outcome": outcome,
                                   "next_step": "Reacquire references and inspect native state; do not replay blindly"}) from error
    finally:
        for part_id in part_ids:
            executor.objects.invalidate_part(part_id)
