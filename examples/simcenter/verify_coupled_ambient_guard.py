"""Verify retained override state and the ambient mismatch guard, without solving."""


def run(executor):
    import importlib
    import time

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if "E-environment-override-20260908-r1" not in sim.FullPath:
        raise ValueError("Unexpected work SIM; inspect session before running")
    table = sim.Simulation.ActiveSolution.PropertyTable
    value, unit = table.GetScalarWithDataPropertyValue("Fluid Temperature")
    retained = {"path": sim.FullPath, "ambient_value": value, "ambient_units": unit.Name}
    assert value == 20 and unit.Name == "Celsius"
    root = executor.workspace.resolve("ui-benchmarks/E-ambient-guard-20260908-r1")
    if root.exists():
        raise ValueError("Inspect retained guard evidence; do not repeat")
    sid = executor._reference(sim, "part", sim, "SIM")["id"]
    copied = executor._sim_save_as(sid, str(root / "coupled_ambient_guard_r1.sim"))
    for name in ("coupled_input", "input_export", "preparation"):
        importlib.reload(importlib.import_module("nx_mcp.simcenter." + name))
    from nx_mcp.simcenter.input_export import export_flow_input

    started = time.monotonic()
    try:
        export_flow_input(executor.session, executor.workspace, sim)
    except NXToolError as error:
        if error.code != "NX_SIM_EXPORT_FAILED":
            raise
        check = error.details.get("coupled_ambient_validation")
        assert check and not check["matches"]
        assert check["native_value"] == 20 and check["exported_value"] == 0
        return {
            "retained_copy_readback": retained,
            "copy": copied,
            "guard_verified": True,
            "error_code": error.code,
            "details": error.details,
            "native_export_and_validation_seconds": time.monotonic() - started,
            "solver_launched": False,
            "numerical_acceptance": False,
        }
    raise AssertionError("Mismatched coupled input was incorrectly accepted")
