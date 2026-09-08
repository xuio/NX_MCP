"""Verify native derived fan-table samples, provenance and rollback."""


def run(executor):
    import importlib
    import types

    import nx_mcp.hardened as hardened
    import nx_mcp.simcenter.native as native
    import nx_mcp.simcenter.server as server
    from nx_mcp.simcenter.fan_field import inspect_fan_table

    importlib.reload(native)
    importlib.reload(server)
    for name in ("nx_sim_fan_table", "nx_sim_scale_fan_table"):
        method = types.MethodType(getattr(native.SimcenterMixin, "_" + name[3:]), executor)
        setattr(executor, "_" + name[3:], method)
        executor._handlers[name] = method
        hardened.NON_MODEL.add(name)
    session = executor.session
    sim = next(
        p for p in session.Parts if p.FullPath.endswith("benchmark_9c5a613280cc_analysis.sim")
    )
    source = next(f for f in sim.FieldManager.Fields if f.Name == "Retained synthetic fan")
    source_before = inspect_fan_table(sim, source)
    work, display = session.Parts.BaseWork, session.Parts.BaseDisplay
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    tags = [int(f.Tag) for f in sim.FieldManager.Fields]
    document = executor._reference(sim, "part", sim, "SIM")["id"]
    source_id = executor._reference(source, "simulation_field", sim, "field")["id"]
    mark = None
    try:
        executor._sim_activate(document)
        mark = session.SetUndoMark(
            executor.nxopen.Session.MarkVisibility.Visible, "Native fan scaling test"
        )
        result = executor._sim_scale_fan_table(document, source_id, "MCP_SCALED_FAN_PROBE", 1100)
        assert result["manifest"]["provenance"]["kind"] == "assumed"
        ratio = 1100 / source_before["manifest"]["rpm"]
        for expected, actual in zip(
            source_before["manifest"]["points"], result["manifest"]["points"], strict=True
        ):
            assert abs(actual["flow_m3_s"] - expected["flow_m3_s"] * ratio) < 1e-12
            assert abs(actual["pressure_Pa"] - expected["pressure_Pa"] * ratio**2) < 1e-12
        assert inspect_fan_table(sim, source) == source_before
        return {
            "scaled_table": result,
            "source_preserved": True,
            "rolled_back_after_readback": True,
        }
    finally:
        if mark is not None:
            session.UndoToMark(mark, None)
            session.DeleteUndoMark(mark, None)
        assert [int(f.Tag) for f in sim.FieldManager.Fields] == tags
        _, status = session.Parts.SetDisplay(display, False, False)
        if status:
            status.Dispose()
        session.Parts.SetWork(work)
        assert flags == {p.FullPath: bool(p.IsModified) for p in session.Parts}
