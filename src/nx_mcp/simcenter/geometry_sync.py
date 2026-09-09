"""Synchronize an all-body CAD association through the NX 2606 native API."""

from nx_mcp.runtime import NXToolError


def synchronize(executor, fem):
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.mesh_plan import mesh_counts
    from nx_mcp.simcenter.remesh import settings
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    nx, session = executor.nxopen, executor.session
    if not isinstance(fem, cae.FemPart) or session.Parts.BaseWork != fem:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the standalone FEM")
    if fem.PartUnits != nx.BasePart.Units.Millimeters or fem.MasterCadPart is None:
        raise NXToolError("NX_SIM_PRECONDITION", "Requires millimeter FEM with loaded master CAD")
    require_solver_idle()
    cad = fem.MasterCadPart
    manager = fem.BaseFEModel.MeshManager

    def snapshot():
        meshes = list(manager.GetMeshes())
        return {
            "body_tags": sorted(int(b.Tag) for b in fem.Bodies),
            "mesh_tags": [int(m.Tag) for m in meshes],
            "mesh_settings": [settings(manager, mesh) for mesh in meshes],
            "counts": mesh_counts(fem) if meshes else {"nodes": 0, "elements": 0},
        }

    data = fem.GetGeometryDataWithAttributes()
    try:
        if data[0] != cae.FemPart.UseBodiesOption.AllBodies:
            raise NXToolError(
                "NX_SIM_UNSUPPORTED", "Only existing all-body CAD associations are supported"
            )
        before = snapshot()
        cad_tags = sorted(int(b.Tag) for b in cad.Bodies)
        if not cad_tags:
            raise NXToolError("NX_SIM_PRECONDITION", "Master CAD must contain bodies")
        affected = [fem] + [
            p for p in session.Parts if isinstance(p, cae.SimPart) and p.FemPart == fem
        ]
        part_ids = [executor._part_id(p) for p in affected]
        mark = session.SetUndoMark(
            nx.Session.MarkVisibility.Visible, "NX MCP synchronize FEM geometry"
        )
        try:
            fem.SetGeometryDataWithAttributes(data[0], [], data[2], data[3])
            fem.BaseFEModel.UpdateFemodel()
            after = snapshot()
            if fem.MasterCadPart != cad or sorted(int(b.Tag) for b in cad.Bodies) != cad_tags:
                raise ValueError("Master CAD association or source body inventory changed")
            if len(after["body_tags"]) != len(cad_tags):
                raise ValueError("FEM body count differs from master CAD after update")
            covered = {tag for row in after["mesh_settings"] for tag in row["body_tags"]}
            unmeshed = sorted(set(after["body_tags"]) - covered)
            from nx_mcp.simcenter.postviews import present_result

            return {
                "before_body_count": len(before["body_tags"]),
                "body_count": len(after["body_tags"]),
                "cad_body_count": len(cad_tags),
                "before_counts": before["counts"],
                "counts": after["counts"],
                "mesh_count": len(after["mesh_tags"]),
                "unmeshed_body_tags": unmeshed,
                "mesh_coverage_complete": not unmeshed,
                "saved": False,
                "solver_launched": False,
                "results_stale": True,
                "references_invalidated": [p.FullPath for p in affected],
                "units": "mm",
                "coordinate_frame": "fem_part_absolute",
                "presentation": present_result(session, fem),
                "next_step": "Reacquire references, inspect selections and mesh coverage; update dependent SIM and re-export before solving",
            }
        except Exception as error:
            outcome = "rolled_back"
            try:
                session.UndoToMark(mark, None)
                session.DeleteUndoMark(mark, None)
                if snapshot() != before:
                    raise ValueError("Rollback inventory/settings/counts differ")
            except Exception:
                outcome = "partial"
            raise NXToolError(
                "NX_SIM_GEOMETRY_SYNC_FAILED",
                str(error),
                nx_code=getattr(error, "ErrorCode", None),
                details={
                    "mutation_outcome": outcome,
                    "references_invalidated": [p.FullPath for p in affected],
                    "rollback_verification": "body/mesh identities, mesh settings and counts only",
                },
            ) from error
        finally:
            for part_id in part_ids:
                executor.objects.invalidate_part(part_id)
    finally:
        data[2].Dispose()
