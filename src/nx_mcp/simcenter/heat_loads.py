"""Explicit total internal heat on one SIM body occurrence."""

import math

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.recovery import authoring_snapshot, rollback_creation


def create_body_power(
    session,
    sim,
    body,
    power_w,
    name,
    provenance,
    overlap_policy="reject",
    *,
    schedule_field=None,
    schedule_scale=1.0,
):
    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.properties import read_properties

    if session.Parts.BaseWork != sim or body.OwningPart != sim:
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Heat target must belong to the active SIM")
    if (
        isinstance(power_w, bool)
        or not isinstance(power_w, (int, float))
        or not math.isfinite(power_w)
        or power_w < 0
    ):
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Internal heat must be finite and nonnegative watts"
        )
    if not name.strip() or not provenance.strip():
        raise NXToolError("NX_INVALID_ARGUMENT", "Provide heat-source name and provenance")
    for load in sim.Simulation.Loads:
        if load.Name.casefold() == name.casefold():
            raise NXToolError("NX_SIM_NAME_CONFLICT", "A load with that name already exists")
        table = load.PropertyTable
        if "Heat Load" in [
            table.GetPropertyNameByIndex(i) for i in range(table.GetPropertyCount())
        ]:
            for index in range(load.TargetSetManager.TargetSetCount):
                _, members = load.TargetSetManager.GetTargetSetMembers(index)
                if any(
                    m is not None and m.Obj is not None and m.Obj.Tag == body.Tag for m in members
                ):
                    raise NXToolError(
                        "NX_SIM_DUPLICATE_HEAT_SOURCE",
                        "This body already has a heat load; inspect it before assigning another source",
                    )
    from nx_mcp.simcenter.distributed_heat import preflight
    from nx_mcp.simcenter.heat_overlap import inspect_heat_overlap

    with preflight():
        if overlap_policy not in ("reject", "allow_additive"):
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "overlap_policy must be reject or allow_additive"
            )
        overlaps = inspect_heat_overlap(sim, [body])
        if any(row["relation"] == "same_target" for row in overlaps):
            raise NXToolError(
                "NX_SIM_DUPLICATE_HEAT_SOURCE",
                "This body already has an assigned heat source",
                details={"overlaps": overlaps},
            )
        if overlaps and overlap_policy == "reject":
            raise NXToolError(
                "NX_SIM_OVERLAPPING_HEAT_SOURCE",
                "An existing face/body heat source overlaps this body",
                details={
                    "overlaps": overlaps,
                    "next_step": "Inspect existing loads; use allow_additive only for separate intended contributions",
                },
            )
    schedule = None
    if schedule_field is not None:
        from nx_mcp.simcenter.heat_schedule import validate_binding

        with preflight():
            schedule = validate_binding(sim, schedule_field, schedule_scale)
    before = authoring_snapshot(sim)
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP internal heat")
    builder = None
    try:
        builder = sim.Simulation.CreateBcBuilderForLoadDescriptor("Heat Load", name)
        if schedule_field is None:
            expression = sim.Expressions.CreateSystemNumberExpression(
                str(power_w), sim.UnitCollection.FindObject("Watt")
            )
            wrapper = sim.FieldManager.CreateScalarFieldWrapperWithExpression(expression)
        else:
            wrapper = sim.FieldManager.CreateScalarFieldWrapperWithField(
                schedule_field, schedule["scale"]
            )
        builder.PropertyTable.SetScalarFieldWrapperPropertyValue("Heat Load", wrapper)
        member = cae.SetObject()
        member.Obj, member.SubType, member.SubId = body, cae.CaeSetObjectSubType.NotSet, 0
        builder.TargetSetManager.SetTargetSetMembers(0, [member])
        load = builder.CommitAddBc()
        builder.Destroy()
        builder = None
        load.SetUserAttribute("NX_MCP_PROVENANCE", -1, provenance, nx.Update.Option.Now)
        load.SetUserAttribute("NX_MCP_ENERGY_ACCOUNTING", -1, "internal_heat", nx.Update.Option.Now)
        load.SetUserAttribute(
            "NX_MCP_HEAT_OVERLAP_POLICY", -1, overlap_policy, nx.Update.Option.Now
        )
        if load.GetStringUserAttribute("NX_MCP_HEAT_OVERLAP_POLICY", -1) != overlap_policy:
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Heat overlap policy did not persist")
        if load.GetStringUserAttribute("NX_MCP_PROVENANCE", -1) != provenance:
            raise ValueError("Heat provenance did not commit")
        properties = read_properties(load.PropertyTable, nx)
        actual = next(p for p in properties if p["name"] == "Heat Load")
        _, targets = load.TargetSetManager.GetTargetSetMembers(0)
        if (
            (schedule_field is None and float(actual["expression"]) != power_w)
            or len(targets) != 1
            or targets[0].Obj.Tag != body.Tag
        ):
            raise ValueError("Heat power or target changed during commit")
        if schedule is not None:
            from nx_mcp.simcenter.heat_schedule import verify_committed

            verify_committed(sim, load, actual, schedule)
        return {
            "load": load,
            **(
                {"power_w": float(actual["expression"])}
                if schedule is None
                else {"schedule": schedule}
            ),
            "power_units": "W",
            "properties": properties,
            "provenance": provenance,
            "energy_accounting": "internal_heat",
            "target_count": 1,
            "saved": False,
            "solver_launched": False,
            "overlap_policy": overlap_policy,
            "overlaps": overlaps,
        }
    except Exception as error:
        pending_builder, builder = builder, None
        rollback_creation(session, sim, mark, pending_builder, before, error)
    finally:
        if builder is not None:
            builder.Destroy()
