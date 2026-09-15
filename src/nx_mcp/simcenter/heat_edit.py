"""Guarded edits of existing constant, single-body total heat loads."""
import math

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.internal_fan import snapshot
from nx_mcp.simcenter.recovery import authoring_snapshot


def inspect(sim, load):
    import NXOpen as nx
    import NXOpen.CAE as cae
    from nx_mcp.simcenter.properties import read_properties

    if load.OwningPart != sim or load.DescriptorName != "Heat Load":
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Select a total Heat Load owned by this SIM")
    if load.GetStringUserAttribute("NX_MCP_ENERGY_ACCOUNTING", -1) != "internal_heat":
        raise NXToolError("NX_SIM_UNSUPPORTED_CONFIGURATION", "Requires labelled internal heat")
    p = load.PropertyTable
    props = read_properties(p, nx)
    if any("inspection_status" in x for x in props):
        raise NXToolError("NX_SIM_UNSUPPORTED_CONFIGURATION", "Heat properties must be fully readable")
    by_name = {x["name"]: x for x in props}
    expected = {"Selection Method": 0, "Override Region": False,
                "Specify Reference Temperature Set": False, "Control Heater": False,
                "Specify Layer to Apply to": False, "Apply to": 0, "Layer Number": 1,
                "Per Element": False, "Per Node": False, "distributionType": 32,
                "Custom Settings Option": False}
    if any(by_name.get(k, {}).get("value") != v for k, v in expected.items()):
        raise NXToolError("NX_SIM_UNSUPPORTED_CONFIGURATION", "Requires simple constant total body heat")
    if by_name.get("Heat Load Override", {}).get("expression") != "-777777":
        raise NXToolError("NX_SIM_UNSUPPORTED_CONFIGURATION", "Heat override is unsupported")
    wrapper = p.GetScalarFieldWrapperPropertyValue("Heat Load")
    expr = wrapper.GetExpression() if wrapper else None
    if expr is None or wrapper.GetField() is not None or expr.Units is None or expr.Units.Symbol != "W":
        raise NXToolError("NX_SIM_UNSUPPORTED_CONFIGURATION", "Requires constant expression in watts")
    try:
        power = float(expr.GetFormula())
    except (ValueError, TypeError) as error:
        raise NXToolError("NX_SIM_UNSUPPORTED_CONFIGURATION", "Parameterized heat is unsupported") from error
    if not math.isfinite(power) or power < 0:
        raise NXToolError("NX_SIM_UNSUPPORTED_CONFIGURATION", "Requires finite nonnegative heat")
    targets = []
    for index in range(load.TargetSetManager.TargetSetCount):
        _, members = load.TargetSetManager.GetTargetSetMembers(index)
        for m in members:
            if m is None or m.Obj is None:
                continue
            if (index != 0 or not isinstance(m.Obj, cae.CAEBody) or m.Obj.OwningPart != sim
                    or int(m.SubId) != 0 or str(m.SubType) != "0"):
                raise NXToolError("NX_SIM_UNSUPPORTED_CONFIGURATION", "Requires one SIM body target")
            targets.append((index, int(m.Obj.Tag), str(m.SubType), int(m.SubId)))
    if len(targets) != 1:
        raise NXToolError("NX_SIM_UNSUPPORTED_CONFIGURATION", "Requires exactly one body")
    return {"power_w": power, "wrapper": int(wrapper.Tag), "expression": int(expr.Tag),
            "provenance": load.GetStringUserAttribute("NX_MCP_PROVENANCE", -1),
            "invariants": {"name": load.Name, "targets": targets,
                           "target_set_count": load.TargetSetManager.TargetSetCount,
                           "properties": [x for x in props if x["name"] != "Heat Load"],
                           "energy_accounting": "internal_heat",
                           "overlap_policy": load.GetStringUserAttribute("NX_MCP_HEAT_OVERLAP_POLICY", -1)}}


def inventory(sim):
    from nx_mcp.simcenter.boundary_state import capture_effective_membership
    return {**snapshot(sim), **authoring_snapshot(sim),
            "membership": capture_effective_membership(sim),
            "heat": {str(int(x.Tag)): inspect(sim, x) for x in sim.Simulation.Loads
                     if x.DescriptorName == "Heat Load"}}


