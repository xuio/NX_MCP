"""Native Flow / Thermal-Flow configuration on the NX UI thread."""

from nx_mcp.runtime import NXToolError


def create_initial_step(session, sim, name):
    """Create the first native flow step and inspect its actual defaults.

    Does not assign fluid regions, boundaries, parameter tables, or mesh. Solver
    defaults are read back without inventing meanings for undocumented enums.
    """
    import NXOpen as nx
    import NXOpen.UF as uf

    from nx_mcp.simcenter.properties import read_properties

    if session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected SIM first")
    if not isinstance(name, str) or not name.strip():
        raise NXToolError("NX_INVALID_ARGUMENT", "Provide a nonempty step name")
    sol = sim.Simulation.ActiveSolution
    if (
        sol is None
        or sol.SolverType != "NX MULTIPHYSICS"
        or sol.AnalysisType not in ("Flow", "Coupled Thermal-Flow")
    ):
        raise NXToolError(
            "NX_SIM_SOLUTION_TYPE",
            "Select an NX MULTIPHYSICS Flow or Coupled Thermal-Flow solution",
        )
    if sol.StepCount != 0:
        raise NXToolError(
            "NX_SIM_STEP_EXISTS",
            "Inspect existing steps; this operation creates only the first step",
        )
    native = uf.UFSession.GetUFSession()
    desc = native.Sf.SolutionAskDescriptorNx(sol.Tag)
    allowed = [
        native.Sfl.StepDescriptorAskNameNx(
            native.Sfl.SolutionAskNthAllowableStepDescriptorNx(desc, i)
        )
        for i in range(sol.AllowedStepTypeCount)
    ]
    expected = "Step - Flow" if sol.AnalysisType == "Flow" else "Step - Thermal Flow"
    if allowed.count(expected) != 1:
        raise NXToolError(
            "NX_SIM_STEP_UNAVAILABLE", "Installed solution has no unique expected flow step"
        )
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP initial flow step")
    try:
        step = sol.CreateStep(allowed.index(expected), True, name)
        if sol.StepCount != 1 or sol.ActiveStep != step or sol.GetStepByIndex(0) != step:
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Native flow step creation readback differs"
            )
        return {
            "name": step.Name,
            "descriptor": expected,
            "active": True,
            "properties": read_properties(step.PropertyTable, nx),
            "saved": False,
            "solve_ready": False,
            "defaults_basis": "installed native defaults; solver interpretation not yet verified",
        }
    except Exception as error:
        try:
            session.UndoToMark(mark, None)
            if sol.StepCount != 0:
                raise RuntimeError("Step remains after rollback")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError(
                "NX_SIM_ROLLBACK_FAILED",
                "Flow step creation failed and rollback was incomplete",
                details={
                    "operation_error": str(error),
                    "recovery_error": str(recovery),
                    "mutation_outcome": "partial",
                },
            ) from error
        raise


def attach_default_tables(session, sim, name_prefix):
    """Attach verified Flow/coupled tables without replacing existing settings.

    Defaults are reported verbatim; attaching tables does not validate a flow
    domain or boundary conditions and never establishes solver readiness.
    """
    import NXOpen as nx

    from nx_mcp.simcenter.properties import read_properties

    if session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected SIM first")
    sol = sim.Simulation.ActiveSolution
    if (
        sol is None
        or sol.SolverType != "NX MULTIPHYSICS"
        or sol.AnalysisType not in ("Flow", "Coupled Thermal-Flow")
    ):
        raise NXToolError(
            "NX_SIM_SOLUTION_TYPE",
            "Select an NX MULTIPHYSICS Flow or Coupled Thermal-Flow solution",
        )
    if not isinstance(name_prefix, str) or not name_prefix.strip():
        raise NXToolError("NX_INVALID_ARGUMENT", "Provide a nonempty table name prefix")
    keys = (
        ("Flow Solution Parameters", "Flow Surface Parameters", "Flow Output Requests")
        if sol.AnalysisType == "Flow"
        else (
            "Thermal Parameters",
            "Flow Solution Parameters",
            "Flow Surface Parameters",
            "Thermal-Flow Output Requests",
            "Coupled Solution Parameters",
        )
    )
    for key in keys:
        if sol.PropertyTable.GetNamedPropertyTablePropertyValue(key) is not None:
            raise NXToolError(
                "NX_SIM_TABLE_EXISTS",
                "Inspect existing flow settings; automatic replacement is not allowed",
            )
    names = [name_prefix + " " + key for key in keys]
    if any(table.Name in names for table in sim.ModelingObjectPropertyTables):
        raise NXToolError("NX_SIM_NAME_CONFLICT", "Flow table names must be unique")
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP flow parameter tables")
    try:
        rows = []
        for key, name in zip(keys, names, strict=True):
            descriptor = (
                "Thermal-Flow Coupled Solution Parameters"
                if key == "Coupled Solution Parameters"
                else key
            )
            table = sim.ModelingObjectPropertyTables.CreateModelingObjectPropertyTable(
                descriptor, "NX MULTIPHYSICS - " + sol.AnalysisType, "NX MULTIPHYSICS", name, 0
            )
            sol.PropertyTable.SetNamedPropertyTablePropertyValue(key, table)
            actual = sol.PropertyTable.GetNamedPropertyTablePropertyValue(key)
            if actual != table or actual.DescriptorType != descriptor:
                raise NXToolError(
                    "NX_SIM_READBACK_MISMATCH", "Flow table association differs from request"
                )
            rows.append(
                {
                    "property": key,
                    "name": actual.Name,
                    "descriptor": actual.DescriptorType,
                    "properties": read_properties(actual.PropertyTable, nx),
                }
            )
        return {
            "tables": rows,
            "saved": False,
            "solve_ready": False,
            "defaults_basis": "installed native table defaults, not numerical acceptance",
            "unresolved_controls": [],
        }
    except Exception as error:
        try:
            session.UndoToMark(mark, None)
            if any(
                sol.PropertyTable.GetNamedPropertyTablePropertyValue(k) is not None for k in keys
            ):
                raise RuntimeError("Flow table association remains after rollback")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError(
                "NX_SIM_ROLLBACK_FAILED",
                "Flow table setup failed and rollback was incomplete",
                details={
                    "operation_error": str(error),
                    "recovery_error": str(recovery),
                    "mutation_outcome": "partial",
                },
            ) from error
        raise


