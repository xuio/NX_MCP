"""Cancel unlaunched durable reservations; never terminate or signal processes."""

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.jobs import JobStore


def cancel_unlaunched(workspace, job_id, expected_revision, job_folder="simcenter-jobs"):
    if type(expected_revision) is not int or not 0 <= expected_revision <= 9998:
        raise NXToolError("NX_INVALID_ARGUMENT", "expected_revision must be an integer in 0..9998")
    store = JobStore(workspace, job_folder)
    current = store.inspect(job_id)
    evidence = current.get("record", {}).get("evidence", {})
    if current["state"] == "cancelled" and evidence.get("cancellation_scope") == "before_launch":
        if current["revision"] not in (expected_revision, expected_revision + 1):
            raise NXToolError(
                "NX_SIM_JOB_REVISION_CONFLICT", "Reinspect the cancelled job revision"
            )
        replayed = True
    else:
        if current["state"] != "accepted":
            raise NXToolError(
                "NX_SIM_CANCELLATION_UNAVAILABLE",
                "Only accepted, unlaunched jobs can be cancelled. Running native solver cancellation is unverified; inspect job status and the native monitor.",
                details={"state": current["state"], "mutation_outcome": "not_started"},
            )
        current = store.transition(
            job_id,
            expected_revision=expected_revision,
            state="cancelled",
            evidence={"cancellation_scope": "before_launch", "solver_launched": False},
        )
        replayed = False
    return {
        "job_id": job_id,
        "state": current["state"],
        "revision": current["revision"],
        "request_sha256": current["request_sha256"],
        "replayed": replayed,
        "cancellation_scope": "before_launch",
        "solver_stop_requested": False,
        "files_deleted": False,
        "launch_retry_allowed": False,
    }
