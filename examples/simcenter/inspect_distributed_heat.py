"""Inspect exact installed thermal constraint descriptors without committing."""


def run(executor):
    import NXOpen.UF

    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    s = executor.session
    old_work, old_display = s.Parts.BaseWork, s.Parts.BaseDisplay
    targets = [
        p
        for p in s.Parts
        if p.FullPath.endswith(r"B-contact-context-20260908-r2\contact_context_r2.sim")
    ]
    if len(targets) != 1:
        raise ValueError("Expected loaded isolated thermal source")
    target = targets[0]
    ref = executor._reference(target, "part", target, "part")["id"]
    rows = []
    try:
        executor._sim_activate(ref)
        copied = {"new_copy_created": False, "isolated_existing_copy": target.FullPath}
        sim = s.Parts.BaseWork
        uf = NXOpen.UF.UFSession.GetUFSession()
        sol = sim.Simulation.ActiveSolution
        context = {
            "path": sim.FullPath,
            "solver": sol.SolverType,
            "solver_display": sol.GetDisplayNameOfSolverType(),
            "analysis": sol.AnalysisType,
            "solution": sol.Name,
            "current_language": int(uf.Sfl.AskCurLanguageNx()),
            "solution_language": int(uf.Sf.SolutionAskLanguageNx(sol.Tag)),
        }
        before = [(p.FullPath, bool(p.IsModified)) for p in s.Parts]
        objects = [int(x.Tag) for x in sim.Simulation.SimulationObjects]
        for descriptor in (
            "Heat Flux",
            "Heat Generation",
        ):
            mark = s.SetUndoMark(
                executor.nxopen.Session.MarkVisibility.Visible, "Contact descriptor context probe"
            )
            builder = None
            try:
                builder = sim.Simulation.CreateBcBuilderForLoadDescriptor(
                    descriptor, "MCP_CONTACT_CONTEXT_PROBE"
                )
                rows.append(
                    {
                        "descriptor": descriptor,
                        "accepted": True,
                        "neutral": builder.PropertyTable.DescriptorNeutralName,
                        "properties": read_properties(builder.PropertyTable, executor.nxopen),
                        "target_sets": builder.TargetSetManager.TargetSetCount,
                        "committed": False,
                    }
                )
            except Exception as error:
                rows.append(
                    {
                        "descriptor": descriptor,
                        "accepted": False,
                        "nx_code": getattr(error, "ErrorCode", None),
                        "error": str(error),
                    }
                )
            finally:
                if builder is not None:
                    builder.Destroy()
                s.UndoToMark(mark, None)
                s.DeleteUndoMark(mark, None)
            if objects != [int(x.Tag) for x in sim.Simulation.SimulationObjects]:
                raise ValueError("Probe rollback changed simulation object set")
        assert before == [(p.FullPath, bool(p.IsModified)) for p in s.Parts]
        return {"context": context, "copied": copied, "probes": rows, "rollback_verified": True}
    finally:
        if old_display is not None:
            _, status = s.Parts.SetDisplay(old_display, False, False)
            if status is not None:
                status.Dispose()
        if old_work is not None:
            s.Parts.SetWork(old_work)
