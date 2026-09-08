"""One-time native guard verification and failure recording for the retained diagnostic.

The exact old request hash is intentional: do not apply this recovery to another job.
"""

def run(executor):
    import hashlib
    import importlib
    from pathlib import Path

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    modules = {}
    for name in ("coupled_input", "input_export", "preparation"):
        m = importlib.reload(importlib.import_module("nx_mcp.simcenter." + name))
        modules[name] = hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()
    from nx_mcp.simcenter.input_export import export_flow_input
    from nx_mcp.simcenter.jobs import JobStore

    s = executor.session
    sim = s.Parts.BaseWork
    if "E-finned-pressure-20260908-r1" not in sim.FullPath:
        raise ValueError("Expected retained, never-launched specified-pressure diagnostic")
    store = JobStore(executor.workspace)
    job = store.inspect("coupled-finned-pressure-r1")
    if (
        job["state"] != "accepted"
        or job["request_sha256"]
        != "2ad76bb922a3d168bb50d7d5bfb495710d1c46c5765cc5e4793ea2d7a1d1517f"
    ):
        raise ValueError("Inspect unexpected diagnostic job state")
    failed = store.transition(
        "coupled-finned-pressure-r1",
        expected_revision=job["revision"],
        state="failed",
        evidence={
            "reason": "Verified active specified pressure native 101325 Pa versus exported 0 Pa",
            "solver_launched": False,
            "retained_input_sha256": "9a8f318500beed70bdd9699b16bfb70cce18df2ba7c50162b2688e917d1f857e",
        },
    )
    rows = {
        "deployed_sha256": modules,
        "old_diagnostic_job_state": failed["state"],
        "solver_launched": False,
    }
    for name, folder in [
        ("specified", "E-finned-pressure-guard-20260908-r1"),
        ("altitude", "E-finned-altitude-guard-20260908-r1"),
    ]:
        if name == "altitude":
            candidates = [
                p
                for p in s.Parts
                if "E-finned-layer-reopen-export-20260908-r1" in p.FullPath
                and p.FullPath.endswith(".sim")
            ]
            if len(candidates) != 1:
                raise ValueError("Expected retained altitude reference SIM")
            sim = candidates[0]
            _, status = s.Parts.SetDisplay(sim, False, False)
            if status:
                status.Dispose()
            s.Parts.SetWork(sim)
        root = executor.workspace.resolve("ui-benchmarks/" + folder)
        if root.exists():
            raise ValueError("Do not replay existing export guard check")
        executor._sim_save_as(
            executor._reference(sim, "part", sim, "SIM")["id"], str(root / (name + "_guard_r1.sim"))
        )
        try:
            value = export_flow_input(s, executor.workspace, sim)
        except NXToolError as e:
            if name != "specified":
                raise
            if (
                e.code != "NX_SIM_EXPORT_FAILED"
                or not e.details["coupled_ambient_validation"]["matches"]
                or e.details["coupled_pressure_validation"]["matches"]
            ):
                raise
            rows[name] = {
                "export_succeeded": False,
                "expected_error": e.code,
                "details": e.details,
                "guard_rejection_verified": True,
            }
        else:
            if name != "altitude":
                raise ValueError("Specified-pressure mismatch was incorrectly accepted")
            if (
                not value["coupled_pressure_validation"]["matches"]
                or value["coupled_pressure_validation"]["stored_absolute_pressure_active"]
            ):
                raise ValueError("Altitude selector interpretation differs")
            rows[name] = value
    return rows
