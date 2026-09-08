"""Recover only the verified unmodified partial SIM using saved dependency paths."""


def run(executor):
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    s = executor.session
    path = executor.workspace.resolve(
        "ui-benchmarks/orthotropic-solve-20260908-r1/orthotropic_solve_r1.sim"
    )
    matches = [p for p in s.Parts if executor.workspace.resolve(p.FullPath) == path]
    assert len(matches) == 1 and not matches[0].IsModified
    assert not any(p.FullPath.endswith("OrthotropicR1_mesh.fem") for p in s.Parts)
    before = {p.FullPath: bool(p.IsModified) for p in s.Parts if p != matches[0]}
    preference = s.Parts.LoadOptions.ComponentLoadMethod
    closed = executor._sim_close(executor._reference(matches[0], "part", matches[0], "part")["id"])
    opened = executor._sim_open(str(path))
    sim = s.Parts.BaseWork
    assert sim.FemPart is not None and sim.FemPart.IsFullyLoaded
    assert sim.FemPart.FullPath.endswith(
        r"orthotropic-conduction-20260908-r1\OrthotropicR1_mesh.fem"
    )
    assert s.Parts.LoadOptions.ComponentLoadMethod == preference
    assert all(
        {p.FullPath: bool(p.IsModified) for p in s.Parts}.get(path) == flag
        for path, flag in before.items()
    )
    return {
        "closed_partial": closed,
        "opened": opened,
        "fem_path": sim.FemPart.FullPath,
        "load_preference_restored": True,
        "unrelated_flags_preserved": True,
    }
