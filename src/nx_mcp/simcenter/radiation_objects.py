"""NX 2606 radiation simulation objects with explicit active selectors and recovery."""

import math

from nx_mcp.runtime import NXToolError

SIDES = {"both": 0, "top": 1, "bottom": 2}


def validate(kind, emissivity, side, include_environment):
    message = None
    if kind == "emissivity":
        if (
            type(emissivity) not in (float, int)
            or not math.isfinite(emissivity)
            or not 0 <= emissivity <= 1
        ):
            message = "emissivity must be finite and dimensionless in [0,1]"
        elif not isinstance(side, str) or side not in SIDES:
            message = "side must be both, top or bottom"
    elif kind == "enclosure":
        if type(include_environment) is not bool:
            message = "include_radiative_environment must be boolean"
    else:
        message = "Unsupported radiation object kind"
    if message:
        raise NXToolError(
            "NX_INVALID_ARGUMENT", message, details={"mutation_outcome": "not_started"}
        )


def verify(properties, kind, emissivity, side, include_environment):
    rows = {p["name"]: p for p in properties}
    if kind == "enclosure":
        if (
            rows.get("Calculation Method", {}).get("value") != 1
            or rows.get("Include Radiative Environment", {}).get("value") is not include_environment
        ):
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Enclosure active settings differ")
    else:
        row = rows.get("Emissivity", {})
        try:
            matches = (
                row.get("units") == "dimensionless"
                and row.get("representation") == "expression"
                and not row.get("inspection_status")
                and math.isclose(float(row["expression"]), emissivity, rel_tol=1e-12, abs_tol=1e-12)
            )
        except (TypeError, ValueError, KeyError):
            matches = False
        if not matches or rows.get("Apply Override Set to", {}).get("value") != SIDES[side]:
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Emissivity override selector/value/units differ"
            )


def create(
    session,
    sim,
    faces,
    name,
    provenance,
    *,
    kind,
    emissivity=None,
    side="both",
    include_environment=True,
):
    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    validate(kind, emissivity, side, include_environment)
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
        or any(not isinstance(f, cae.CAEFace) or f.OwningPart != sim for f in faces)
    ):
        raise NXToolError(
            "NX_SIM_SELECTION_OWNER",
            "Supply 1..1000 distinct CAE faces belonging to the SIM",
            details={"mutation_outcome": "not_started"},
        )
    if any(o.Name.casefold() == name.casefold() for o in sim.Simulation.SimulationObjects):
        raise NXToolError(
            "NX_SIM_NAME_CONFLICT",
            "Simulation object name already exists",
            details={"mutation_outcome": "not_started"},
        )
    require_solver_idle()
    descriptor = "Override Thermal Emissivity" if kind == "emissivity" else "Enclosure Radiation"

    def snapshot():
        return {
            "objects": sorted(int(o.Tag) for o in sim.Simulation.SimulationObjects),
            "expressions": sorted(int(e.Tag) for e in sim.Expressions),
            "solution_bcs": sorted(int(b.Tag) for b in solution.GetBcs()),
        }

    before = snapshot()
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP " + descriptor)
    builder = None
    try:
        builder = sim.Simulation.CreateBcBuilderForSimulationObjectDescriptor(descriptor, name)
        table = builder.PropertyTable
        if kind == "emissivity":
            expression = sim.Expressions.CreateSystemExpression("Number", str(emissivity))
            table.SetScalarFieldWrapperPropertyValue(
                "Emissivity", sim.FieldManager.CreateScalarFieldWrapperWithExpression(expression)
            )
            table.SetIntegerPropertyValue("Apply Override Set to", SIDES[side])
        else:
            table.SetIntegerPropertyValue("Calculation Method", 1)
            table.SetBooleanPropertyValue("Include Radiative Environment", include_environment)
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
        verify(properties, kind, emissivity, side, include_environment)
        _, actual = boundary.TargetSetManager.GetTargetSetMembers(0)
        if sorted(int(m.Obj.Tag) for m in actual) != sorted(int(f.Tag) for f in faces):
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Radiation object target set differs")
        if kind == "enclosure":
            if boundary.TargetSetManager.TargetSetCount != 2:
                raise NXToolError(
                    "NX_SIM_READBACK_MISMATCH", "Unexpected enclosure target-set count"
                )
            _, extra = boundary.TargetSetManager.GetTargetSetMembers(1)
            if any(m is not None and m.Obj is not None for m in extra):
                raise NXToolError(
                    "NX_SIM_READBACK_MISMATCH", "Unrequested secondary enclosure members"
                )
        if (
            boundary.Tag not in {b.Tag for b in solution.GetBcs()}
            or boundary.GetStringUserAttribute("NX_MCP_PROVENANCE", -1) != provenance
        ):
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Radiation object membership/provenance differs"
            )
        return {
            "boundary": boundary,
            "descriptor": descriptor,
            "properties": properties,
            "face_count": len(actual),
            "solution_membership_verified": True,
            "provenance": provenance,
            "emissivity": float(emissivity) if kind == "emissivity" else None,
            "side": side if kind == "emissivity" else None,
            "calculation_method": "deterministic" if kind == "enclosure" else None,
            "include_radiative_environment": include_environment if kind == "enclosure" else None,
            "secondary_target_set": "empty; not exposed" if kind == "enclosure" else None,
            "saved": False,
            "solver_launched": False,
            "numerical_acceptance": "not_established",
        }
    except Exception as error:
        cleanup = []
        if builder is not None:
            try:
                builder.Destroy()
            except Exception as exc:
                cleanup.append(str(exc))
            builder = None
        try:
            session.UndoToMark(mark, None)
            if snapshot() != before:
                cleanup.append("Creation state not restored")
            session.DeleteUndoMark(mark, None)
        except Exception as exc:
            cleanup.append(str(exc))
        raise NXToolError(
            "NX_SIM_RECOVERY_INCOMPLETE"
            if cleanup
            else getattr(error, "code", "NX_SIM_AUTHORING_FAILED"),
            "Radiation object creation failed; inspect recovery details",
            nx_code=getattr(error, "nx_code", getattr(error, "ErrorCode", None)),
            details={
                "mutation_outcome": "partial" if cleanup else "rolled_back",
                "cleanup": cleanup,
                "cause": str(error),
                "verification_scope": "simulation objects, expressions, active solution membership",
            },
        ) from error
    finally:
        if builder is not None:
            builder.Destroy()
