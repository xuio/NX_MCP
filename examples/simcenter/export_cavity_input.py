def run(executor):
    import datetime
    import json
    from pathlib import Path

    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.runtime import NXToolError

    session = executor.session
    sim = session.Parts.BaseWork
    if not isinstance(sim, cae.SimPart):
        raise ValueError("SIM must be active")
    root = Path(sim.FullPath).parent
    if root.name != "D-cavity-documents-20260908-r2" or "SIMCENTER_MCP_WORKSPACE" not in str(root):
        raise ValueError("Probe requires isolated UI benchmark")
    record = root / "cavity-input-export-02.json"
    if record.exists():
        previous = json.loads(record.read_text())
        if previous.get("state") == "failed":
            raise NXToolError(
                "NX_SIM_EXPORT_FAILED",
                previous.get("error", "Export failed"),
                details={"job": previous, "replayed": True},
            )
        return {"job": previous, "replayed": True}
    data = {
        "job_id": "cavity-input-export-02",
        "state": "accepted",
        "solver_launched": False,
        "sim": str(sim.FullPath),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    with record.open("x") as f:
        json.dump(data, f)

    def persist():
        tmp = record.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(record)

    try:
        for part in session.Parts:
            if Path(part.FullPath).parent == root:
                status = part.Save(
                    nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue
                )
                status.Dispose()
        sol = sim.Simulation.ActiveSolution
        data["state"] = "exporting"
        persist()
        data["api"] = "SimSolution.Solve / WriteSolverInputFile"
        persist()
        sol.Solve(
            cae.SimSolutionSolveOption.WriteSolverInputFile,
            cae.SimSolutionSetupCheckOption.CompleteCheckAndOutputErrors,
        )
        data["state"] = "export_returned"
        data["files"] = [
            {"name": p.name, "size": p.stat().st_size} for p in root.iterdir() if p.is_file()
        ]
    except Exception as exc:
        data.update(state="failed", error=str(exc), nx_code=getattr(exc, "ErrorCode", None))
        raise NXToolError(
            "NX_SIM_EXPORT_FAILED", "Native cavity input export failed", details={"job": data}
        ) from exc
    finally:
        persist()
    return {"job": data}