def configure_laminar_no_slip(session, sim):
    """Apply the v2606 Flow selectors verified in native solver comparisons.

    Does not certify mesh adequacy or numerical results. A changed configuration
    invalidates prior results for engineering use; it is left unsaved.
    """
    import NXOpen as nx

    if session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected SIM first")
    sol = sim.Simulation.ActiveSolution
    if sol is None or sol.SolverType != "NX MULTIPHYSICS" or sol.AnalysisType != "Flow":
        raise NXToolError("NX_SIM_SOLUTION_TYPE", "Requires NX MULTIPHYSICS Flow")
    surface = sol.PropertyTable.GetNamedPropertyTablePropertyValue("Flow Surface Parameters")
    if surface is None:
        raise NXToolError("NX_SIM_CONFIGURATION_MISSING", "Attach the Flow parameter tables first")
    entries = [(sol.PropertyTable, "Turbulence Model"), (surface.PropertyTable, "Wall Treatment")]
    before = [table.GetIntegerPropertyValue(key) for table, key in entries]
    changes = [
        {"property": key, "before": value, "after": 0}
        for (_, key), value in zip(entries, before, strict=True)
        if value != 0
    ]
    result = {
        "flow_model": "laminar",
        "wall_treatment": "no_slip",
        "native_values": {"Turbulence Model": 0, "Wall Treatment": 0},
        "changes": changes,
        "changed": bool(changes),
        "solve_ready": False,
        "saved": False,
        "prior_results_require_revalidation": bool(changes),
    }
    if not changes:
        return result
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP laminar no-slip flow")
    try:
        for table, key in entries:
            table.SetIntegerPropertyValue(key, 0)
        if any(table.GetIntegerPropertyValue(key) != 0 for table, key in entries):
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Flow settings differ after assignment")
        return result
    except Exception as error:
        try:
            session.UndoToMark(mark, None)
            if [table.GetIntegerPropertyValue(key) for table, key in entries] != before:
                raise RuntimeError("Flow settings differ after rollback")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError(
                "NX_SIM_ROLLBACK_FAILED",
                "Flow configuration failed with incomplete recovery",
                details={
                    "operation_error": str(error),
                    "recovery_error": str(recovery),
                    "mutation_outcome": "partial",
                },
            ) from error
        raise


def configure_coupled_steady(session, sim, name):
    """Set the sole coupled step to native steady type 0; no solve or save."""
    import NXOpen as nx

    solution = sim.Simulation.ActiveSolution
    if session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected SIM first")
    if (
        solution is None
        or solution.SolverType != "NX MULTIPHYSICS"
        or solution.AnalysisType != "Coupled Thermal-Flow"
    ):
        raise NXToolError(
            "NX_SIM_SOLUTION_TYPE", "Select an NX MULTIPHYSICS Coupled Thermal-Flow solution"
        )
    if solution.StepCount != 1 or solution.ActiveStep != solution.GetStepByIndex(0):
        raise NXToolError("NX_SIM_STEP_PRECONDITION", "Requires exactly one active coupled step")
    table = solution.ActiveStep.PropertyTable
    before = table.GetIntegerPropertyValue("Solution Type")
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP coupled steady step")
    try:
        table.SetIntegerPropertyValue("Solution Type", 0)
        actual = table.GetIntegerPropertyValue("Solution Type")
        if actual != 0:
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Coupled step type differs from steady request"
            )
        return {
            "step": solution.ActiveStep.Name,
            "solution_type": "steady",
            "native_value": actual,
            "previous_native_value": before,
            "saved": False,
            "solve_ready": False,
            "name_semantics": "existing step name retained",
        }
    except Exception as error:
        try:
            session.UndoToMark(mark, None)
            if table.GetIntegerPropertyValue("Solution Type") != before:
                raise RuntimeError("Step type differs after rollback")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError(
                "NX_SIM_ROLLBACK_FAILED",
                "Coupled step rollback failed",
                details={
                    "mutation_outcome": "partial",
                    "operation_error": str(error),
                    "recovery_error": str(recovery),
                },
            ) from error
        raise
