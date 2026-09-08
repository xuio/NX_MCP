"""Explicit benchmark environment and pressure readback; no solve."""


def run(executor):
    import json
    import time
    import NXOpen as nx
    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if "E-development-steady-20260908-r1" not in sim.FullPath:
        raise ValueError("Unexpected SIM")
    receipt = executor.workspace.resolve("ui-benchmarks/E-coupled-environment-r1.json")
    if receipt.exists():
        return {"replayed": True, "receipt": json.loads(receipt.read_text())}
    solution = sim.Simulation.ActiveSolution
    opening = next(b for b in sim.Simulation.SimulationObjects if b.Name == "Coupled Opening")
    rows = []
    started = time.monotonic()
    mark = executor.session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "MCP coupled environment"
    )
    try:
        for key, value in [("Pressure Value", 101325.0), ("External Relative Pressure", 0.0)]:
            expr = sim.Expressions.CreateSystemNumberExpression(
                str(value), sim.UnitCollection.FindObject("PressurePascals")
            )
            wrapper = sim.FieldManager.CreateScalarFieldWrapperWithExpression(expr)
            opening.PropertyTable.SetScalarFieldWrapperPropertyValue(key, wrapper)
        for key, value, unit in [
            ("Fluid Temperature", 20.0, "Celsius"),
            ("Absolute Pressure", 101325.0, "PressurePascals"),
            ("Initial Temperature Value", 20.0, "Celsius"),
        ]:
            solution.PropertyTable.SetBaseScalarWithDataPropertyValue(
                key, value, sim.UnitCollection.FindObject(unit)
            )
            actual, actual_unit = solution.PropertyTable.GetBaseScalarWithDataPropertyValue(key)
            assert actual == value and actual_unit.Name == unit
            rows.append({"property": key, "value": actual, "units": actual_unit.Name})
        props = read_properties(opening.PropertyTable, nx)
        for key, value in [("Pressure Value", 101325.0), ("External Relative Pressure", 0.0)]:
            actual = next(p for p in props if p["name"] == key)
            assert float(actual["expression"]) == value and actual["units"] == "PressurePascals"
        result = {
            "environment": rows,
            "opening": props,
            "solution_properties": read_properties(solution.PropertyTable, nx),
            "elapsed_seconds": time.monotonic() - started,
            "saved": False,
            "solver_launched": False,
            "inlet_temperature_inheritance": "requires exported input and solver readback",
            "interface_coupling": "unverified",
        }
        receipt.write_text(json.dumps(result, indent=2))
        return result
    except Exception:
        executor.session.UndoToMark(mark, None)
        executor.session.DeleteUndoMark(mark, None)
        raise
