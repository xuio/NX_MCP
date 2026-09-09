"""Native temperature-material handler creation and post-commit rollback fixture."""


def run(executor):
    import importlib
    import json
    import types
    from pathlib import Path

    from nx_mcp import hardened
    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter import native, scalar_tables, temperature_material

    importlib.reload(scalar_tables)
    importlib.reload(temperature_material)
    importlib.reload(native)
    method = types.MethodType(native.SimcenterMixin._sim_temperature_material, executor)
    executor._sim_temperature_material = method
    executor._handlers["nx_sim_temperature_material"] = method
    hardened.NON_MODEL.add("nx_sim_temperature_material")
    session = executor.session
    sim = next(p for p in session.Parts if p.FullPath.endswith("temperature_material_r1.sim"))
    fem = sim.FemPart
    fid = executor._reference(fem, "part", fem, "FEM")["id"]
    sid = executor._reference(sim, "part", sim, "SIM")["id"]
    executor._sim_activate(fid)
    before = temperature_material.snapshot(fem)
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    original = temperature_material.verify
    reached = []

    def fail(*args):
        reached.append(True)
        raise NXToolError(
            "NX_SIM_READBACK_MISMATCH", "Injected temperature material post-commit failure"
        )

    args = {
        "document": fid,
        "name": "MCP_NATIVE_TEMP",
        "conductivity_samples": [[273.15, 100], [293.15, 150], [313.15, 200]],
        "heat_capacity_samples": [[273.15, 800], [293.15, 900], [313.15, 1000]],
        "density_kg_m3": 2700,
        "provenance": "Generic native temperature material fixture",
    }
    try:
        temperature_material.verify = fail
        try:
            executor._sim_temperature_material(**args)
        except NXToolError as error:
            assert error.details["mutation_outcome"] == "rolled_back", error.details
            recovery = {"code": error.code, "details": error.details}
        else:
            raise AssertionError("Expected injected failure")
    finally:
        temperature_material.verify = original
    assert reached == [True]
    assert temperature_material.snapshot(fem) == before
    assert flags == {p.FullPath: bool(p.IsModified) for p in session.Parts}
    created = executor._sim_temperature_material(**args)
    executor._sim_save(fid)
    executor._sim_activate(sid)
    result = {
        "created": created,
        "rollback": recovery,
        "snapshot_restored": True,
        "flags_restored": True,
        "document": fid,
        "path": fem.FullPath,
        "solver_launched": False,
    }
    Path(
        r"Z:\nx-mcp-integration\simcenter-discovery\temperature-material-handler-native.json"
    ).write_text(json.dumps(result, indent=2))
    return result
