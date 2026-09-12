"""Explicit documented NX Multiphysics flow selectors; no numerical acceptance."""

from nx_mcp.runtime import NXToolError

MODELS = {
    "laminar": 0,
    "mixing_length": 2,
    "standard_k_epsilon": 3,
    "rng_k_epsilon": 4,
    "realizable_k_epsilon": 5,
    "k_omega": 6,
    "sst": 7,
    "spalart_allmaras": 8,
}
WALLS = {"no_slip": 0, "slip": 1, "wall_function": 2, "hybrid_wall_function": 3}


def configure_model(session, sim, *, model, wall_treatment=None):
    import NXOpen as nx

    if (
        not isinstance(model, str)
        or model not in MODELS
        or (
            wall_treatment is not None
            and (not isinstance(wall_treatment, str) or wall_treatment not in WALLS)
        )
    ):
        raise NXToolError("NX_INVALID_ARGUMENT", "Unsupported flow or wall selector")
    if session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected SIM first")
    solution = sim.Simulation.ActiveSolution
    if (
        solution is None
        or solution.SolverType != "NX MULTIPHYSICS"
        or solution.AnalysisType not in ("Flow", "Coupled Thermal-Flow")
    ):
        raise NXToolError(
            "NX_SIM_SOLUTION_TYPE", "Requires NX MULTIPHYSICS Flow or Coupled Thermal-Flow"
        )
    table = solution.PropertyTable
    surface = table.GetNamedPropertyTablePropertyValue("Flow Surface Parameters")
    if surface is None:
        raise NXToolError("NX_SIM_CONFIGURATION_MISSING", "Attach Flow Surface Parameters first")
    wall = surface.PropertyTable
    active = wall.GetBooleanPropertyValue("Non-fluid 2D and 3D Elements Block Flow")
    if wall_treatment is not None and not active:
        raise NXToolError(
            "NX_SIM_UNSUPPORTED_CONFIGURATION",
            "Global wall treatment is inactive while solid flow blockage is disabled",
        )

    def read():
        return {
            "turbulence_model": table.GetIntegerPropertyValue("Turbulence Model"),
            "global_wall_treatment": wall.GetIntegerPropertyValue("Wall Treatment"),
        }

    before = read()
    requested = {
        "turbulence_model": MODELS[model],
        "global_wall_treatment": before["global_wall_treatment"]
        if wall_treatment is None
        else WALLS[wall_treatment],
    }
    if model == "laminar" and active and requested["global_wall_treatment"] not in (0, 1):
        raise NXToolError(
            "NX_SIM_UNSUPPORTED_CONFIGURATION",
            "Laminar flow requires an explicit supported no-slip or slip wall; wall-function configurations are unverified",
        )
    changed = before != requested
    result = {
        "before": before,
        "actual": requested,
        "changed": changed,
        "model": model,
        "global_wall_change_requested": wall_treatment is not None,
        "saved": False,
        "prior_results_require_revalidation": changed,
        "wall_overrides": "not_inspected",
        "global_wall_treatment_active": active,
        "near_wall_resolution": "not_verified",
        "solve_readiness": "not_established",
        "solver_launched": False,
    }
    if not changed:
        return result
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP flow model selectors")
    try:
        table.SetIntegerPropertyValue("Turbulence Model", MODELS[model])
        if wall_treatment is not None:
            wall.SetIntegerPropertyValue("Wall Treatment", WALLS[wall_treatment])
        if session.UpdateManager.DoUpdate(mark):
            raise NXToolError("NX_SIM_UPDATE_FAILED", "Native flow model update reported errors")
        actual = read()
        if actual != requested:
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Flow model selectors differ after assignment"
            )
        result["actual"] = actual
        return result
    except Exception as error:
        try:
            session.UndoToMark(mark, None)
            if read() != before:
                raise RuntimeError("Flow selectors differ after rollback")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError(
                "NX_SIM_ROLLBACK_FAILED",
                "Flow model mutation failed with incomplete rollback",
                details={
                    "operation_error": str(error),
                    "recovery_error": str(recovery),
                    "mutation_outcome": "partial",
                },
            ) from error
        raise