def edit(session, sim, load, expected_power_w, power_w, provenance):
    import NXOpen as nx

    for value in (expected_power_w, power_w):
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise NXToolError("NX_INVALID_ARGUMENT", "Expected and new heat must be finite nonnegative watts")
    if not isinstance(provenance, str) or not provenance.strip() or len(provenance) > 4096:
        raise NXToolError("NX_INVALID_ARGUMENT", "Supply nonempty provenance of at most 4096 characters")
    sol = sim.Simulation.ActiveSolution
    if (session.Parts.BaseWork != sim or sol is None or sol.SolverType != "NX MULTIPHYSICS"
            or sol.AnalysisType != "Thermal" or sol.StepCount != 1
            or list(sim.Simulation.Solutions) != [sol]):
        raise NXToolError("NX_SIM_SOLUTION_TYPE", "Activate a single-solution, single-step Multiphysics Thermal SIM")
    before = inspect(sim, load)
    if not math.isclose(before["power_w"], expected_power_w, rel_tol=1e-12, abs_tol=1e-12):
        raise NXToolError("NX_SIM_STALE_VALUE", "Existing power differs from expected; inspect before editing")
    old = inventory(sim)
    key = str(int(load.Tag))
    if key not in old["heat"] or not old["membership"]["comparison_verified"]:
        raise NXToolError("NX_SIM_UNSUPPORTED_CONFIGURATION", "Requires owned heat and fully readable membership")
    ref = {"journal_id": load.JournalIdentifier, "owner_path": sim.FullPath}
    if (ref not in old["membership"]["solution"]["bcs"]
            or any(ref in s["bcs"] for s in old["membership"]["steps"])):
        raise NXToolError("NX_SIM_UNSUPPORTED_CONFIGURATION", "Requires direct solution heat, without step overrides")
    result = {"before_w": before["power_w"], "power_w": power_w, "provenance": provenance,
              "saved": False, "solver_launched": False, "results_stale": True,
              "native_export_effectiveness": "not_verified"}
    if before["power_w"] == power_w and before["provenance"] == provenance:
        return {**result, "changed": False}
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP total heat edit")
    try:
        # Never edit an existing expression: other loads may share it.
        expr = sim.Expressions.CreateSystemNumberExpression(str(float(power_w)), sim.UnitCollection.FindObject("Watt"))
        wrapper = sim.FieldManager.CreateScalarFieldWrapperWithExpression(expr)
        load.PropertyTable.SetScalarFieldWrapperPropertyValue("Heat Load", wrapper)
        load.SetUserAttribute("NX_MCP_PROVENANCE", -1, provenance, nx.Update.Option.Now)
        if session.UpdateManager.DoUpdate(mark):
            raise NXToolError("NX_SIM_UPDATE_FAILED", "Heat update reported errors")
        actual = inspect(sim, load)
        after = inventory(sim)
        if (not math.isclose(actual["power_w"], power_w, rel_tol=1e-12, abs_tol=1e-12)
                or actual["provenance"] != provenance or actual["invariants"] != before["invariants"]
                or any(after[k] != old[k] for k in ("objects", "loads", "constraints", "solution_bcs", "membership"))
                or {k:v for k,v in after["heat"].items() if k != key} != {k:v for k,v in old["heat"].items() if k != key}):
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Heat edit or preserved state did not match")
        return {**result, "changed": True, "preserved": actual["invariants"],
                "heat_load_count": len(after["heat"]),
                "all_heat_loads_total_w": sum(v["power_w"] for v in after["heat"].values())}
    except Exception as error:
        try:
            session.UndoToMark(mark, None)
            if inspect(sim, load) != before or inventory(sim) != old:
                raise RuntimeError("Heat binding, provenance or inventory not restored")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError("NX_SIM_ROLLBACK_FAILED", "Heat edit rollback incomplete",
                              details={"mutation_outcome": "partial", "operation_error": str(error),
                                       "recovery_error": str(recovery)}) from error
        raise NXToolError(getattr(error, "code", "NX_SIM_AUTHORING_FAILED"), "Heat edit failed and was rolled back",
                          details={"mutation_outcome": "rolled_back", "operation_error": str(error)}) from error
