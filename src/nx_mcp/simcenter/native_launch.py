"""Versioned native background launch for a previously prepared isolated job.

API return is not solver completion. No automatic retry, process termination,
licence changes, or numerical acceptance is performed here.
"""

import hashlib

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.dependencies import inspect_direct
from nx_mcp.simcenter.jobs import JobStore
from nx_mcp.simcenter.launch import launch_once
from nx_mcp.simcenter.launch_gate import claim_launch_gate
from nx_mcp.simcenter.log_reader import owned_output
from nx_mcp.simcenter.prepared_input import validate_prepared_input
from nx_mcp.simcenter.solver_guard import require_solver_idle
from nx_mcp.simcenter.solver_manifest import preserve_input
from nx_mcp.simcenter.thermal_state import capture_analysis_thermal_state, require_thermal_state


def launch_prepared(session, workspace, sim, job_id, job_folder="simcenter-jobs"):
    import NXOpen.CAE as cae

    store = JobStore(workspace, job_folder)
    current = store.inspect(job_id)
    manifest = current.get("manifest", {})
    if current["state"] == "unknown" or manifest.get("preparation_adapter") != 1:
        raise NXToolError(
            "NX_SIM_JOB_CONFLICT", "Inspect the incomplete job or prepare a new isolated job"
        )
    if not isinstance(sim, cae.SimPart) or workspace.resolve(sim.FullPath) != workspace.resolve(
        manifest["analysis_path"]
    ):
        raise NXToolError("NX_SIM_JOB_CONFLICT", "Selected SIM does not own this prepared job")
    # A prior intent always wins, even after unsaved changes or solution switches.
    if current["state"] != "accepted":
        return _response(current, True)
    if session.Parts.BaseWork != sim or session.Parts.BaseDisplay != sim:
        raise NXToolError(
            "NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate and display the prepared SIM before launching"
        )
    solution = sim.Simulation.ActiveSolution
    if solution is None or any(
        getattr(solution, attr) != manifest[key]
        for attr, key in (
            ("Name", "solution"),
            ("SolverType", "solver"),
            ("AnalysisType", "analysis_type"),
        )
    ):
        raise NXToolError(
            "NX_SIM_SOLUTION_CHANGED", "Select the exact prepared solution or prepare a new job"
        )
    if solution.SolverType != "NX MULTIPHYSICS" or solution.AnalysisType not in (
        "Thermal",
        "Flow",
        "Coupled Thermal-Flow",
    ):
        raise NXToolError(
            "NX_SIM_UNSUPPORTED",
            "Native background launch supports prepared Thermal, Flow or Coupled Thermal-Flow solutions",
        )
    if sum(s.Name == solution.Name for s in sim.Simulation.Solutions) != 1:
        raise NXToolError("NX_SIM_SOLUTION_AMBIGUOUS", "Prepared solution name is no longer unique")
    _, directory = owned_output(store, job_id)
    if directory != workspace.resolve(sim.FullPath).parent:
        raise NXToolError(
            "NX_SIM_OUTPUT_CONFLICT", "Prepared output directory differs from native SIM location"
        )
    require_solver_idle()
    dependencies = inspect_direct(session, sim, workspace)
    if dependencies["unresolved"]:
        raise NXToolError(
            "NX_SIM_DEPENDENCIES_UNRESOLVED", "Resolve dependencies and prepare a new job"
        )
    rows = [{k: v for k, v in row.items() if k != "part"} for row in dependencies["rows"]]
    if "live_thermal_state" in manifest:
        require_thermal_state(manifest["live_thermal_state"], capture_analysis_thermal_state(sim))
    validation = validate_prepared_input(workspace, manifest["prepared_input"], rows)
    # Read supported property before committing launch intent. API absence must
    # reject without reserving an ambiguous launch or changing the model.
    foreground = solution.PropertyTable.GetBooleanPropertyValue("Foreground")
    with workspace.resolve(manifest["prepared_input"]["input"]["path"]).open("rb") as stream:
        raw = stream.read(64 * 1024 * 1024 + 1)
    if hashlib.sha256(raw).hexdigest() != validation["input"]["sha256"]:
        raise NXToolError(
            "NX_SIM_INPUT_CHANGED", "Input changed during launch preflight; inspect before recovery"
        )
    preserve_input(store._directory(job_id), "before-launch", raw)

    def invoke():
        try:
            solution.PropertyTable.SetBooleanPropertyValue("Foreground", False)
            if solution.PropertyTable.GetBooleanPropertyValue("Foreground"):
                raise ValueError("Native background mode did not commit")
            solution.Solve(
                cae.SimSolutionSolveOption.Solve,
                cae.SimSolutionSetupCheckOption.CompleteCheckAndOutputErrors,
            )
        finally:
            solution.PropertyTable.SetBooleanPropertyValue("Foreground", foreground)
        restored = solution.PropertyTable.GetBooleanPropertyValue("Foreground") == foreground
        if not restored:
            raise ValueError("Foreground setting restoration failed after native launch")
        return {
            "background_requested": True,
            "foreground_setting_restored": True,
            "prepared_inputs_validated": True,
            "native_may_regenerate_input": True,
            "executed_input_identity": "not_yet_audited",
        }

    claim_launch_gate(store, job_id)
    result = launch_once(store, job_id, manifest, invoke)
    return _response(result, result["replayed"])


def _response(current, replayed):
    return {
        "job_id": current["job_id"],
        "state": current["state"],
        "revision": current["revision"],
        "request_sha256": current["request_sha256"],
        "replayed": replayed,
        "solver_state": "not_observed_by_launch",
        "numerical_convergence": "not_established",
        "results_validated": False,
        "cancellation": "not_implemented",
        "next_step": "Inspect nx_sim_job_status and nx_sim_job_logs; API return is not solver completion",
    }
