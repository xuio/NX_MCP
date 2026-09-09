def run(executor):
    import NXOpen.CAE as cae
    import traceback
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    nx, session = executor.nxopen, executor.session
    sim = session.Parts.BaseWork
    if "public-multibody-analysis-r1" not in sim.FullPath or not sim.FullPath.endswith(".sim"):
        raise ValueError("Expected isolated SIM")
    before = sorted(int(x.Tag) for x in sim.Simulation.Loads)
    expressions = sorted(int(x.Tag) for x in sim.Expressions)
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP gravity probe")
    builder = None
    result = {}
    try:
        unit = sim.UnitCollection.FindObject("MeterPerSquareSecond")
        values = [0.0, 0.0, -9.80665]
        expr = [sim.Expressions.CreateSystemNumberExpression(str(v), unit) for v in values]
        vector = sim.FieldManager.CreateVectorFieldWrapperWithExpressions(expr)
        builder = sim.Simulation.CreateBcBuilderForLoadDescriptor(
            "ComponentGravityField", "Gravity probe", 0
        )
        builder.PropertyTable.SetIntegerPropertyValue("CSYSOption", 0)
        builder.PropertyTable.SetVectorFieldWrapperPropertyValue("CartesianMagnitude", vector)
        comp = sim.ComponentAssembly.RootComponent.GetChildren()[0]
        members = []
        for body in sim.FemPart.Bodies:
            member = cae.SetObject()
            member.Obj = comp.FindOccurrence(body)
            member.SubType = cae.CaeSetObjectSubType.NotSet
            member.SubId = 0
            members.append(member)
        builder.TargetSetManager.SetTargetSetMembers(0, members)
        load = builder.CommitAddBc()
        builder.Destroy()
        builder = None
        actual = load.PropertyTable.GetVectorFieldWrapperPropertyValue("CartesianMagnitude")
        rows = [
            {
                "value": actual.GetExpressionByIndex(i).Value,
                "si_value": actual.GetExpressionByIndex(i).GetValueUsingUnits(
                    nx.Expression.UnitsOption.Expression
                ),
                "rhs": actual.GetExpressionByIndex(i).RightHandSide,
                "unit": actual.GetExpressionByIndex(i).Units.Name,
            }
            for i in range(3)
        ]
        assert [row["si_value"] for row in rows] == values
        _, targets = load.TargetSetManager.GetTargetSetMembers(0)
        result = {
            "passed": True,
            "values": rows,
            "targets": len(targets),
            "solution_member": any(
                b.Tag == load.Tag for b in sim.Simulation.ActiveSolution.GetBcs()
            ),
            "csys": load.PropertyTable.GetIntegerPropertyValue("CSYSOption"),
        }
    except Exception as error:
        result = {"passed": False, "error": str(error), "traceback": traceback.format_exc()}
    finally:
        if builder:
            builder.Destroy()
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
        result["rollback_verified"] = before == sorted(
            int(x.Tag) for x in sim.Simulation.Loads
        ) and expressions == sorted(int(x.Tag) for x in sim.Expressions)
    return result
