"""Native two-region contact coupling with explicit total resistance/conductance."""

import math

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.properties import read_properties

MODES = {
    "resistance": (1, "Total Resistance", "ThermalResistance_Metric4", "dK/W", "K/W"),
    "conductance": (0, "Total Conductance", "ThermalConductance_Metric4", "W/dK", "W/K"),
}


def validate_contact(primary, secondary, mode, value, name, provenance):
    if (
        mode not in MODES
        or type(value) not in (float, int)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise NXToolError(
            "NX_INVALID_ARGUMENT",
            "Select resistance or conductance and a positive finite total value",
        )
    if (
        not isinstance(name, str)
        or not name.strip()
        or not isinstance(provenance, str)
        or not provenance.strip()
    ):
        raise NXToolError("NX_INVALID_ARGUMENT", "Nonempty name and provenance required")
    for faces in (primary, secondary):
        if not 1 <= len(faces) <= 1000 or len({int(f.Tag) for f in faces}) != len(faces):
            raise NXToolError("NX_INVALID_ARGUMENT", "Each region requires 1..1000 distinct faces")
    if {int(f.Tag) for f in primary} & {int(f.Tag) for f in secondary}:
        raise NXToolError(
            "NX_SIM_SELECTION_OVERLAP", "Primary and secondary regions must be disjoint"
        )


def verify_contact_value(actual, value, unit_name):
    if (
        actual.get("representation") != "expression"
        or float(actual.get("expression", "nan")) != float(value)
        or actual.get("units") != unit_name
    ):
        raise NXToolError(
            "NX_SIM_READBACK_MISMATCH",
            "Contact value or units differ after commit",
            details={"readback": actual},
        )


def create_contact(session, sim, primary, secondary, mode, value, name, provenance):
    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    validate_contact(primary, secondary, mode, value, name, provenance)
    sol = sim.Simulation.ActiveSolution
    if (
        session.Parts.BaseWork != sim
        or sol is None
        or sol.SolverType != "NX MULTIPHYSICS"
        or sol.AnalysisType != "Thermal"
    ):
        raise NXToolError("NX_SIM_UNSUPPORTED", "Activate an NX MULTIPHYSICS Thermal SIM")
    if any(not isinstance(f, cae.CAEFace) or f.OwningPart != sim for f in primary + secondary):
        raise NXToolError(
            "NX_SIM_SELECTION_OWNER", "Select CAE faces owned by the selected SIM occurrence"
        )
    if any(o.Name.casefold() == name.casefold() for o in sim.Simulation.SimulationObjects):
        raise NXToolError("NX_SIM_NAME_CONFLICT", "Simulation object name already exists")
    require_solver_idle()
    selector, key, unit_name, symbol, units = MODES[mode]
    unit = sim.UnitCollection.FindObject(unit_name)
    if unit.Symbol != symbol:
        raise NXToolError(
            "NX_SIM_UNIT_MISMATCH", "Installed contact unit differs from verified unit"
        )

    def snapshot():
        return {
            "objects": sorted(int(o.Tag) for o in sim.Simulation.SimulationObjects),
            "expressions": sorted(int(e.Tag) for e in sim.Expressions),
            "solution_bcs": sorted(int(b.Tag) for b in sol.GetBcs()),
        }

    before = snapshot()
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP thermal contact")
    builder = None
    try:
        builder = sim.Simulation.CreateBcBuilderForSimulationObjectDescriptor(
            "Contact Thermal Coupling", name
        )
        props = builder.PropertyTable
        props.SetBooleanPropertyValue("Override Secondary Region", False)
        props.SetBooleanPropertyValue("Specify Region Side to Apply to", False)
        props.SetIntegerPropertyValue("Type", selector)
        if mode == "conductance":
            props.SetBooleanPropertyValue("Per Element", False)
        expression = sim.Expressions.CreateSystemNumberExpression(str(value), unit)
        wrapper = sim.FieldManager.CreateScalarFieldWrapperWithExpression(expression)
        props.SetScalarFieldWrapperPropertyValue(key, wrapper)
        for index, faces in enumerate((primary, secondary)):
            members = []
            for face in faces:
                member = cae.SetObject()
                member.Obj, member.SubType, member.SubId = face, cae.CaeSetObjectSubType.NotSet, 0
                members.append(member)
            builder.TargetSetManager.SetTargetSetMembers(index, members)
        bc = builder.CommitAddBc()
        builder.Destroy()
        builder = None
        bc.SetUserAttribute("NX_MCP_PROVENANCE", -1, provenance, nx.Update.Option.Now)
        p = bc.PropertyTable
        if (
            p.GetBooleanPropertyValue("Override Secondary Region")
            or p.GetBooleanPropertyValue("Specify Region Side to Apply to")
            or p.GetIntegerPropertyValue("Type") != selector
        ):
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Contact mode selectors differ after commit"
            )
        if mode == "conductance" and p.GetBooleanPropertyValue("Per Element"):
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Total conductance unexpectedly applied per element"
            )
        properties = read_properties(p, nx)
        actual = next(row for row in properties if row["name"] == key)
        verify_contact_value(actual, value, unit_name)
        for index, faces in enumerate((primary, secondary)):
            _, members = bc.TargetSetManager.GetTargetSetMembers(index)
            if sorted(
                int(m.Obj.Tag) for m in members if m is not None and m.Obj is not None
            ) != sorted(int(f.Tag) for f in faces):
                raise NXToolError(
                    "NX_SIM_READBACK_MISMATCH", "Contact face association differs after commit"
                )
        if (
            bc not in list(sol.GetBcs())
            or bc.GetStringUserAttribute("NX_MCP_PROVENANCE", -1) != provenance
        ):
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Contact solution membership or provenance differs"
            )
        return {
            "boundary": bc,
            "mode": mode,
            "value": float(value),
            "units": units,
            "properties": properties,
            "primary_count": len(primary),
            "secondary_count": len(secondary),
            "solution_membership_verified": True,
            "provenance": provenance,
            "saved": False,
            "solver_launched": False,
        }
    except Exception as error:
        cleanup = []
        if builder is not None:
            try:
                builder.Destroy()
            except Exception as exc:
                cleanup.append(str(exc))
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
            "Contact authoring failed; inspect recovery details",
            nx_code=getattr(error, "nx_code", getattr(error, "ErrorCode", None)),
            details={
                "mutation_outcome": "partial" if cleanup else "rolled_back",
                "cleanup": cleanup,
                "cause": str(error),
                "cause_details": getattr(error, "details", {}),
                "verification_scope": "simulation objects, expressions, solution membership",
            },
        ) from error
