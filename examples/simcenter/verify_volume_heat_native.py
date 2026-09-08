"""Create/read/rollback distributed heat on an isolated native analysis."""


def run(executor):
    from nx_mcp.simcenter.distributed_heat import create_distributed_heat
    from nx_mcp.simcenter.recovery import authoring_snapshot
    from nx_mcp.simcenter.selections import face_inventory

    s = executor.session
    old_work, old_display = s.Parts.BaseWork, s.Parts.BaseDisplay
    executor._sim_create_benchmark(folder="ui-benchmarks/volume-heat-authoring-20260908-r1")
    sim = s.Parts.BaseWork
    before_flags = {p.FullPath: bool(p.IsModified) for p in s.Parts}
    ref = executor._reference(sim, "part", sim, "SIM")["id"]
    results = []
    try:
        executor._sim_activate(ref)
        inventory = face_inventory(s, sim)
        used = set()
        for load in sim.Simulation.Loads:
            for i in range(load.TargetSetManager.TargetSetCount):
                _, members = load.TargetSetManager.GetTargetSetMembers(i)
                used.update(int(m.Obj.Tag) for m in members if m and m.Obj)
        component = sim.ComponentAssembly.RootComponent.GetChildren()[0]
        face = component.FindOccurrence(inventory["rows"][0]["body"])
        assert face is not None and face.OwningPart == sim
        before = authoring_snapshot(sim)
        mark = s.SetUndoMark(
            executor.nxopen.Session.MarkVisibility.Visible, "MCP distributed heat acceptance"
        )
        try:
            result = create_distributed_heat(
                s,
                sim,
                [face],
                kind="volume_generation",
                value=100000.0,
                name="MCP uniform generation probe",
                provenance="assumed isolated native adapter test",
            )
            load = result.pop("load")
            result["native_load_name"] = load.Name
            try:
                create_distributed_heat(
                    s,
                    sim,
                    [face],
                    kind="volume_generation",
                    value=200000.0,
                    name="MCP duplicate generation probe",
                    provenance="duplicate test",
                )
            except Exception as error:
                assert getattr(error, "code", None) == "NX_SIM_DUPLICATE_HEAT_SOURCE", str(error)
                result["duplicate_rejected"] = True
            else:
                raise AssertionError("Duplicate load was accepted")
            results.append(result)
        finally:
            s.UndoToMark(mark, None)
            s.DeleteUndoMark(mark, None)
        assert authoring_snapshot(sim) == before
        assert before_flags == {p.FullPath: bool(p.IsModified) for p in s.Parts}
        return {"results": results, "rollback_verified": True, "numerical_acceptance": "not_tested"}
    finally:
        _, status = s.Parts.SetDisplay(old_display, False, False)
        if status is not None:
            status.Dispose()
        s.Parts.SetWork(old_work)
