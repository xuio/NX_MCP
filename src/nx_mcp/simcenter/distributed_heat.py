"""Uniform heat-flux and volumetric-generation authoring for NX 2606 Thermal."""

import math
from contextlib import contextmanager

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.recovery import authoring_snapshot, rollback_creation
from nx_mcp.simcenter.solver_guard import require_solver_idle

KINDS = {
    "surface_flux": ("Heat Flux", "HeatFlux_Metric5", "W/m^2"),
    "volume_generation": ("Heat Generation", "HeatGeneration_Metric3", "W/m^3"),
}


@contextmanager
def preflight():
    """Classify failures only while the caller has not started native mutation."""
    try:
        yield
    except NXToolError as error:
        error.details.setdefault("mutation_outcome", "not_started")
        error.details.setdefault(
            "next_step",
            "Inspect the selected document and existing loads; correct the request before retrying",
        )
        raise
    except Exception as error:
        raise NXToolError(
            "NX_SIM_PREFLIGHT_FAILED",
            "Could not inspect the heat assignment prerequisites; no mutation started",
            nx_code=getattr(error, "ErrorCode", None),
            details={
                "mutation_outcome": "not_started",
                "next_step": "Inspect document/selection state before retrying",
            },
        ) from error


def validate_density(kind, value):
    if kind not in KINDS:
        raise NXToolError("NX_INVALID_ARGUMENT", "Select surface_flux or volume_generation")
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise NXToolError("NX_INVALID_ARGUMENT", "Heat density must be finite and nonnegative")
    return KINDS[kind]


def measure_applied_power(sim, targets, kind, value):
    """Integrate constant density over native direct-FEM prototype geometry."""
    validate_density(kind, value)
    if str(sim.PartUnits) != "1" or str(sim.FemPart.PartUnits) != "1":
        raise NXToolError(
            "NX_SIM_UNSUPPORTED", "Heat integration requires millimeter SIM/FEM documents"
        )
    import NXOpen.UF

    sf = NXOpen.UF.UFSession.GetUFSession().Sf
    measures = []
    for target in targets:
        prototype = target.Prototype
        if prototype is None or prototype.OwningPart != sim.FemPart:
            raise NXToolError("NX_SIM_SELECTION_OWNER", "Measure direct FEM occurrences only")
        if kind == "surface_flux":
            measure = sf.FaceAskArea(prototype.Tag)
            scale, units = 1e-6, "m^2"
        else:
            measure, _ = sf.BodyAskVolumeAndCentroid(prototype.Tag)
            scale, units = 1e-9, "m^3"
        if not math.isfinite(measure) or measure <= 0:
            raise NXToolError(
                "NX_SIM_GEOMETRY_MEASURE", "Native area/volume must be finite and positive"
            )
        measures.append(measure * scale)
    total = math.fsum(measures) * value
    if not math.isfinite(total):
        raise NXToolError("NX_INVALID_ARGUMENT", "Integrated power is not finite")
    return {
        "total_power_w": total,
        "total_power_status": "integrated_native_geometry",
        "target_measures": measures,
        "measure_units": units,
        "integration_scope": "sum of selected native areas/volumes at constant density; not geometric union or solved heat flow",
    }


