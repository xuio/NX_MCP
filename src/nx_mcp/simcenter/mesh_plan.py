"""Explicit solid/fluid meshing plans; native meshing only, no material inference."""

import math

from nx_mcp.runtime import NXToolError

ELEMENTS = {"solid": "Linear Tetrahedron", "fluid": "Fluid Linear Tetrahedron"}


def validate(regions):
    if not isinstance(regions, list) or not regions:
        raise ValueError("Supply a nonempty list of body mesh definitions")
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


def validate_processors(number_of_processors):
    if number_of_processors is not None and (
        type(number_of_processors) is not int or not 1 <= number_of_processors <= 32
    ):
        raise ValueError("number_of_processors must be an integer in 1..32 or omitted")


def configure_processors(table, number_of_processors):
    validate_processors(number_of_processors)
    if number_of_processors is not None:
        table.SetIntegerPropertyValue("number of processors", number_of_processors)
        if table.GetIntegerPropertyValue("number of processors") != number_of_processors:
            raise ValueError("Native mesher processor setting differs from the request")


def generate(executor, fem, regions, number_of_processors=None):
    validate(regions)
    validate_processors(number_of_processors)
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
        for index, (region, body) in enumerate(zip(regions, bodies, strict=True), 1):
            log = getattr(session, "LogFile", None)
            if log is not None:
                log.WriteLine(
                    f"NX MCP mesh plan region {index}/{len(regions)} START "
                    f"body_tag={int(body.Tag)} body_ref={region['body']} "
                    f"size_mm={region['size_mm']} processors={number_of_processors}"
                )
            builder = manager.CreateMesh3dTetBuilder(None)
            try:
                element = ELEMENTS[region["kind"]]
                if element not in builder.ElementType.GetElementTypeNames():
                    raise ValueError("Installed solution does not offer " + element)
                builder.ElementType.ElementTypeName = element
                builder.ElementType.DestinationCollector.AutomaticMode = True
                builder.AutoSizeOption = False
                configure_processors(builder.PropertyTable, number_of_processors)
                builder.PropertyTable.SetBaseScalarWithDataPropertyValue(
                    "quad mesh overall edge size",
                    float(region["size_mm"]),
                    fem.UnitCollection.FindObject("MilliMeter"),
                )
                builder.SelectionList.Add([body])
                meshes = list(builder.CommitMesh())
                if not meshes:
                    raise ValueError("Native mesher produced no mesh for " + region["body"])
                if log is not None:
                    log.WriteLine(f"NX MCP mesh plan region {index} COMMIT_RETURNED meshes={len(meshes)}")
            finally:
                builder.Destroy()
            # Reopen the primary tet mesh, rather than assuming its inputs persisted.
            reader = manager.CreateMesh3dTetBuilder(meshes[0])
            try:
                size, unit = reader.PropertyTable.GetBaseScalarWithDataPropertyValue(
                    "quad mesh overall edge size"
                )
                targets = {int(b.Tag) for b in reader.SelectionList.GetArray()}
                actual_processors = None
                if number_of_processors is not None:
                    actual_processors = reader.PropertyTable.GetIntegerPropertyValue(
                        "number of processors"
                    )
                    if actual_processors != number_of_processors:
                        raise ValueError("Committed mesher processor setting differs")
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
                        "number_of_processors": actual_processors,
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
            "requested_number_of_processors": number_of_processors,
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
