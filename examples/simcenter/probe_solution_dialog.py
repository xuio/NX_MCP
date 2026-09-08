"""Record one native solution dialog invocation; never rerun a pending intent."""


def run(executor):
    import json
    from pathlib import Path

    import NXOpen as nx

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    record = Path(r"Z:\nx-mcp-integration\simcenter-discovery\solution-dialog-invocation-r1.json")
    if record.exists():
        raise ValueError(
            "Invocation intent exists; inspect its state and live UI rather than retrying"
        )
    executor._sim_open(
        r"D:\CAD\SIMCENTER_MCP_WORKSPACE\ui-benchmarks\E-coupled-mcp-20260908-r1\benchmark_d1e2b031a3dd_analysis.sim"
    )
    before = [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts]
    session = executor.session
    journal = session.JournalManager
    if journal.IsJournalRecording:
        raise ValueError("Preserve the existing journal recording")
    base = executor.workspace.resolve("ui-benchmarks/coupled-solution-dialog-r1")
    if list(base.parent.glob(base.name + "*")):
        raise ValueError("Journal destination already exists")
    ui = nx.UI.GetUI()
    button = ui.MenuBarManager.GetButtonFromName("UG_SFEM_INSERT_SOLUTION")
    result = {
        "state": "accepted",
        "command": "UG_SFEM_INSERT_SOLUTION",
        "journal_path_base": str(base),
        "model_path": session.Parts.BaseWork.FullPath,
        "solver_launched": False,
    }
    with record.open("x") as stream:
        json.dump(result, stream)
    journal.RecordJournal(str(base))
    try:
        result["state"] = "invoke_requested"
        record.write_text(json.dumps(result, indent=2))
        ui.DialogTester.InvokeMenuButtonAction(button)
        result["state"] = "invoke_returned"
    except Exception as error:
        result.update(
            state="invoke_failed",
            nx_code=getattr(error, "ErrorCode", None),
            error_type=type(error).__name__,
            message=str(error),
        )
    finally:
        if journal.IsJournalRecording:
            journal.StopRecordingJournal()
        result["document_flags_preserved"] = before == [
            (p.FullPath, bool(p.IsModified)) for p in session.Parts
        ]
        record.write_text(json.dumps(result, indent=2))
    return result
