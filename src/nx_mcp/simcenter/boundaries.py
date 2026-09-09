"""Native thermal boundaries with explicit units and committed-state inspection."""

import math

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.recovery import authoring_snapshot, rollback_creation


def verify_face_targets(boundary, faces):
    """Verify native selection readback without modifying the constraint."""
    _, committed = boundary.TargetSetManager.GetTargetSetMembers(0)
    requested_tags = sorted(int(face.Tag) for face in faces)
    actual_tags = sorted(int(member.Obj.Tag) for member in committed)
    if actual_tags != requested_tags:
        raise NXToolError("NX_SIM_READBACK_MISMATCH", "Convection face selection changed on commit")
    return {"committed_face_count": len(committed), "committed_face_tags": actual_tags}


def create_convection(
    session,
    sim,
    faces,
    coefficient_w_m2_k,
    name,
    provenance,
    temperature_source="fluid_ambient",
    temperature_k=None,
):
    """Assign solution-level assumed convection to explicit SIM occurrence faces.

    Uses the selected ambient source or a specified Kelvin constant. Callers must prevent overlap
    with solved fluid interfaces; this primitive does not detect that overlap.
    """
    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.convection_environment import (
        SOURCES,
        validate_environment,
        verify_convection_properties,
    )
    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    validate_environment(temperature_source, temperature_k)
    require_solver_idle()
    if session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the target SIM first")
    if (
        isinstance(coefficient_w_m2_k, bool)
        or not math.isfinite(coefficient_w_m2_k)
        or coefficient_w_m2_k <= 0
    ):
        raise NXToolError("NX_INVALID_ARGUMENT", "Convection coefficient must be positive W/(m² K)")
    if not name.strip() or not provenance.strip() or not faces:
        raise NXToolError("NX_INVALID_ARGUMENT", "Provide a name, provenance and occurrence faces")
    if any(face.OwningPart != sim for face in faces):
        raise NXToolError(
            "NX_SIM_SELECTION_OWNER", "Faces must belong to the target SIM occurrence"
        )
    if any(bc.Name.casefold() == name.casefold() for bc in sim.Simulation.Constraints):
        raise NXToolError("NX_SIM_NAME_CONFLICT", "A constraint with that name already exists")
    unit = sim.UnitCollection.FindObject("ConvectionCoefficient_Metric8")
    before = authoring_snapshot(sim)
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP assumed convection")
    builder = None
    try:
        builder = sim.Simulation.CreateBcBuilderForConstraintDescriptor("Convection", name)
        builder.PropertyTable.SetIntegerPropertyValue("Convect From", 0)
        builder.PropertyTable.SetIntegerPropertyValue("Specify", 0)
        builder.PropertyTable.SetIntegerPropertyValue(
            "Environment Temperature Type", SOURCES[temperature_source]
        )
        if temperature_source == "specified":
            temperature = sim.Expressions.CreateSystemNumberExpression(
                str(temperature_k), sim.UnitCollection.FindObject("Kelvin")
            )
            environment = sim.FieldManager.CreateScalarFieldWrapperWithExpression(temperature)
            builder.PropertyTable.SetScalarFieldWrapperPropertyValue(
                "Environment Temperature", environment
            )
        expression = sim.Expressions.CreateSystemNumberExpression(str(coefficient_w_m2_k), unit)
        wrapper = sim.FieldManager.CreateScalarFieldWrapperWithExpression(expression)
        builder.PropertyTable.SetScalarFieldWrapperPropertyValue("Convection Coefficient", wrapper)
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
        boundary.SetUserAttribute("NX_MCP_COEFFICIENT_BASIS", -1, "assumed", nx.Update.Option.Now)
        if boundary.GetStringUserAttribute("NX_MCP_PROVENANCE", -1) != provenance:
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Convection provenance did not commit")
        properties = read_properties(boundary.PropertyTable, nx)
        environment = verify_convection_properties(
            properties, coefficient_w_m2_k, temperature_source, temperature_k
        )
        if boundary.Tag not in {bc.Tag for bc in sim.Simulation.ActiveSolution.GetBcs()}:
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Convection is absent from the active solution"
            )
        targets = verify_face_targets(boundary, faces)
        return {
            "boundary": boundary,
            "properties": properties,
            "provenance": provenance,
            "coefficient_basis": "assumed",
            **environment,
            "active_solution_membership": True,
            "coefficient_units": "W/(m² K)",
            "provenance_storage": "NX_MCP_PROVENANCE user attribute on native constraint",
            "requested_face_count": len(members),
            **targets,
            "saved": False,
        }
    except Exception as error:
        pending_builder, builder = builder, None
        rollback_creation(session, sim, mark, pending_builder, before, error)
    finally:
        if builder is not None:
            builder.Destroy()


def create_temperature(session, sim, faces, temperature_k, name, provenance):
    """Assign prescribed absolute temperature to explicit SIM occurrence faces."""
    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.properties import read_properties

    if session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the target SIM first")
    if isinstance(temperature_k, bool) or not math.isfinite(temperature_k) or temperature_k < 0:
        raise NXToolError("NX_INVALID_ARGUMENT", "Temperature must be finite and nonnegative K")
    if not name.strip() or not provenance.strip() or not faces:
        raise NXToolError("NX_INVALID_ARGUMENT", "Provide a name, provenance and occurrence faces")
    if any(face.OwningPart != sim for face in faces):
        raise NXToolError(
            "NX_SIM_SELECTION_OWNER", "Faces must belong to the target SIM occurrence"
        )
    if any(bc.Name.casefold() == name.casefold() for bc in sim.Simulation.Constraints):
        raise NXToolError("NX_SIM_NAME_CONFLICT", "A constraint with that name already exists")
    unit = sim.UnitCollection.FindObject("Kelvin")
    before = authoring_snapshot(sim)
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP prescribed temperature")
    builder = None
    try:
        builder = sim.Simulation.CreateBcBuilderForConstraintDescriptor("Temperature", name)
        expression = sim.Expressions.CreateSystemNumberExpression(str(temperature_k), unit)
        wrapper = sim.FieldManager.CreateScalarFieldWrapperWithExpression(expression)
        builder.PropertyTable.SetScalarFieldWrapperPropertyValue("Temperature", wrapper)
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
        boundary.SetUserAttribute(
            "NX_MCP_TEMPERATURE_BASIS", -1, "prescribed", nx.Update.Option.Now
        )
        if boundary.GetStringUserAttribute("NX_MCP_PROVENANCE", -1) != provenance:
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Temperature provenance did not commit")
        properties = read_properties(boundary.PropertyTable, nx)
        coefficient = next(p for p in properties if p["name"] == "Temperature")
        if float(coefficient["expression"]) != temperature_k:
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Temperature changed on commit")
        targets = verify_face_targets(boundary, faces)
        return {
            "boundary": boundary,
            "properties": properties,
            "provenance": provenance,
            "temperature_basis": "prescribed",
            "temperature_units": "K",
            "temperature_k": float(coefficient["expression"]),
            "provenance_storage": "NX_MCP_PROVENANCE user attribute on native constraint",
            "requested_face_count": len(members),
            **targets,
            "saved": False,
        }
    except Exception as error:
        pending_builder, builder = builder, None
        rollback_creation(session, sim, mark, pending_builder, before, error)
    finally:
        if builder is not None:
            builder.Destroy()
