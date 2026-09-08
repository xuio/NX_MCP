"""Isolated job-store contract fixtures; no real solver or prepared solve."""


def run(executor):
    import importlib
    import json
    import types
    from pathlib import Path

    from nx_mcp import hardened
    from nx_mcp.simcenter.jobs import JobStore

    native = importlib.reload(importlib.import_module("nx_mcp.simcenter.native"))
    importlib.reload(importlib.import_module("nx_mcp.simcenter.server"))
    bound = types.MethodType(native.SimcenterMixin._sim_cancel, executor)
    executor._sim_cancel = bound
    executor._handlers["nx_sim_cancel"] = bound
    hardened.NON_MODEL.add("nx_sim_cancel")
    folder = "ui-benchmarks/cancellation-contract-20260909-r1/jobs"
    store = JobStore(executor.workspace, folder)
    store.reserve("accepted", {"fixture": "unlaunched cancellation contract; no solver"})
    store.reserve("intent", {"fixture": "synthetic launch-intent record; no solver"})
    intent = store.inspect("intent")
    if intent["state"] == "accepted":
        store.transition(
            "intent",
            expected_revision=0,
            state="launch_requested",
            evidence={"fixture_only": True, "solver_launched": False},
        )
    context = {
        "job_folder": folder,
        "solver_launched": False,
        "verification_scope": "durable job-store/public MCP contract; not native solver cancellation",
    }
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\cancel-contract-context.json").write_text(
        json.dumps(context)
    )
    return context
