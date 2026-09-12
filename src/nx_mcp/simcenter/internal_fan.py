"""Native Internal Fan inspection; authoring and numerical acceptance remain separate."""

from nx_mcp.runtime import NXToolError


def snapshot(sim):
    return {
        "objects": sorted(int(x.Tag) for x in sim.Simulation.SimulationObjects),
        "expressions": sorted(int(x.Tag) for x in sim.Expressions),
        "fields": sorted(int(x.Tag) for x in sim.FieldManager.Fields),
        "solution_bcs": sorted(int(x.Tag) for x in sim.Simulation.ActiveSolution.GetBcs()),
        "modified": bool(sim.IsModified),
    }


def inspect_schema(session, sim):
    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    if not isinstance(sim, cae.SimPart) or session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the target SIM")
    solution = sim.Simulation.ActiveSolution
    if (
        solution is None
        or solution.SolverType != "NX MULTIPHYSICS"
        or solution.AnalysisType not in ("Flow", "Coupled Thermal-Flow")
    ):
        raise NXToolError(
            "NX_SIM_SOLUTION_TYPE", "Requires NX MULTIPHYSICS Flow or Coupled Thermal-Flow"
        )
    solver_preflight = require_solver_idle()
    before = snapshot(sim)
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Invisible, "NX MCP inspect Internal Fan")
    builder = None
    error = None
    result = None
    try:
        builder = sim.Simulation.CreateBcBuilderForSimulationObjectDescriptor(
            "Internal Fan", "NX MCP uncommitted inspection"
        )
        props = builder.PropertyTable
        descriptors = []
        for i in range(props.GetPropertyCount()):
            key = props.GetPropertyNameByIndex(i)
            if "licen" in key.lower():
                continue
            try:
                value = props.GetPropertyDescriptorName(key)
                descriptors.append({"name": key, "descriptor": value})
            except Exception as exc:
                descriptors.append({"name": key, "inspection_error": str(exc)})
        result = {
            "descriptor": "Internal Fan",
            "target_set_count": builder.TargetSetManager.TargetSetCount,
            "properties": read_properties(props, nx),
            "property_descriptors": descriptors,
            "solver_preflight": solver_preflight,
            "committed_boundaries": 0,
            "selection_semantics_verified": False,
            "numerical_acceptance": False,
        }
    except Exception as exc:
        error = exc
    finally:
        cleanup_errors = []
        if builder is not None:
            try:
                builder.Destroy()
            except Exception as exc:
                cleanup_errors.append(str(exc))
        try:
            session.UndoToMark(mark, None)
            if snapshot(sim) != before:
                raise RuntimeError(
                    "SIM inventory or modified flag differs after inspection rollback"
                )
            session.DeleteUndoMark(mark, None)
        except Exception as exc:
            cleanup_errors.append(str(exc))
        if cleanup_errors:
            raise NXToolError(
                "NX_SIM_RECOVERY_INCOMPLETE",
                "Internal Fan inspection cleanup failed",
                details={"mutation_outcome": "partial", "errors": cleanup_errors},
            ) from error
    if error is not None:
        raise NXToolError(
            "NX_SIM_SCHEMA_INSPECTION_FAILED",
            str(error),
            details={"mutation_outcome": "rolled_back"},
        ) from error
    result["state_restored"] = True
    return result
