"""Verify stale prepared-state rejection after the isolated native solve."""


def run(executor):
    import importlib

    from nx_mcp.simcenter import prepared_input
    from nx_mcp.simcenter.dependencies import inspect_direct
    from nx_mcp.simcenter.jobs import JobStore

    importlib.reload(prepared_input)
    store = JobStore(executor.workspace, "ui-benchmarks/F-input-export-20260908-r2/jobs")
    job = store.inspect("isolated-flow-01")
    if job["state"] != "solver_exited":
        raise ValueError("Reconcile the isolated solve before this read-only fixture")
    dependencies = inspect_direct(
        executor.session, executor.session.Parts.BaseWork, executor.workspace
    )
    rows = [{k: v for k, v in row.items() if k != "part"} for row in dependencies["rows"]]
    try:
        prepared_input.validate_prepared_input(
            executor.workspace, job["manifest"]["prepared_input"], rows
        )
    except prepared_input.NXToolError as error:
        if error.code != "NX_SIM_REVISION_CHANGED":
            raise
        return {
            "rejected": True,
            "code": error.code,
            "details": error.details,
            "solver_launched": False,
            "scope": "Native post-solve unsaved SIM flag rejection, not intentional geometry-change acceptance",
        }
    raise ValueError("Expected the observed post-solve unsaved SIM state to invalidate preparation")
