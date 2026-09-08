"""Exercise job persistence on the NX host without launching any solver.

Call twice through separate bridge clients. The second call must return the same
reserved launch intent, never create or execute a second launch.
"""


def run(executor):
    import importlib

    from nx_mcp.simcenter import jobs

    importlib.reload(jobs)
    store = jobs.JobStore(executor.workspace, "ui-benchmarks/F-job-ledger-20260908-r1")
    manifest = {"fixture": "job-persistence-only", "solver_launch_permitted": False, "schema": 1}
    reserved = store.reserve("reconnect", manifest)
    if reserved["state"] == "accepted":
        store.transition(
            "reconnect",
            expected_revision=0,
            state="launch_requested",
            evidence={"intent": "disposable launch-intent test; no solver invocation"},
        )
    current = jobs.JobStore(executor.workspace, "ui-benchmarks/F-job-ledger-20260908-r1").inspect(
        "reconnect"
    )
    if (
        current["state"] != "launch_requested"
        or current["revision"] != 1
        or current["launch_retry_allowed"]
    ):
        raise ValueError("Reconnect did not preserve the no-relaunch state")
    try:
        store.reserve("reconnect", {"fixture": "conflicting"})
    except jobs.NXToolError as error:
        if error.code != "NX_SIM_JOB_CONFLICT":
            raise
        conflict = error.code
    else:
        raise ValueError("Conflicting manifest was accepted")
    return {
        "reservation_replayed": reserved["replayed"],
        "job": current,
        "conflict": conflict,
        "solver_launched": False,
        "scope": "native host filesystem and reconnect persistence only; no solve/cancellation acceptance",
    }
