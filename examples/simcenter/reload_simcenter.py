"""Development-only reload hook, called on the existing interactive NX thread.

Deploy source files first. Registers the whole opt-in surface so tools cannot be
advertised by a new sidecar while absent from an older live executor. Does not
restart NX, load/save documents or launch solvers.
"""


def run(executor):
    import importlib
    import types

    import nx_mcp.hardened as hardened
    import nx_mcp.simcenter.native as native
    import nx_mcp.simcenter.server as server

    # Reload dependencies before consumers. Replacing only native.py leaves
    # previously imported parser functions alive in this long-running NX UI.
    for name in (
        "scenario_import",
        "postviews",
        "flow_results",
        "flow_audit",
        "log_reader",
        "solver_guard",
        "fan_field",
        "fan_boundary",
        "time_controls",
        "release_evidence",
        "capabilities",
        "descriptors",
        "documents",
        "benchmark_geometry",
        "solver_log",
        "solver_manifest",
        "input_export",
        "prepared_input",
        "preparation",
        "launch",
        "launch_gate",
        "native_launch",
        "job_observer",
        "observer_worker",
        "process_identity",
        "job_processes",
        "properties",
        "recovery",
        "boundaries",
        "heat_loads",
        "scenario_apply",
    ):
        importlib.reload(importlib.import_module("nx_mcp.simcenter." + name))
    importlib.reload(server)
    importlib.reload(native)
    bindings = {}
    for name in server.READ_ONLY | server.NON_MODEL:
        method = "_" + name[3:]
        bindings[name] = (
            method,
            types.MethodType(getattr(native.SimcenterMixin, method), executor),
        )
    # Resolve every callable before changing the live dispatch table.
    hardened.READ_ONLY.update(server.READ_ONLY)
    hardened.NON_MODEL.update(server.NON_MODEL)
    for name, (method, bound) in bindings.items():
        setattr(executor, method, bound)
        executor._handlers[name] = bound
    return {"registered": sorted(bindings), "count": len(bindings)}
