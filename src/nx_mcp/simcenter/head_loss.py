"""Internal native boundary head-loss authoring; no assumed solver conventions."""

import math

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.properties import read_properties


def require_manual_dynamic_pressure(table):
    """Manual K is active only for the documented Specify/dynamic-pressure mode."""
    if table.DescriptorType != "Head Loss":
        raise NXToolError(
            "NX_SIM_HEAD_LOSS_MODE",
            "Expected a Head Loss descriptor",
            details={"mutation_outcome": "not_started"},
        )
    props = table.PropertyTable
    selectors = {key: props.GetIntegerPropertyValue(key) for key in ("Type", "Proportional to")}
    if selectors != {"Type": 0, "Proportional to": 0}:
        raise NXToolError(
            "NX_SIM_HEAD_LOSS_MODE",
            "Manual coefficient requires Type=Specify and Proportional to=Dynamic Pressure; inspect the active resistance model before editing",
            details={"selectors": selectors, "mutation_outcome": "not_started"},
        )
    return selectors


def attach_head_loss(session, sim, boundary, name, coefficient):
    import NXOpen as nx
    import NXOpen.CAE as cae

    if type(coefficient) not in (int, float) or not math.isfinite(coefficient) or coefficient < 0:
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Head-loss coefficient must be finite and nonnegative"
        )
    if not isinstance(name, str) or not name.strip():
        raise NXToolError("NX_INVALID_ARGUMENT", "Supply a head-loss table name")
    if not isinstance(sim, cae.SimPart) or session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected SIM")
    if boundary.OwningPart != sim or boundary not in list(sim.Simulation.SimulationObjects):
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Select a boundary owned by this SIM")
    sol = sim.Simulation.ActiveSolution
    if sol is None or sol.SolverType != "NX MULTIPHYSICS" or sol.AnalysisType != "Flow":
        raise NXToolError(
            "NX_SIM_SOLUTION_TYPE", "Head-loss adapter requires the tested Flow solution"
        )
    owner = boundary.PropertyTable
    if owner.GetNamedPropertyTablePropertyValue("Head Loss") is not None:
        raise NXToolError(
            "NX_SIM_TABLE_EXISTS", "Boundary already has head loss; inspect before replacing"
        )
    collection = sim.ModelingObjectPropertyTables
    before = {int(t.Tag) for t in collection}
    if any(t.Name.casefold() == name.casefold() for t in collection):
        raise NXToolError("NX_SIM_NAME_CONFLICT", "Head-loss table name already exists")
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP boundary head loss")
    try:
        table = collection.CreateModelingObjectPropertyTable(
            "Head Loss", "NX MULTIPHYSICS - Flow", "NX MULTIPHYSICS", name, 0
        )
        props = table.PropertyTable
        props.SetIntegerPropertyValue("Type", 0)
        props.SetIntegerPropertyValue("Proportional to", 0)
        require_manual_dynamic_pressure(table)
        _, unit = props.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient")
        props.SetBaseScalarWithDataPropertyValue("Head Loss Coefficient", float(coefficient), unit)
        owner.SetNamedPropertyTablePropertyValue("Head Loss", table)
        value, actual_unit = props.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient")
        if (
            value != coefficient
            or actual_unit != unit
            or owner.GetNamedPropertyTablePropertyValue("Head Loss") != table
        ):
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Head-loss coefficient or association differs"
            )
        return {
            "table": table,
            "boundary_name": boundary.Name,
            "properties": read_properties(props, nx),
            "coefficient": value,
            "units": actual_unit.Name if actual_unit else "dimensionless",
            "convention": "not_independently_verified",
            "saved": False,
            "results_require_revalidation": True,
        }
    except Exception as error:
        try:
            session.UndoToMark(mark, None)
            if {
                int(t.Tag) for t in collection
            } != before or owner.GetNamedPropertyTablePropertyValue("Head Loss") is not None:
                raise RuntimeError("Head-loss state differs after rollback")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError(
                "NX_SIM_ROLLBACK_FAILED",
                "Head-loss authoring failed with incomplete rollback",
                details={
                    "operation_error": str(error),
                    "recovery_error": str(recovery),
                    "mutation_outcome": "partial",
                },
            ) from error
        raise


