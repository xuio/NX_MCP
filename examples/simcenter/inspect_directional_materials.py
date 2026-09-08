"""Inspect documented directional material builders on an isolated FEM."""


def run(executor):
    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    session, nx = executor.session, executor.nxopen
    old_work, old_display = session.Parts.BaseWork, session.Parts.BaseDisplay
    fem = next(p for p in session.Parts if p.FullPath.endswith("VariantTxnR1_mesh.fem"))
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    materials = fem.MaterialManager.PhysicalMaterials
    before = [int(m.Tag) for m in materials]
    rows = []
    try:
        _, status = session.Parts.SetDisplay(fem, False, False)
        if status:
            status.Dispose()
        session.Parts.SetWork(fem)
        for kind in ("Orthotropic", "Anisotropic"):
            mark = session.SetUndoMark(
                nx.Session.MarkVisibility.Visible, "Inspect directional material"
            )
            builder = None
            try:
                builder = materials.CreatePhysicalMaterialBuilder(
                    getattr(nx.PhysicalMaterial.Type, kind)
                )
                properties = read_properties(builder.PropertyTable, nx)
                rows.append(
                    {
                        "type": kind,
                        "accepted": True,
                        "thermal_properties": [
                            r
                            for r in properties
                            if any(
                                k in r["name"].lower()
                                for k in ("thermal", "conduct", "density", "specificheat")
                            )
                        ],
                        "committed": False,
                    }
                )
            except Exception as error:
                rows.append(
                    {
                        "type": kind,
                        "accepted": False,
                        "error": str(error),
                        "nx_code": getattr(error, "ErrorCode", None),
                    }
                )
            finally:
                if builder:
                    builder.Destroy()
                session.UndoToMark(mark, None)
                session.DeleteUndoMark(mark, None)
            assert before == [int(m.Tag) for m in materials]
        assert flags == {p.FullPath: bool(p.IsModified) for p in session.Parts}
        return {"builders": rows, "materials_unchanged": True, "flags_preserved": True}
    finally:
        _, status = session.Parts.SetDisplay(old_display, False, False)
        if status:
            status.Dispose()
        session.Parts.SetWork(old_work)
