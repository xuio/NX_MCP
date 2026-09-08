"""Native failure/freshness test on the isolated fan-definition SIM; rolled back."""


def run(executor):
    import importlib
    import json
    from pathlib import Path

    import NXOpen as nx

    from nx_mcp.simcenter import fan_field
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    importlib.reload(importlib.import_module("nx_mcp.simcenter.properties"))
    state = importlib.reload(importlib.import_module("nx_mcp.simcenter.boundary_state"))
    context = json.loads(
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\fan-definition-readback.json").read_text()
    )
    sim = executor.objects.resolve(context["matches"][0]["document"], expected_kind="part")
    assert executor.session.Parts.BaseWork == sim
    inlet = next(b for b in sim.Simulation.SimulationObjects if b.DescriptorName == "Inlet")
    wrapper = inlet.PropertyTable.GetScalarFieldWrapperPropertyValue("Fan Curve")
    field = wrapper.GetField()
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    before = state.capture_boundary_state(sim, nx)
    mark = executor.session.SetUndoMark(nx.Session.MarkVisibility.Visible, "Fan definition audit")
    try:
        wrapper.SetField(field, 2.0)
        scaled = state.capture_boundary_state(sim, nx)
        # Only claim whole-boundary hash sensitivity if this fixture is complete.
        if before["comparison_verified"]:
            assert scaled["comparison_verified"] and before["sha256"] != scaled["sha256"]
        field.SetUserAttribute(
            fan_field._HEADER_ATTRIBUTE, -1, "invalid audit header", nx.Update.Option.Now
        )
        failed = state.capture_boundary_state(sim, nx)
        assert not failed["comparison_verified"] and failed["sha256"] is None
        rejected = next(
            p for b in failed["boundaries"] for p in b["properties"] if p["name"] == "Fan Curve"
        )
        assert rejected["inspection_error"]["code"] == "NX_SIM_MANIFEST_INVALID"
        assert any(
            r.get("property") == "Fan Curve" and r["reason"] == "read_failed"
            for r in failed["errors"]
        )
    finally:
        executor.session.UndoToMark(mark, None)
        executor.session.DeleteUndoMark(mark, None)
    restored = state.capture_boundary_state(sim, nx)
    assert restored == before
    assert flags == {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    result = {
        "passed": True,
        "before": before,
        "scaled": scaled,
        "invalid_definition": failed,
        "restored_exactly": True,
        "modified_flags_preserved": True,
        "solver_launched": False,
    }
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\fan-definition-freshness.json").write_text(
        json.dumps(result, indent=2)
    )
    return result
