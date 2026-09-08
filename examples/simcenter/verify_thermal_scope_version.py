"""Native capture and old-scope rejection; no solver launch or model mutation."""


def run(executor):
    import importlib
    import json
    import sys
    from pathlib import Path

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    importlib.reload(importlib.import_module("nx_mcp.simcenter.properties"))
    importlib.reload(importlib.import_module("nx_mcp.simcenter.boundary_state"))
    module = importlib.reload(importlib.import_module("nx_mcp.simcenter.thermal_state"))
    refreshed = []
    for name in ("nx_mcp.simcenter.preparation", "nx_mcp.simcenter.native_launch"):
        consumer = sys.modules.get(name)
        if consumer is not None:
            consumer.capture_analysis_thermal_state = module.capture_analysis_thermal_state
            refreshed.append(name)
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    path = executor.workspace.resolve(
        "ui-benchmarks/volume-numerical-solve-20260908-r1/volume_solve_r1.sim"
    )
    executor._sim_open(str(path))
    sim = executor.session.Parts.BaseWork
    state = module.capture_analysis_thermal_state(sim)
    assert state["adapter"] == 3
    assert state["boundary_scope"].endswith("_v4")
    if not state["sha256"]:
        return {
            "passed": False,
            "state": state,
            "solver_launched": False,
            "limitation": "Native fixture cannot establish a complete scoped snapshot",
        }
    old = {**state, "adapter": 2}
    old.pop("boundary_scope")
    try:
        module.require_thermal_state(old, state)
    except NXToolError as error:
        assert error.details["comparison"]["reason"] == "live_thermal_state_scope_mismatch"
        rejected = error.details
    else:
        raise AssertionError("Old scope was accepted")
    assert module.require_thermal_state(state, state)["state"] == "matches"
    after = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    assert all(after.get(path) == value for path, value in flags.items())
    result = {
        "passed": True,
        "refreshed_consumers": refreshed,
        "state": state,
        "old_scope_rejection": rejected,
        "unrelated_modified_flags_preserved": True,
        "solver_launched": False,
    }
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\thermal-scope-version.json").write_text(
        json.dumps(result, indent=2)
    )
    return result
