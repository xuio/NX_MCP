"""Reopen the saved isolated K2 export fixture; no writes or solver launch."""


def run(executor):
    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.head_loss import require_manual_dynamic_pressure
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    path = sim.FullPath
    if (
        not path.endswith("F3-head-loss-export-20260909-r1\\f3_head_loss_export_r1.sim")
        or sim.IsModified
    ):
        raise ValueError("Requires the saved isolated K2 export fixture")

    def state(part):
        opening = next(b for b in part.Simulation.SimulationObjects if b.Name == "Duct Opening")
        table = opening.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss")
        coefficient, unit = table.PropertyTable.GetBaseScalarWithDataPropertyValue(
            "Head Loss Coefficient"
        )
        return opening, {
            "table": table.Name,
            "selectors": require_manual_dynamic_pressure(table),
            "coefficient": coefficient,
            "unit": unit.Name if unit else "dimensionless",
        }

    opening, before = state(sim)
    assert before["coefficient"] == 2
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts if p != sim}
    refs = [
        executor._reference(sim, "part", sim, "SIM")["id"],
        executor._reference(opening, "simulation_object", sim, "opening")["id"],
    ]
    executor._sim_close(refs[0])
    stale = []
    for ref in refs:
        try:
            executor.objects.resolve(ref)
        except NXToolError as error:
            assert error.code == "NX_OBJECT_STALE"
            stale.append(error.code)
        else:
            raise AssertionError("Closed reference resolves")
    executor._sim_open(path)
    reopened = executor.session.Parts.BaseWork
    _, after = state(reopened)
    assert before == after
    assert flags == {
        p.FullPath: bool(p.IsModified) for p in executor.session.Parts if p != reopened
    }
    return {
        "passed": True,
        "before": before,
        "after": after,
        "stale_errors": stale,
        "unrelated_modified_flags_preserved": True,
        "document_path": path,
        "solver_launched": False,
    }
