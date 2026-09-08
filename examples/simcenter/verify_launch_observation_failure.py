"""Host persistence fault injection only: deliberately launches no solver."""


def run(executor):
    import importlib

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter import launch
    from nx_mcp.simcenter.jobs import JobStore

    importlib.reload(launch)
    folder = "ui-benchmarks/F-launch-observation-20260908-r1/jobs"
    if executor.workspace.resolve(folder).exists():
        raise ValueError("Fixture exists; inspect the reserved job instead of rerunning")
    store = JobStore(executor.workspace, folder)
    original_transition = store.transition
    calls = []

    def fail_observation(*args, **kwargs):
        if kwargs["state"] == "launch_returned":
            raise OSError("Injected observation persistence failure")
        return original_transition(*args, **kwargs)

    def callback():
        calls.append(1)
        return {"synthetic_callback": True, "solver_launched": False}

    store.transition = fail_observation
    manifest = {"purpose": "fault injection only; no native solver", "solver_launched": False}
    try:
        launch.launch_once(store, "observation-failure", manifest, callback)
    except NXToolError as error:
        assert error.code == "NX_SIM_LAUNCH_UNCERTAIN"
        details = error.details
    else:
        raise AssertionError("Storage failure was not reported")
    restored = JobStore(executor.workspace, folder)
    replay = launch.launch_once(restored, "observation-failure", manifest, callback)
    assert calls == [1] and replay["replayed"] and replay["state"] == "launch_requested"
    return {
        "scope": "Windows durable job replay after injected observation write failure",
        "error": details,
        "callback_count": len(calls),
        "replayed": True,
        "persisted_state": restored.inspect("observation-failure")["state"],
        "solver_launched": False,
        "actual_solver_interruption_tested": False,
        "job_folder": folder,
    }
