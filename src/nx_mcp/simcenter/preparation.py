"""Prepare one native export and durable job without launching a solver."""

import os

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.dependencies import inspect_direct
from nx_mcp.simcenter.input_export import export_flow_input
from nx_mcp.simcenter.jobs import JobStore
from nx_mcp.simcenter.output_claims import claim_output
from nx_mcp.simcenter.prepared_input import capture_prepared_input, validate_prepared_input
from nx_mcp.simcenter.result_identity import fingerprint_file
from nx_mcp.simcenter.revisions import audit_saved_revision
from nx_mcp.simcenter.solver_guard import require_solver_idle
from nx_mcp.simcenter.thermal_state import capture_analysis_thermal_state, require_thermal_state


def prepare_solve(
    session, workspace, sim, job_id, job_folder="simcenter-jobs", mesh_inspection_limit=200000
):
    import NXOpen.CAE as cae

    from nx_mcp.simcenter import mesh_guard

    mesh_guard.validate_budget(mesh_inspection_limit)

    if not isinstance(sim, cae.SimPart) or session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected SIM first")
    solution = sim.Simulation.ActiveSolution
    if (
        solution is None
        or solution.SolverType != "NX MULTIPHYSICS"
        or solution.AnalysisType not in ("Thermal", "Flow", "Coupled Thermal-Flow")
    ):
        raise NXToolError(
            "NX_SIM_UNSUPPORTED",
            "Preparation supports NX MULTIPHYSICS Thermal, Flow or Coupled Thermal-Flow",
        )
    if not solution.Name or sum(s.Name == solution.Name for s in sim.Simulation.Solutions) != 1:
        raise NXToolError(
            "NX_SIM_SOLUTION_AMBIGUOUS", "Use a unique, nonempty solution name before preparation"
        )
    source = workspace.resolve(sim.FullPath)
    store = JobStore(workspace, job_folder)
    directory = store._directory(job_id)
    if store.root == source.parent or source.parent in store.root.parents:
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Store job records outside the native output directory"
        )
    identity = {
        "analysis_path": str(source),
        "solution": solution.Name,
        "solver": solution.SolverType,
        "analysis_type": solution.AnalysisType,
    }

    def dependencies():
        result = inspect_direct(session, sim, workspace)
        if result["unresolved"]:
            raise NXToolError(
                "NX_SIM_DEPENDENCIES_UNRESOLVED",
                "Resolve analysis dependencies before preparation",
                details={"unresolved": result["unresolved"]},
            )
        rows = [{k: v for k, v in row.items() if k != "part"} for row in result["rows"]]
        if any(r["modified"] or not r["fully_loaded"] or r["file_state"] != "exists" for r in rows):
            raise NXToolError(
                "NX_SIM_REVISION_UNSAVED",
                "Save and fully load every direct analysis dependency first",
            )
        return result, rows

    if directory.exists():
        current = store.inspect(job_id)
        manifest = current.get("manifest", {})
        if (
            current["state"] == "unknown"
            or manifest.get("preparation_adapter") != 1
            or any(manifest.get(k) != v for k, v in identity.items())
        ):
            raise NXToolError(
                "NX_SIM_JOB_CONFLICT",
                "This job ID has a different or incomplete preparation; inspect it and use a new ID",
            )
        if current["state"] != "accepted":
            # Never re-export or reinterpret an already launched job as prepared.
            return {
                "job_id": job_id,
                "state": current["state"],
                "replayed": True,
                "preparation_revalidated": False,
                "solver_launched_by_call": False,
                "request_sha256": current["request_sha256"],
            }
        _, rows = dependencies()
        mesh_guard.verify_manifest(sim, manifest)
        if "live_thermal_state" in manifest:
            require_thermal_state(
                manifest["live_thermal_state"], capture_analysis_thermal_state(sim)
            )
        validate_prepared_input(workspace, manifest["prepared_input"], rows)
        claim = claim_output(store, job_id, source.parent)
        return _response(current, claim, True)

    require_solver_idle()
    report, rows = dependencies()
    live_mesh_state = mesh_guard.capture(sim, mesh_inspection_limit)
    mesh_guard.require(live_mesh_state, live_mesh_state)
    live_thermal_state = capture_analysis_thermal_state(sim)
    if live_thermal_state is not None:
        require_thermal_state(live_thermal_state, live_thermal_state)
    baseline, consumed = [], 0
    for row in rows:
        snapshot = fingerprint_file(
            workspace.resolve(row["path"]), maximum_bytes=1_073_741_824 - consumed
        )
        baseline.append(snapshot)
        consumed += snapshot["bytes"]
    # The exporter rejects existing output files and retains partial artifacts.
    exported = export_flow_input(session, workspace, sim)
    try:
        _, current_rows = dependencies()
        audit = audit_saved_revision(workspace, baseline, current_rows)
        if not audit["revision_matches"]:
            raise NXToolError(
                "NX_SIM_REVISION_CHANGED",
                "Dependencies changed during export",
                details={"audit": audit},
            )
        if sim.Simulation.ActiveSolution != solution:
            raise ValueError("Active solution changed during preparation")
        prepared = capture_prepared_input(workspace, exported["input_path"], current_rows)
        mesh_guard.require(live_mesh_state, mesh_guard.capture(sim, mesh_inspection_limit))
        if live_thermal_state is not None:
            require_thermal_state(live_thermal_state, capture_analysis_thermal_state(sim))
        manifest = {
            "preparation_adapter": 1,
            "live_mesh_state": live_mesh_state,
            "mesh_inspection_limit": mesh_inspection_limit,
            **identity,
            "isolated_output_directory": os.path.normcase(str(source.parent)),
            "prepared_input": prepared,
            "native_export": exported,
            "dependency_scope": report["scope"],
            "excluded_dependencies": report["excluded"],
        }
        if live_thermal_state is not None:
            manifest["live_thermal_state"] = live_thermal_state
        current = store.reserve(job_id, manifest)
        claim = claim_output(store, job_id, source.parent)
        return _response(current, claim, False)
    except Exception as error:
        raise NXToolError(
            "NX_SIM_PREPARATION_INCOMPLETE",
            "Input was exported but preparation did not complete; inspect retained files and job records before recovery",
            details={
                "job_id": job_id,
                "retained_directory": str(source.parent),
                "mutation_outcome": "partial",
                "solver_launched": False,
                "cause_code": getattr(error, "code", None),
            },
        ) from error


def _response(current, claim, replayed):
    manifest = current["manifest"]
    return {
        "job_id": current["job_id"],
        "state": current["state"],
        "request_sha256": current["request_sha256"],
        "replayed": replayed,
        "preparation_revalidated": True,
        "solver_launched_by_call": False,
        "input_path": manifest["prepared_input"]["input"]["path"],
        "input_sha256": manifest["prepared_input"]["input"]["sha256"],
        "output_claim": claim,
        "mesh_counts": manifest["native_export"]["validation"]["mesh_counts"],
        "dependency_completeness": "not_established",
        "solve_readiness": "not_established",
        "next_step": "Inspect the immutable manifest with nx_sim_job_status(include_manifest=True), then use nx_sim_launch; cancellation is not yet implemented",
    }
