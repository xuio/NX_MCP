"""Regenerate existing supported tetra meshes; no geometry edits or solver launch."""

import math

from nx_mcp.runtime import NXToolError


def settings(manager, mesh):
    from nx_mcp.simcenter.mesh_plan import ELEMENTS

    builder = manager.CreateMesh3dTetBuilder(mesh)
    try:
        size, unit = builder.PropertyTable.GetBaseScalarWithDataPropertyValue(
            "quad mesh overall edge size"
        )
        element = builder.ElementType.ElementTypeName
        if (
            element not in ELEMENTS.values()
            or builder.AutoSizeOption
            or unit.Name != "MilliMeter"
            or not math.isfinite(size)
            or size <= 0
        ):
            raise ValueError(
                "Requires explicitly sized linear solid/fluid tetra meshes in millimeters"
            )
        targets = sorted(int(b.Tag) for b in builder.SelectionList.GetArray())
        if not targets:
            raise ValueError("Existing tetra mesh has no body selection")
        return {"element_type": element, "size_mm": size, "body_tags": targets}
    finally:
        builder.Destroy()


def regenerate(executor, fem):
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.mesh_plan import mesh_counts
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    nx, session = executor.nxopen, executor.session
    if not isinstance(fem, cae.FemPart) or session.Parts.BaseWork != fem:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate a standalone FEM")
    if fem.PartUnits != nx.BasePart.Units.Millimeters:
        raise NXToolError("NX_SIM_UNITS", "Remeshing requires a millimeter FEM")
    require_solver_idle()
    manager = fem.BaseFEModel.MeshManager
    meshes = list(manager.GetMeshes())
    if not meshes:
        raise NXToolError("NX_SIM_MESH_PRECONDITION", "Requires existing tetra meshes")
    try:
        before_settings = [settings(manager, mesh) for mesh in meshes]
    except Exception as error:
        raise NXToolError(
            "NX_SIM_MESH_UNSUPPORTED",
            str(error),
            nx_code=getattr(error, "ErrorCode", None),
            details={
                "mutation_outcome": "not_started",
                "next_step": "Inspect mesh types; layered/other mesh types require separate verification",
            },
        ) from error
    before = mesh_counts(fem)
    before_tags = [int(m.Tag) for m in meshes]
    # Invalidate dependent occurrence and selection handles even on rollback: native
    # remeshing can retire mesh entities while restoring equivalent geometry.
    affected = [fem] + [
        part for part in session.Parts if isinstance(part, cae.SimPart) and part.FemPart == fem
    ]
    part_ids = [executor._part_id(part) for part in affected]
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP regenerate tetra meshes")
    try:
        for mesh, expected in zip(meshes, before_settings, strict=True):
            builder = manager.CreateMesh3dTetBuilder(mesh)
            try:
                committed = list(builder.CommitMesh())
            finally:
                builder.Destroy()
            if len(committed) != 1 or int(committed[0].Tag) != int(mesh.Tag):
                raise ValueError("Remeshing changed mesh identity/cardinality")
            if settings(manager, mesh) != expected:
                raise ValueError("Remeshing changed element type, size or body selection")
        after = mesh_counts(fem)
        if [int(m.Tag) for m in manager.GetMeshes()] != before_tags:
            raise ValueError("Remeshing changed mesh inventory")
        return {
            "before_counts": before,
            "counts": after,
            "mesh_count": len(meshes),
            "settings": before_settings,
            "units": "mm",
            "coordinate_frame": "fem_part_absolute",
            "saved": False,
            "solver_launched": False,
            "results_stale": True,
            "references_invalidated": [p.FullPath for p in affected],
            "quality_validation": "not_performed",
            "convergence": "not_established",
            "next_step": "Reacquire document/face/mesh references, inspect quality and update associated SIM before solving",
        }
    except Exception as error:
        outcome = "rolled_back"
        try:
            session.UndoToMark(mark, None)
            session.DeleteUndoMark(mark, None)
            restored = list(manager.GetMeshes())
            if (
                [int(m.Tag) for m in restored] != before_tags
                or mesh_counts(fem) != before
                or [settings(manager, m) for m in restored] != before_settings
            ):
                raise ValueError("Mesh inventory, counts or settings differ after rollback")
        except Exception:
            outcome = "partial"
        raise NXToolError(
            "NX_SIM_REMESH_FAILED",
            str(error),
            nx_code=getattr(error, "ErrorCode", None),
            details={
                "mutation_outcome": outcome,
                "references_invalidated": [p.FullPath for p in affected],
                "next_step": "Reacquire references and inspect mesh inventory/settings before retrying",
            },
        ) from error
    finally:
        for part_id in part_ids:
            executor.objects.invalidate_part(part_id)