def create_distributed_heat(
    session, sim, targets, *, kind, value, name, provenance, overlap_policy="reject"
):
    """Commit an explicit uniform SI load with native geometry power integration.

    Numerical acceptance remains separate from native authoring checks. Targets
    must be SIM occurrence faces for flux or occurrence bodies for generation.
    """
    from nx_mcp.simcenter.properties import read_properties

    with preflight():
        descriptor, unit_name, symbol = validate_density(kind, value)
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(provenance, str)
            or not provenance.strip()
        ):
            raise NXToolError("NX_INVALID_ARGUMENT", "Provide load name and property provenance")
        if not targets or len(targets) > 1000 or len({int(t.Tag) for t in targets}) != len(targets):
            raise NXToolError("NX_INVALID_ARGUMENT", "Provide 1..1000 distinct targets")
        import NXOpen as nx
        import NXOpen.CAE as cae

        solution = sim.Simulation.ActiveSolution
        if session.Parts.BaseWork != sim:
            raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the target SIM")
        if (
            solution is None
            or solution.SolverType != "NX MULTIPHYSICS"
            or solution.AnalysisType != "Thermal"
        ):
            raise NXToolError("NX_SIM_UNSUPPORTED", "This adapter requires NX MULTIPHYSICS Thermal")
        if any(t.OwningPart != sim for t in targets):
            raise NXToolError("NX_SIM_SELECTION_OWNER", "Targets must belong to the active SIM")
        tags = {int(t.Tag) for t in targets}
        for load in sim.Simulation.Loads:
            if load.Name.casefold() == name.casefold():
                raise NXToolError("NX_SIM_NAME_CONFLICT", "A load with that name exists")
            if load.PropertyTable.DescriptorNeutralName not in (
                "Heat Load",
                "Heat Flux",
                "Heat Generation",
            ):
                continue
            for index in range(load.TargetSetManager.TargetSetCount):
                _, members = load.TargetSetManager.GetTargetSetMembers(index)
                if any(
                    m is not None and m.Obj is not None and int(m.Obj.Tag) in tags for m in members
                ):
                    raise NXToolError(
                        "NX_SIM_DUPLICATE_HEAT_SOURCE",
                        "A target already has a heat source; inspect existing assignments",
                    )
        from nx_mcp.simcenter.heat_overlap import inspect_heat_overlap

        if overlap_policy not in ("reject", "allow_additive"):
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "overlap_policy must be reject or allow_additive"
            )
        overlaps = inspect_heat_overlap(sim, targets)
        if overlaps and overlap_policy == "reject":
            raise NXToolError(
                "NX_SIM_OVERLAPPING_HEAT_SOURCE",
                "A face/body heat source overlaps this assignment",
                details={
                    "overlaps": overlaps,
                    "next_step": "Inspect existing sources; use allow_additive only for intentionally separate heat contributions",
                },
            )
        unit = sim.UnitCollection.FindObject(unit_name)
        if unit.Symbol != symbol:
            raise NXToolError(
                "NX_SIM_UNIT_MISMATCH", "Native heat-density unit differs from required SI unit"
            )
        power = measure_applied_power(sim, targets, kind, value)
        require_solver_idle()
        before = authoring_snapshot(sim)
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP distributed heat")
    builder = None
    try:
        builder = sim.Simulation.CreateBcBuilderForLoadDescriptor(descriptor, name)
        expression = sim.Expressions.CreateSystemNumberExpression(str(value), unit)
        wrapper = sim.FieldManager.CreateScalarFieldWrapperWithExpression(expression)
        builder.PropertyTable.SetScalarFieldWrapperPropertyValue(descriptor, wrapper)
        members = []
        for target in targets:
            member = cae.SetObject()
            member.Obj, member.SubType, member.SubId = target, cae.CaeSetObjectSubType.NotSet, 0
            members.append(member)
        builder.TargetSetManager.SetTargetSetMembers(0, members)
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
        properties = read_properties(load.PropertyTable, nx)
        actual = next(p for p in properties if p["name"] == descriptor)
        _, committed = load.TargetSetManager.GetTargetSetMembers(0)
        if (
            float(actual["expression"]) != value
            or actual["unit_symbol"] != symbol
            or sorted(int(m.Obj.Tag) for m in committed) != sorted(tags)
            or load.GetStringUserAttribute("NX_MCP_PROVENANCE", -1) != provenance
        ):
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH",
                "Heat density, unit, selection or provenance changed during commit",
            )
        return {
            "load": load,
            "kind": kind,
            "value": float(actual["expression"]),
            "units": symbol,
            "target_count": len(committed),
            "properties": properties,
            "provenance": provenance,
            **power,
            "saved": False,
            "solver_launched": False,
            "duplicate_check_scope": "same target and face/body ownership; geometric intersections between distinct bodies not checked",
            "overlap_policy": overlap_policy,
            "overlaps": overlaps,
        }
    except Exception as error:
        pending, builder = builder, None
        rollback_creation(session, sim, mark, pending, before, error)
    finally:
        if builder is not None:
            builder.Destroy()
