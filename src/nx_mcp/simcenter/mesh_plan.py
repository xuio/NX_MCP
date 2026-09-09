"""Explicit solid/fluid meshing plans; native meshing only, no material inference."""

import math

from nx_mcp.runtime import NXToolError

ELEMENTS = {"solid": "Linear Tetrahedron", "fluid": "Fluid Linear Tetrahedron"}


def validate(regions):
    if not isinstance(regions, list) or not 1 <= len(regions) <= 16:
        raise ValueError("Supply 1..16 body mesh definitions")
    seen = set()
    for row in regions:
        if not isinstance(row, dict) or set(row) != {"body", "kind", "size_mm"}:
            raise ValueError("Each region requires exactly body, kind and size_mm")
        if not isinstance(row["body"], str) or not row["body"] or row["body"] in seen:
            raise ValueError("Body references must be distinct nonempty IDs")
        seen.add(row["body"])
        if not isinstance(row["kind"], str) or row["kind"] not in ELEMENTS:
            raise ValueError("kind must be solid or fluid")
        size = row["size_mm"]
        if type(size) not in (int, float) or not math.isfinite(size) or not 0 < size <= 10000:
            raise ValueError("size_mm must be finite and in (0,10000]")


def mesh_counts(fem):
    elements = nodes = None
    try:
        elements = fem.BaseFEModel.FeelementLabelMap
        nodes = fem.BaseFEModel.FenodeLabelMap
        counts = {"elements": elements.NumElements, "nodes": nodes.NumNodes}
        if counts["elements"] <= 0 or counts["nodes"] <= 0:
            raise ValueError("Native mesh has no elements or nodes")
        return counts
    finally:
        try:
            if nodes is not None:
                nodes.Dispose()
        finally:
            if elements is not None:
                elements.Dispose()


def generate(executor, fem, regions):
    validate(regions)
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    nx, session = executor.nxopen, executor.session
    if not isinstance(fem, cae.FemPart) or session.Parts.BaseWork != fem:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the standalone FEM")
    if fem.PartUnits != nx.BasePart.Units.Millimeters:
        raise NXToolError("NX_SIM_UNITS", "Mesh plans require a millimeter FEM")
    bodies = [executor.objects.resolve(r["body"], expected_kind="body") for r in regions]
    if (
        any(b.OwningPart != fem for b in bodies)
        or {int(b.Tag) for b in bodies} != {int(b.Tag) for b in fem.Bodies}
        or len({int(b.Tag) for b in bodies}) != len(bodies)
    ):
        raise NXToolError(
            "NX_SIM_SELECTION_OWNER", "Plan must cover every FEM-owned body exactly once"
        )
    manager = fem.BaseFEModel.MeshManager
    if manager.GetMeshes():
        raise NXToolError(
            "NX_SIM_MESH_PRECONDITION", "Existing meshes require a separate remesh workflow"
        )
    require_solver_idle()
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP body mesh plan")
    rows = []
    try:
        for region, body in zip(regions, bodies, strict=True):
            builder = manager.CreateMesh3dTetBuilder(None)
            try:
                element = ELEMENTS[region["kind"]]
                if element not in builder.ElementType.GetElementTypeNames():
                    raise ValueError("Installed solution does not offer " + element)
                builder.ElementType.ElementTypeName = element
                builder.ElementType.DestinationCollector.AutomaticMode = True
                builder.AutoSizeOption = False
                builder.PropertyTable.SetBaseScalarWithDataPropertyValue(
                    "quad mesh overall edge size",
                    float(region["size_mm"]),
                    fem.UnitCollection.FindObject("MilliMeter"),
                )
                builder.SelectionList.Add([body])
                meshes = list(builder.CommitMesh())
                if not meshes:
                    raise ValueError("Native mesher produced no mesh for " + region["body"])
            finally:
                builder.Destroy()
            # Reopen the primary tet mesh, rather than assuming its inputs persisted.
            reader = manager.CreateMesh3dTetBuilder(meshes[0])
            try:
                size, unit = reader.PropertyTable.GetBaseScalarWithDataPropertyValue(
                    "quad mesh overall edge size"
                )
                targets = {int(b.Tag) for b in reader.SelectionList.GetArray()}
                if (
                    reader.ElementType.ElementTypeName != element
                    or reader.AutoSizeOption
                    or unit.Name != "MilliMeter"
                    or not math.isclose(size, region["size_mm"], rel_tol=1e-12)
                    or targets != {int(body.Tag)}
                ):
                    raise ValueError("Committed element type, size or body selection differs")
                rows.append(
                    {
                        "body": executor._reference(body, "body", fem, "body"),
                        "kind": region["kind"],
                        "size_mm": size,
                        "element_type": reader.ElementType.ElementTypeName,
                        "meshes": [
                            executor._reference(m, "simulation_mesh", fem, "mesh") for m in meshes
                        ],
                    }
                )
            finally:
                reader.Destroy()
        counts = mesh_counts(fem)
        return {
            "regions": rows,
            "counts": counts,
            "mesh_count": len(manager.GetMeshes()),
            "units": "mm",
            "coordinate_frame": "fem_part_absolute",
            "saved": False,
            "results_stale": True,
            "material_assignments": "not_created",
            "quality_validation": "not_performed",
            "boundary_layer_effect": "inspect generated topology and quality; not inferred from control presence",
        }
    except Exception as error:
        outcome = "rolled_back"
        try:
            session.UndoToMark(mark, None)
            session.DeleteUndoMark(mark, None)
            if manager.GetMeshes():
                raise ValueError("Meshes remain after rollback")
        except Exception:
            outcome = "partial"
        raise NXToolError(
            "NX_SIM_MESH_PLAN_FAILED",
            str(error),
            nx_code=getattr(error, "ErrorCode", None),
            details={
                "mutation_outcome": outcome,
                "next_step": "Inspect the FEM mesh inventory before retrying",
            },
        ) from error
