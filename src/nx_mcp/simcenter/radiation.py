"""Documented NX 2606 simple environment radiation; effective-emissivity mode."""

import math

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.convection_environment import SOURCES
from nx_mcp.simcenter.recovery import authoring_snapshot, rollback_creation


def validate(effective_emissivity, temperature_source, temperature_k):
    message = None
    if (
        type(effective_emissivity) not in (int, float)
        or not math.isfinite(effective_emissivity)
        or not 0 <= effective_emissivity <= 1
    ):
        message = "effective_emissivity must be a finite dimensionless value in [0,1]"
    elif not isinstance(temperature_source, str) or temperature_source not in SOURCES:
        message = "Unknown radiation temperature source"
    elif temperature_source == "specified":
        if (
            type(temperature_k) not in (int, float)
            or not math.isfinite(temperature_k)
            or temperature_k < 0
        ):
            message = "Specified environment requires finite temperature_k >= 0 K"
    elif temperature_k is not None:
        message = "temperature_k is only valid with specified temperature source"
    if message:
        raise NXToolError(
            "NX_INVALID_ARGUMENT", message, details={"mutation_outcome": "not_started"}
        )


def verify(properties, emissivity, source, temperature_k):
    rows = {p["name"]: p for p in properties}
    for name, expected in [
        ("Radiation From", 0),
        ("Emissivity Type", 2),
        ("Temperature Type", SOURCES[source]),
    ]:
        if rows.get(name, {}).get("value") != expected:
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Radiation selector mismatch: " + name)
    expected_values = [("Effective Emissivity", emissivity, "dimensionless")]
    if source == "specified":
        expected_values.append(("Temperature", temperature_k, "Kelvin"))
    for name, expected, unit in expected_values:
        row = rows.get(name, {})
        try:
            matches = (
                row.get("representation") == "expression"
                and row.get("units") == unit
                and not row.get("inspection_status")
                and math.isclose(float(row["expression"]), expected, rel_tol=1e-12, abs_tol=1e-12)
            )
        except (ValueError, TypeError, KeyError):
            matches = False
        if not matches:
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Radiation value/units mismatch: " + name)


def create_environment(
    session,
    sim,
    faces,
    effective_emissivity,
    name,
    provenance,
    temperature_source="radiative_ambient",
    temperature_k=None,
):
    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    validate(effective_emissivity, temperature_source, temperature_k)
    solution = sim.Simulation.ActiveSolution
    if (
        session.Parts.BaseWork != sim
        or solution is None
        or solution.SolverType != "NX MULTIPHYSICS"
        or solution.AnalysisType != "Thermal"
    ):
        raise NXToolError(
            "NX_SIM_UNSUPPORTED",
            "Activate an NX MULTIPHYSICS Thermal SIM",
            details={"mutation_outcome": "not_started"},
        )
    if (
        not isinstance(name, str)
        or not name.strip()
        or not isinstance(provenance, str)
        or not provenance.strip()
    ):
        raise NXToolError(
            "NX_INVALID_ARGUMENT",
            "Nonempty name and provenance required",
            details={"mutation_outcome": "not_started"},
        )
    if (
        not 1 <= len(faces) <= 1000
        or len({int(f.Tag) for f in faces}) != len(faces)
        or any(f.OwningPart != sim for f in faces)
    ):
        raise NXToolError(
            "NX_SIM_SELECTION_OWNER",
            "Supply 1..1000 distinct faces belonging to the selected SIM",
            details={"mutation_outcome": "not_started"},
        )
    if any(b.Name.casefold() == name.casefold() for b in sim.Simulation.Constraints):
        raise NXToolError(
            "NX_SIM_NAME_CONFLICT",
            "Constraint name already exists",
            details={"mutation_outcome": "not_started"},
        )
    require_solver_idle()
    before = authoring_snapshot(sim)
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP environment radiation")
    builder = None
    try:
        builder = sim.Simulation.CreateBcBuilderForConstraintDescriptor(
            "Simple Environment Radiation", name
        )
        table = builder.PropertyTable
        table.SetIntegerPropertyValue("Radiation From", 0)
        table.SetIntegerPropertyValue("Emissivity Type", 2)
        table.SetIntegerPropertyValue("Temperature Type", SOURCES[temperature_source])
        expression = sim.Expressions.CreateSystemExpression("Number", str(effective_emissivity))
        table.SetScalarFieldWrapperPropertyValue(
            "Effective Emissivity",
            sim.FieldManager.CreateScalarFieldWrapperWithExpression(expression),
        )
        if temperature_source == "specified":
            expression = sim.Expressions.CreateSystemNumberExpression(
                str(temperature_k), sim.UnitCollection.FindObject("Kelvin")
            )
            table.SetScalarFieldWrapperPropertyValue(
                "Temperature", sim.FieldManager.CreateScalarFieldWrapperWithExpression(expression)
            )
        members = []
        for face in faces:
            member = cae.SetObject()
            member.Obj, member.SubType, member.SubId = face, cae.CaeSetObjectSubType.NotSet, 0
            members.append(member)
        builder.TargetSetManager.SetTargetSetMembers(0, members)
        boundary = builder.CommitAddBc()
        builder.Destroy()
        builder = None
        boundary.SetUserAttribute("NX_MCP_PROVENANCE", -1, provenance, nx.Update.Option.Now)
        properties = read_properties(boundary.PropertyTable, nx)
        verify(properties, effective_emissivity, temperature_source, temperature_k)
        _, actual = boundary.TargetSetManager.GetTargetSetMembers(0)
        if sorted(int(m.Obj.Tag) for m in actual) != sorted(int(f.Tag) for f in faces):
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Radiation target association differs")
        if (
            boundary.Tag not in {b.Tag for b in solution.GetBcs()}
            or boundary.GetStringUserAttribute("NX_MCP_PROVENANCE", -1) != provenance
        ):
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Radiation membership/provenance differs")
        return {
            "boundary": boundary,
            "properties": properties,
            "effective_emissivity": float(effective_emissivity),
            "emissivity_units": "dimensionless",
            "temperature_source": temperature_source,
            "temperature_k": float(temperature_k) if temperature_source == "specified" else None,
            "environment_dependency": "boundary constant"
            if temperature_source == "specified"
            else "native solution ambient; effective value not resolved",
            "face_count": len(actual),
            "solution_membership_verified": True,
            "provenance": provenance,
            "saved": False,
            "solver_launched": False,
            "scope": "Simple environment radiation, top-side effective emissivity; not enclosure/view-factor authoring or numerical validation",
        }
    except Exception as error:
        pending, builder = builder, None
        rollback_creation(session, sim, mark, pending, before, error)
    finally:
        if builder is not None:
            builder.Destroy()
