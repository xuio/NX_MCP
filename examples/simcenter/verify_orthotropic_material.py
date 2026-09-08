"""Commit/read/rollback a synthetic directional material in an isolated FEM."""


def run(executor):
    from nx_mcp.simcenter.directional_material import create_orthotropic

    session = executor.session
    work, display = session.Parts.BaseWork, session.Parts.BaseDisplay
    fem = next(p for p in session.Parts if p.FullPath.endswith("VariantTxnR1_mesh.fem"))
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    tags = [int(m.Tag) for m in fem.MaterialManager.PhysicalMaterials]
    mark = None
    try:
        material, readback, mark = create_orthotropic(
            session,
            executor.nxopen,
            fem,
            conductivities=[12, 7, 0.4],
            density=1900,
            heat_capacity=900,
            name="MCP_DIRECTIONAL_NATIVE_PROBE",
            provenance="Synthetic orthotropic material readback benchmark; not approved PCB data",
        )
        assert int(material.Tag) not in tags
        assert len(list(fem.MaterialManager.PhysicalMaterials)) == len(tags) + 1
        return {
            "committed_readback": readback,
            "material_name": material.Name,
            "assigned": False,
            "saved": False,
            "rolled_back_after_readback": True,
        }
    finally:
        if mark is not None:
            session.UndoToMark(mark, None)
            session.DeleteUndoMark(mark, None)
        assert tags == [int(m.Tag) for m in fem.MaterialManager.PhysicalMaterials]
        _, status = session.Parts.SetDisplay(display, False, False)
        if status:
            status.Dispose()
        session.Parts.SetWork(work)
        assert flags == {p.FullPath: bool(p.IsModified) for p in session.Parts}
