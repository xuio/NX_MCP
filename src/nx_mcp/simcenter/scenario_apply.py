"""Creation-only transaction for a preflighted internal-heat scenario."""

import json
import math

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.heat_loads import create_body_power
from nx_mcp.simcenter.recovery import authoring_snapshot, rollback_creation


def _preflight_error(code, message):
    return NXToolError(code, message, details={"mutation_outcome": "not_started"})


def apply_scenario(session, sim, plan, targets):
    import NXOpen as nx

    solution = sim.Simulation.ActiveSolution
    if (
        session.Parts.BaseWork != sim
        or solution is None
        or solution.SolverType != "NX MULTIPHYSICS"
        or solution.AnalysisType != "Thermal"
    ):
        raise _preflight_error("NX_SIM_SOLUTION_TYPE", "Activate an NX MULTIPHYSICS Thermal SIM")
    # Creation-only import deliberately does not infer whether an existing load
    # participates in this scenario or represents a nested power subtotal.
    if list(sim.Simulation.Loads):
        raise _preflight_error(
            "NX_SIM_SCENARIO_CONFLICT",
            "Scenario import requires an empty load collection; use an isolated analysis copy with no loads",
        )
    assignments = plan["assignments"]
    if not assignments or len(assignments) != len(targets):
        raise _preflight_error(
            "NX_SIM_SCENARIO_INVALID",
            "Provide at least one internal heat source and every resolved target",
        )
    if len({int(t.Tag) for t in targets}) != len(targets) or any(
        t.OwningPart != sim for t in targets
    ):
        raise _preflight_error(
            "NX_SIM_SELECTION_OWNER",
            "Scenario targets must be distinct body occurrences in this SIM",
        )
    names = [a["source"].casefold() for a in assignments]
    if len(set(names)) != len(names):
        raise _preflight_error(
            "NX_SIM_NAME_CONFLICT", "Heat load names must be case-insensitively unique"
        )
    provenance = [
        json.dumps(
            {
                "scenario_sha256": plan["scenario_sha256"],
                "workload_revision": plan["workload_revision"],
                "accounting_id": a["accounting_id"],
                **a["provenance"],
            },
            sort_keys=True,
        )
        for a in assignments
    ]
    if any(len(p) > 4096 for p in provenance):
        raise _preflight_error(
            "NX_SIM_SCENARIO_INVALID", "Per-source provenance exceeds 4096 characters"
        )
    before = authoring_snapshot(sim)
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP heat scenario")
    results = []
    try:
        for assignment, target, source in zip(assignments, targets, provenance, strict=True):
            result = create_body_power(
                session, sim, target, assignment["power_W"], assignment["source"], source
            )
            if result["power_w"] != assignment["power_W"] or result["target_count"] != 1:
                raise NXToolError("NX_SIM_READBACK_MISMATCH", "Scenario source readback differs")
            results.append(result)
        total = math.fsum(r["power_w"] for r in results)
        if not math.isclose(total, plan["totals_W"]["internal_heat"], rel_tol=1e-12, abs_tol=1e-12):
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Committed scenario total differs")
        return {
            "loads": results,
            "applied_internal_heat_W": total,
            "applied_to_nx": True,
            "scenario_sha256": plan["scenario_sha256"],
            "source_sha256": plan["source_sha256"],
            "preview_sha256": plan["preview_sha256"],
            "totals_W": plan["totals_W"],
            "excluded_sources": plan["excluded_sources"],
            "ambient_K": plan["ambient_K"],
            "ambient_applied": False,
            "saved": False,
            "solver_launched": False,
            "results_require_revalidation": True,
        }
    except Exception as error:
        rollback_creation(session, sim, mark, None, before, error)
