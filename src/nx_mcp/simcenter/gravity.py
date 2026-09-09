"""Constant Cartesian gravity on explicitly selected SIM body occurrences."""

import math

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.recovery import authoring_snapshot, rollback_creation


def validate(acceleration, name):
    if (
        not isinstance(acceleration, list)
        or len(acceleration) != 3
        or any(type(v) not in (int, float) or not math.isfinite(v) for v in acceleration)
    ):
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Supply three finite acceleration components in m/s^2"
        )
    if not isinstance(name, str) or not name.strip():
        raise NXToolError("NX_INVALID_ARGUMENT", "Supply a nonempty gravity name")


def create(session, sim, bodies, acceleration, name):
    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    validate(acceleration, name)
    solution = sim.Simulation.ActiveSolution
    if (
        session.Parts.BaseWork != sim
        or solution is None
        or solution.AnalysisType != "Coupled Thermal-Flow"
    ):
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate a coupled thermal-flow SIM")
    if (
        not bodies
        or len({int(b.Tag) for b in bodies}) != len(bodies)
        or any(b.OwningPart != sim for b in bodies)
    ):
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Select distinct owned SIM bodies")
    require_solver_idle()
    expected = {int(b.Tag) for b in bodies}
    for load in sim.Simulation.Loads:
        if load.Name.casefold() == name.casefold():
            raise NXToolError("NX_SIM_NAME_CONFLICT", "Gravity name already exists")
        if load.DescriptorName in (
            "ComponentGravityField",
            "magnitudeDirectionGravity",
        ):
            for i in range(load.TargetSetManager.TargetSetCount):
                _, members = load.TargetSetManager.GetTargetSetMembers(i)
                if any(m is not None and m.Obj is not None and int(m.Obj.Tag) in expected for m in members):
                    raise NXToolError(
                        "NX_SIM_DUPLICATE_GRAVITY",
                        "Selected bodies already have gravity; inspect before adding another load",
                    )
    before = authoring_snapshot(sim)
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP Cartesian gravity")
    builder = None
    try:
        unit = sim.UnitCollection.FindObject("MeterPerSquareSecond")
        expressions = [
            sim.Expressions.CreateSystemNumberExpression(str(float(v)), unit) for v in acceleration
        ]
        vector = sim.FieldManager.CreateVectorFieldWrapperWithExpressions(expressions)
        builder = sim.Simulation.CreateBcBuilderForLoadDescriptor("ComponentGravityField", name, 0)
        builder.PropertyTable.SetIntegerPropertyValue("CSYSOption", 0)
        builder.PropertyTable.SetVectorFieldWrapperPropertyValue("CartesianMagnitude", vector)
        members = []
        for body in bodies:
            member = cae.SetObject()
            member.Obj, member.SubType, member.SubId = body, cae.CaeSetObjectSubType.NotSet, 0
            members.append(member)
        builder.TargetSetManager.SetTargetSetMembers(0, members)
        load = builder.CommitAddBc()
        builder.Destroy()
        builder = None
        actual = load.PropertyTable.GetVectorFieldWrapperPropertyValue("CartesianMagnitude")
        values = []
        for i in range(3):
            expression = actual.GetExpressionByIndex(i)
            if expression is None or expression.Units.Name != "MeterPerSquareSecond":
                raise ValueError("Gravity expression unit differs")
            values.append(expression.GetValueUsingUnits(nx.Expression.UnitsOption.Expression))
        _, targets = load.TargetSetManager.GetTargetSetMembers(0)
        if {int(m.Obj.Tag) for m in targets} != expected or len(targets) != len(bodies):
            raise ValueError("Gravity target readback differs")
        if load.PropertyTable.GetIntegerPropertyValue("CSYSOption") != 0 or any(
            not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
            for a, b in zip(values, acceleration, strict=True)
        ):
            raise ValueError("Gravity vector or coordinate system differs")
        if not any(b.Tag == load.Tag for b in solution.GetBcs()):
            raise ValueError("Gravity is absent from active solution")
        return {
            "load": load,
            "acceleration_m_s2": values,
            "units": "m/s^2",
            "coordinate_frame": "global_cartesian",
            "target_count": len(targets),
            "solution_member": True,
            "saved": False,
            "solver_launched": False,
            "results_stale": True,
            "buoyancy_changed": False,
        }
    except Exception as error:
        rollback_creation(session, sim, mark, builder, before, error)
