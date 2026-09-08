"""Prepare the isolated finned baseline; inspect the exported deck before launch."""


def run(executor):
    import json
    import shutil
    import time

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if "E-finned-run-20260908-r1" not in sim.FullPath:
        raise ValueError("Activate saved finned baseline")
    receipt = executor.workspace.resolve("ui-benchmarks/E-finned-prepare-r2.json")
    if receipt.exists():
        return {
            "replayed": True,
            "receipt": json.loads(receipt.read_text()),
            "solver_launched": False,
        }
    rows = {"solver_launched": False, "acceptance": False}

    def record(key, value):
        rows[key] = value
        receipt.write_text(json.dumps(rows, indent=2))

    record(
        "copy",
        executor._sim_save_as(
            executor._reference(sim, "part", sim, "SIM")["id"],
            "ui-benchmarks/E-finned-run-20260908-r2/finned_run_r2.sim",
        ),
    )
    import NXOpen as nx

    opening = next(b for b in sim.Simulation.SimulationObjects if b.DescriptorName == "Opening")
    props = opening.PropertyTable
    assert props.GetIntegerPropertyValue("Pressure") == 1
    assert props.GetIntegerPropertyValue("External Pressure Type") == 0
    old = props.GetScalarFieldWrapperPropertyValue("Pressure Value").GetExpression()
    assert old.GetFormula() == "-777777"
    expr = sim.Expressions.CreateSystemNumberExpression(
        "101325.0", sim.UnitCollection.FindObject("PressurePascals")
    )
    props.SetScalarFieldWrapperPropertyValue(
        "Pressure Value", sim.FieldManager.CreateScalarFieldWrapperWithExpression(expr)
    )
    value, unit = props.GetScalarWithDataPropertyValue("Pressure Value")
    assert value == 101325 and unit.Name == "PressurePascals"
    record("opening_pressure", {"mode": "specified_absolute", "value": value, "units": unit.Name})
    status = sim.Save(nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue)
    if status:
        status.Dispose()
    started = time.monotonic()
    record(
        "prepare",
        executor._sim_prepare_solve(
            executor._reference(sim, "part", sim, "SIM")["id"], "coupled-finned-baseline-r2"
        ),
    )
    root = executor.workspace.resolve("ui-benchmarks/E-finned-run-20260908-r2")
    decks = list(root.glob("*.xml"))
    assert len(decks) == 1
    shutil.copyfile(
        decks[0], r"Z:\nx-mcp-integration\simcenter-discovery\finned-baseline-r2-deck.xml"
    )
    record("prepare_seconds", time.monotonic() - started)
    return rows
