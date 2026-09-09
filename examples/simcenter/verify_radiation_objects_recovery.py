"""Native creation rollback and geometric association audit for radiation objects."""


def run(executor):
    import json
    from pathlib import Path

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter import radiation_objects
    from nx_mcp.simcenter.selections import face_inventory

    session = executor.session
    sim = session.Parts.BaseWork
    assert sim.FullPath.endswith("enclosure_r1.sim")
    faces = face_inventory(session, sim)["rows"]
    bounds = {int(row["face"].Tag): row["bounds"] for row in faces}
    initial = json.loads(
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\radiation-objects-native.json").read_text()
    )
    expected = sorted(
        json.dumps(row["bounds"], sort_keys=True) for row in initial["faces"]["faces"]
    )
    associations = []
    for name in ["MCP_EMISSIVITY", "MCP_ENCLOSURE"]:
        obj = next(b for b in sim.Simulation.SimulationObjects if b.Name == name)
        _, members = obj.TargetSetManager.GetTargetSetMembers(0)
        actual = sorted(json.dumps(bounds[int(m.Obj.Tag)], sort_keys=True) for m in members)
        assert actual == expected
        associations.append(
            {"name": name, "face_bounds_preserved": True, "face_count": len(members)}
        )

    def snapshot():
        return {
            "objects": sorted(int(o.Tag) for o in sim.Simulation.SimulationObjects),
            "expressions": sorted(int(e.Tag) for e in sim.Expressions),
            "membership": sorted(int(b.Tag) for b in sim.Simulation.ActiveSolution.GetBcs()),
            "flags": {p.FullPath: bool(p.IsModified) for p in session.Parts},
        }

    original = radiation_objects.verify

    def fail(*args):
        raise NXToolError(
            "NX_SIM_READBACK_MISMATCH", "Injected post-commit failure for native recovery test"
        )

    outcomes = []
    try:
        radiation_objects.verify = fail
        for options in [
            {"kind": "emissivity", "emissivity": 0.8},
            {"kind": "enclosure", "include_environment": True},
        ]:
            before = snapshot()
            try:
                radiation_objects.create(
                    session,
                    sim,
                    [r["face"] for r in faces],
                    "MCP_RECOVERY_PROBE",
                    "Failure injection",
                    **options,
                )
            except NXToolError as error:
                assert error.details["mutation_outcome"] == "rolled_back", error.details
                outcomes.append(
                    {"kind": options["kind"], "code": error.code, "details": error.details}
                )
            else:
                raise AssertionError("Expected injected failure")
            assert snapshot() == before
    finally:
        radiation_objects.verify = original
    session.ListingWindow.CloseWindow()
    sim.ModelingViews.WorkView.Fit()
    sim.ModelingViews.WorkView.UpdateDisplay()
    return {
        "associations": associations,
        "injected_failures": outcomes,
        "native_rollback_verified": True,
        "document_flags_preserved": True,
        "solver_launched": False,
    }
