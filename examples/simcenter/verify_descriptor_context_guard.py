"""Verify documented UF descriptor prerequisite without calling UF from a FEM."""


def run(executor):
    import importlib

    import nx_mcp.simcenter.descriptors as descriptors
    from nx_mcp.runtime import NXToolError

    importlib.reload(descriptors)
    session = executor.session
    work, display = session.Parts.BaseWork, session.Parts.BaseDisplay
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    sim = next(p for p in session.Parts if p.FullPath.endswith("live_revision_solve_r1.sim"))
    fem = sim.FemPart
    rejected = []
    try:
        executor._sim_activate(executor._reference(fem, "part", fem, "FEM")["id"])
        for kind in ("load", "constraint", "solution_step"):
            try:
                descriptors.descriptor_inventory(sim, kind=kind)
            except NXToolError as error:
                assert error.code == "NX_SIM_DOCUMENT_NOT_ACTIVE"
                rejected.append(kind)
            else:
                raise AssertionError("FEM context accepted")
        executor._sim_activate(executor._reference(sim, "part", sim, "SIM")["id"])
        valid = descriptors.descriptor_inventory(sim, kind="constraint", limit=2)
        assert valid["total"] > 0
        return {
            "rejected_from_fem": rejected,
            "valid_sim_page": valid,
            "licensing_changed": False,
            "model_mutation": False,
        }
    finally:
        _, status = session.Parts.SetDisplay(display, False, False)
        if status:
            status.Dispose()
        session.Parts.SetWork(work)
        assert flags == {p.FullPath: bool(p.IsModified) for p in session.Parts}
