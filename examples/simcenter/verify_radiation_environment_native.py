"""Create a small reusable radiation fixture; test environment modes under rollback."""


def run(executor):
    import importlib
    import json
    import types
    from pathlib import Path

    from nx_mcp.simcenter import native, radiation
    from nx_mcp.simcenter.selections import face_inventory
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    importlib.reload(radiation)
    importlib.reload(native)
    method = types.MethodType(native.SimcenterMixin._sim_environment_radiation, executor)
    executor._sim_environment_radiation = method
    executor._handlers["nx_sim_environment_radiation"] = method
    from nx_mcp import hardened

    hardened.NON_MODEL.add("nx_sim_environment_radiation")
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    fixture = executor._sim_create_benchmark(
        "ui-benchmarks/R-environment-radiation-20260909-r1",
        length_mm=10,
        width_mm=10,
        height_mm=10,
    )
    session = executor.session
    sim = session.Parts.BaseWork
    sid = executor._reference(sim, "part", sim, "SIM")["id"]
    fem = sim.FemPart
    fid = executor._reference(fem, "part", fem, "FEM")["id"]
    mesh = executor._sim_mesh(fid, 5.0)
    executor._sim_material(
        fid,
        "MCP_RADIATION_SOLID",
        200.0,
        2700.0,
        900.0,
        "Generic API fixture; assumed aluminium",
        True,
    )
    executor._sim_save(fid)
    executor._sim_activate(sid)
    faces = [r["face"] for r in face_inventory(session, sim)["rows"]]
    assert len(faces) == 6
    trials = []
    for source, temperature in [
        ("fluid_ambient", None),
        ("radiative_ambient", None),
        ("specified", 293.15),
    ]:
        mark = session.SetUndoMark(
            executor.nxopen.Session.MarkVisibility.Invisible, "Radiation environment trial"
        )
        try:
            result = radiation.create_environment(
                session,
                sim,
                [faces[0]],
                0.8,
                "MCP_RADIATION_TRIAL",
                "Assumed effective emissivity; radiation API verification",
                source,
                temperature,
            )
            result.pop("boundary")
            trials.append(result)
        finally:
            session.UndoToMark(mark, None)
            session.DeleteUndoMark(mark, None)
    assert not list(sim.Simulation.Constraints)
    executor._sim_save(sid)
    current = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    assert all(current[p] == v for p, v in flags.items())
    result = {
        "fixture": fixture,
        "document": sid,
        "path": sim.FullPath,
        "mesh": mesh,
        "trials": trials,
        "rollback_verified": True,
        "unrelated_modified_flags_preserved": True,
        "faces": executor._sim_faces(sid),
        "solver_launched": False,
    }
    sim.ModelingViews.WorkView.Fit()
    sim.ModelingViews.WorkView.UpdateDisplay()
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\radiation-environment-native.json").write_text(
        json.dumps(result, indent=2)
    )
    return result
