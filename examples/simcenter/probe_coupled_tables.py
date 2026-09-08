"""Native coupled setup discovery on a new disposable benchmark; no solve."""


def run(executor):
    import NXOpen as nx

    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if "E-coupled-setup-20260908-r1" not in sim.FullPath:
        raise ValueError("Use the retained isolated coupled setup")
    created = {"path": sim.FullPath}
    step = {"count": sim.Simulation.ActiveSolution.StepCount}
    solution = sim.Simulation.ActiveSolution
    candidates = [
        ("Thermal Parameters", "Thermal Parameters"),
        ("Flow Solution Parameters", "Flow Solution Parameters"),
        ("Flow Surface Parameters", "Flow Surface Parameters"),
        ("Coupled Solution Parameters", "Coupled Solution Parameters"),
        ("Thermal-Flow Output Requests", "Thermal-Flow Output Requests"),
        ("Thermal-Flow Output Requests", "Multiphysics Thermal-Flow Output Requests"),
    ]
    rows = []
    for key, descriptor in candidates:
        original = solution.PropertyTable.GetNamedPropertyTablePropertyValue(key)
        assert original is None, key
        before = {int(t.Tag) for t in sim.ModelingObjectPropertyTables}
        mark = executor.session.SetUndoMark(
            nx.Session.MarkVisibility.Visible, "NX MCP coupled descriptor probe"
        )
        row = {"property": key, "descriptor": descriptor}
        try:
            table = sim.ModelingObjectPropertyTables.CreateModelingObjectPropertyTable(
                descriptor,
                "NX MULTIPHYSICS - Coupled Thermal-Flow",
                "NX MULTIPHYSICS",
                "PROBE " + key,
                0,
            )
            solution.PropertyTable.SetNamedPropertyTablePropertyValue(key, table)
            assert solution.PropertyTable.GetNamedPropertyTablePropertyValue(key) == table
            row.update(
                accepted=True,
                actual_descriptor=table.DescriptorType,
                properties=read_properties(table.PropertyTable, nx),
            )
        except Exception as error:
            row.update(
                accepted=False,
                nx_code=getattr(error, "ErrorCode", None),
                error_type=type(error).__name__,
                message=str(error),
            )
        finally:
            executor.session.UndoToMark(mark, None)
            assert {int(t.Tag) for t in sim.ModelingObjectPropertyTables} == before
            assert solution.PropertyTable.GetNamedPropertyTablePropertyValue(key) is None
            executor.session.DeleteUndoMark(mark, None)
        row["rollback_verified"] = True
        rows.append(row)
    return {
        "created": created,
        "step": step,
        "table_probes": rows,
        "solver_launched": False,
        "numerical_acceptance": False,
    }