def set_opening_head_loss(
    session, sim, boundary, coefficient, expected_coefficient=None, name=None
):
    """Create or compare-and-set an opening's native dimensionless resistance."""
    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    values = [coefficient] + ([expected_coefficient] if expected_coefficient is not None else [])
    for value in values:
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "Coefficients must be finite nonnegative numbers"
            )
    if not isinstance(sim, cae.SimPart) or session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected SIM")
    solution = sim.Simulation.ActiveSolution
    if (
        solution is None
        or solution.SolverType != "NX MULTIPHYSICS"
        or solution.AnalysisType != "Flow"
    ):
        raise NXToolError("NX_SIM_SOLUTION_TYPE", "Select NX MULTIPHYSICS Flow")
    if (
        boundary.OwningPart != sim
        or boundary not in list(sim.Simulation.SimulationObjects)
        or boundary.DescriptorName != "Opening"
    ):
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Select an Opening owned by this SIM")
    table = boundary.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss")
    if table is None:
        if expected_coefficient is not None or not isinstance(name, str) or not name.strip():
            raise NXToolError(
                "NX_INVALID_ARGUMENT",
                "Creating head loss requires name and no expected_coefficient",
            )
        require_solver_idle()
        created = attach_head_loss(session, sim, boundary, name, coefficient)
        table = created.pop("table")
        return {
            **created,
            "table_name": table.Name,
            "previous_coefficient": None,
            "changed": True,
            "action": "created",
        }
    if name is not None:
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "name applies only when creating a table; omit it for updates"
        )
    if expected_coefficient is None:
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Updating requires expected_coefficient from prior readback"
        )
    selectors = require_manual_dynamic_pressure(table)
    props = table.PropertyTable
    old, unit = props.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient")
    if old != expected_coefficient:
        raise NXToolError(
            "NX_SIM_VALUE_CONFLICT",
            "Head loss differs from the expected value; inspect and retry deliberately",
            details={"actual_coefficient": old, "mutation_outcome": "not_started"},
        )
    require_solver_idle()
    if old != coefficient:
        mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP opening head loss")
        try:
            props.SetBaseScalarWithDataPropertyValue(
                "Head Loss Coefficient", float(coefficient), unit
            )
            require_manual_dynamic_pressure(table)
            actual, actual_unit = props.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient")
            if (
                actual != coefficient
                or actual_unit != unit
                or boundary.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss") != table
            ):
                raise NXToolError(
                    "NX_SIM_READBACK_MISMATCH", "Head-loss update differs from request"
                )
        except Exception as error:
            try:
                session.UndoToMark(mark, None)
                if (
                    props.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient") != (old, unit)
                    or boundary.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss")
                    != table
                ):
                    raise RuntimeError("Head loss differs after rollback")
                session.DeleteUndoMark(mark, None)
            except Exception as recovery:
                raise NXToolError(
                    "NX_SIM_ROLLBACK_FAILED",
                    "Head-loss recovery is incomplete",
                    details={"mutation_outcome": "partial"},
                ) from recovery
            raise NXToolError(
                "NX_SIM_HEAD_LOSS_FAILED",
                "Head-loss edit failed and was rolled back",
                details={
                    "mutation_outcome": "rolled_back",
                    "cause_code": getattr(error, "code", None),
                },
            ) from error
    return {
        "table_name": table.Name,
        "boundary_name": boundary.Name,
        "coefficient": coefficient,
        "previous_coefficient": old,
        "selectors": selectors,
        "units": unit.Name if unit else "dimensionless",
        "convention": "native Head Loss coefficient; general pressure-loss convention not independently verified",
        "changed": old != coefficient,
        "action": "updated" if old != coefficient else "unchanged",
        "properties": read_properties(props, nx),
        "saved": False,
        "results_require_revalidation": old != coefficient,
    }
