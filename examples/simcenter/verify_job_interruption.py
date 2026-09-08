"""Retain a deliberately incomplete record only in a disposable job fixture."""


def run(executor):
    import importlib

    from nx_mcp.simcenter import jobs

    importlib.reload(jobs)
    store = jobs.JobStore(executor.workspace, "ui-benchmarks/F-job-ledger-20260908-r1")
    result = store.reserve(
        "interrupted-write",
        {"fixture": "interrupted-state-record", "solver_launch_permitted": False},
    )
    directory = executor.workspace.resolve(
        "ui-benchmarks/F-job-ledger-20260908-r1/interrupted-write"
    )
    partial = executor.workspace.ensure_inside(directory / "state-00001.json")
    if result["state"] == "accepted":
        with partial.open("xb") as stream:
            stream.write(b"{")
            stream.flush()
            import os

            os.fsync(stream.fileno())
    elif result["state"] != "unknown":
        raise ValueError("Fixture already contains an unexpected state; preserve it")
    inspected = store.inspect("interrupted-write")
    replay = store.reserve(
        "interrupted-write",
        {"fixture": "interrupted-state-record", "solver_launch_permitted": False},
    )
    if (
        inspected["state"] != "unknown"
        or replay["launch_retry_allowed"]
        or partial.read_bytes() != b"{"
    ):
        raise ValueError("Incomplete record was not retained with launch prohibited")
    try:
        store.transition(
            "interrupted-write",
            expected_revision=0,
            state="launch_requested",
            evidence={"intent": "must be rejected"},
        )
    except jobs.NXToolError as error:
        if error.code != "NX_SIM_JOB_REVISION_CONFLICT":
            raise
        rejection = error.code
    else:
        raise ValueError("Incomplete job allowed a new launch intent")
    return {
        "inspection": inspected,
        "replay": replay,
        "rejection": rejection,
        "partial_record_preserved": True,
        "solver_launched": False,
        "scope": "Windows filesystem interruption fixture; no actual solver transport interruption",
    }
