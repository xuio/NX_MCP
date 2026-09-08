"""Native linked External Conditions readback/change/undo on an isolated copy."""


def run(executor):
    import importlib
    import json
    from pathlib import Path

    import NXOpen as nx

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    importlib.reload(importlib.import_module("nx_mcp.simcenter.properties"))
    module = importlib.reload(importlib.import_module("nx_mcp.simcenter.boundary_state"))
    sim = executor.session.Parts.BaseWork
    if "F1-active-field-20260908-r1" not in sim.FullPath:
        raise ValueError("Expected isolated active-field fixture")
    root = executor.workspace.resolve("ui-benchmarks/F2-linked-state-20260908-r1")
    if root.exists():
        raise ValueError("Inspect existing linked-state test before replay")
    executor._sim_save_as(
        executor._reference(sim, "part", sim, "SIM")["id"], str(root / "linked_state.sim")
    )
    before = module.capture_boundary_state(sim, nx)

    def linked_temperatures(state):
        values = []
        for boundary in state["boundaries"]:
            if boundary["category"] != "simulation_objects":
                continue
            for prop in boundary["properties"]:
                if prop["name"] == "Inlet Conditions":
                    temp = next(p for p in prop["properties"] if p["name"] == "Temperature Value")
                    values.append(temp["evaluated_value"])
        return values

    if linked_temperatures(before) != [20.0, 20.0]:
        raise ValueError("Expected two linked 20 Celsius external conditions")
    inlet = next(b for b in sim.Simulation.SimulationObjects if b.DescriptorName == "Inlet")
    named = inlet.PropertyTable.GetNamedPropertyTablePropertyValue("Inlet Conditions")
    mark = executor.session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "MCP linked-table readback audit"
    )
    try:
        named.PropertyTable.SetScalarWithDataPropertyValue(
            "Temperature Value", 21.0, sim.UnitCollection.FindObject("Celsius")
        )
        changed = module.capture_boundary_state(sim, nx)
        if (
            linked_temperatures(changed) != [21.0, 21.0]
            or changed["boundaries"] == before["boundaries"]
        ):
            raise ValueError("Shared linked temperature change was not observed")
        if changed["effective_membership"] != before["effective_membership"]:
            raise ValueError("Value edit unexpectedly changed membership")
    finally:
        executor.session.UndoToMark(mark, None)
    restored = module.capture_boundary_state(sim, nx)
    if restored != before:
        raise ValueError("Linked table undo did not restore inspected state")
    result = {
        "document": executor._reference(sim, "part", sim, "SIM")["id"],
        "before": before,
        "changed": changed,
        "restored": restored,
        "native_linked_change_and_undo_verified": True,
        "solver_launched": False,
        "numerical_acceptance": "not_tested",
    }
    (root / "verification.json").write_text(json.dumps(result, indent=2))
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\linked-boundary-state.json").write_text(
        json.dumps(result, indent=2)
    )
    return result
