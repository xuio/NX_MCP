"""Bind native result associations to a durable job without certifying physics."""

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.revisions import audit_saved_revision


def require_job_owner(workspace, job, *, path, solution, solver, analysis):
    manifest = job.get("manifest", {})
    if (
        job.get("state") == "unknown"
        or not manifest.get("analysis_path")
        or workspace.resolve(manifest["analysis_path"]) != workspace.resolve(path)
        or any(
            manifest.get(k) != v
            for k, v in (("solution", solution), ("solver", solver), ("analysis_type", analysis))
        )
    ):
        raise NXToolError(
            "NX_SIM_RESULT_JOB_MISMATCH",
            "Select the exact analysis and solution recorded by this job; copies are different analyses",
            details={"mutation_outcome": "not_started"},
        )


def audit_job_result(
    workspace, job, dependencies, result_files, *, maximum_bytes, live_thermal_state=None
):
    evidence = job.get("record", {}).get("evidence", {})
    manifest = job.get("manifest", {})
    observed = evidence.get("result")
    reasons = []
    if job.get("state") != "solver_exited" or evidence.get("observer_adapter") != 1:
        reasons.append("verified_solver_exit_evidence_missing")
    matched = False
    if observed:
        observed_path = workspace.resolve(observed["path"])
        matched = len(result_files) == 1 and all(
            workspace.resolve(row["path"]) == observed_path
            and row["sha256"] == observed.get("sha256")
            and row["bytes"] == observed.get("bytes")
            for row in result_files
        )
    if not matched:
        reasons.append("associated_result_differs_from_job_artifact")
    expected = manifest.get("prepared_input", {}).get("dependencies", [])
    if not expected or dependencies.get("unresolved"):
        revision = {"revision_matches": False, "state": "dependency_evidence_incomplete"}
    else:
        revision = audit_saved_revision(
            workspace, expected, dependencies["rows"], maximum_bytes=maximum_bytes
        )
    if not revision["revision_matches"]:
        reasons.append("current_saved_revision_not_verified_against_prepared_revision")
    from nx_mcp.simcenter.thermal_state import compare_thermal_state

    thermal = compare_thermal_state(manifest.get("live_thermal_state"), live_thermal_state)
    if manifest.get("analysis_type") == "Thermal" and thermal["state"] != "matches":
        reasons.append(thermal["reason"])
    return {
        "job_id": job["job_id"],
        "request_sha256": job.get("request_sha256"),
        "state": "association_and_supplied_revision_match" if not reasons else "not_verified",
        "associated_result_matches_observed_artifact": matched,
        "revision": revision,
        "reasons": reasons,
        "live_thermal_state": thermal,
        "model_result_freshness": "stale" if thermal["state"] == "changed" else "not_verified",
        "engineering_accepted": False,
        "scope": "Exact analysis/solution ownership, observed result artifact and supplied pre-solve file revisions; numerical validation and dependency completeness remain separate",
        "revision_note": "Native solve/save may change SIM metadata; a file mismatch does not by itself identify a physics change",
    }
