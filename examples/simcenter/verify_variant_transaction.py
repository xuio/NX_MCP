"""One isolated saved-file transaction, followed by receipt-only replay."""


def run(executor):
    from nx_mcp.simcenter.dependencies import inspect_direct
    from nx_mcp.simcenter.variant_clone import execute_clone_plan
    from nx_mcp.simcenter.variant_plan import plan_variant

    session = executor.session
    before = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    work, display = session.Parts.BaseWork, session.Parts.BaseDisplay
    assert work.FullPath.endswith("refined_flow_r1.sim")
    plan = plan_variant(
        executor.workspace,
        inspect_direct(session, work, executor.workspace),
        folder="ui-benchmarks/variant-transaction-20260908-r1",
        name="VariantTxnR1",
        loaded_paths=list(before),
        saved_snapshot=True,
    )
    created = execute_clone_plan(session, executor.workspace, plan)
    replayed = execute_clone_plan(session, executor.workspace, plan)
    assert not created["replayed"] and replayed["replayed"]
    assert created["outputs"] == replayed["outputs"]
    assert before == {p.FullPath: bool(p.IsModified) for p in session.Parts}
    assert session.Parts.BaseWork == work and session.Parts.BaseDisplay == display
    return {
        "plan": plan,
        "created": created,
        "replayed": replayed,
        "work_display_preserved": True,
        "document_flags_preserved": True,
    }
