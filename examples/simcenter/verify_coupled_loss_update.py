"""Reversible coupled head-loss compare-and-set and rollback check; no save/solve."""


def run(executor):
    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter import head_loss
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    s, nx = executor.session, executor.nxopen
    sim = s.Parts.BaseWork
    assert sim.FullPath.endswith(r"E-coupled-fan-public-20260909-r1\coupled_fan_public_r1.sim")
    assert sim.Simulation.ActiveSolution.AnalysisType == "Coupled Thermal-Flow"
    flags = {p.FullPath: bool(p.IsModified) for p in s.Parts}
    (opening,) = [b for b in sim.Simulation.SimulationObjects if b.DescriptorName == "Opening"]
    table = opening.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss")
    old = table.PropertyTable.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient")
    assert old[0] == 2
    mark = s.SetUndoMark(nx.Session.MarkVisibility.Visible, "Verify coupled loss update")
    try:
        result = head_loss.set_opening_head_loss(s, sim, opening, 3, expected_coefficient=2)
        assert result["coefficient"] == 3 and result["analysis_type"] == "Coupled Thermal-Flow"
        real = head_loss.require_manual_dynamic_pressure
        calls = 0

        def injected(value):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise NXToolError("NX_SIM_READBACK_MISMATCH", "Injected post-write failure")
            return real(value)

        head_loss.require_manual_dynamic_pressure = injected
        try:
            try:
                head_loss.set_opening_head_loss(s, sim, opening, 4, expected_coefficient=3)
            except NXToolError as error:
                assert error.details["mutation_outcome"] == "rolled_back"
                assert table.PropertyTable.GetBaseScalarWithDataPropertyValue(
                    "Head Loss Coefficient"
                ) == (3, old[1])
            else:
                raise AssertionError("Injected failure did not fail")
        finally:
            head_loss.require_manual_dynamic_pressure = real
    finally:
        s.UndoToMark(mark, None)
        s.DeleteUndoMark(mark, None)
    assert table.PropertyTable.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient") == old
    assert {p.FullPath: bool(p.IsModified) for p in s.Parts} == flags
    return {
        "passed": True,
        "update": result,
        "post_write_failure_rolled_back": True,
        "outer_rollback_verified": True,
        "document_flags_preserved": True,
        "solver_launched": False,
    }
