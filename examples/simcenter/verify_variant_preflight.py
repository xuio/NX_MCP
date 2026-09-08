"""Run the new read-only clone preflight against the current native analysis."""


def run(executor):
    import runpy
    from pathlib import Path

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.dependencies import inspect_direct

    plan_variant = runpy.run_path(str(Path(__file__).with_name("variant_plan.py")))["plan_variant"]
    session = executor.session
    sim = session.Parts.BaseWork
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    dependencies = inspect_direct(session, sim, executor.workspace)
    args = {
        "folder": "ui-benchmarks/variant-api-preflight-20260908-r1",
        "name": "VariantApiR1",
        "loaded_paths": list(flags),
    }
    try:
        default = plan_variant(executor.workspace, dependencies, **args)
        default_status = {"state": "planned", "plan_sha256": default["plan_sha256"]}
    except NXToolError as error:
        if error.code != "NX_SIM_UNSAVED_DOCUMENT":
            raise
        default_status = {"state": "rejected", "code": error.code, "details": error.details}
    result = plan_variant(executor.workspace, dependencies, **args, saved_snapshot=True)
    assert not executor.workspace.resolve(args["folder"]).exists()
    assert flags == {p.FullPath: bool(p.IsModified) for p in session.Parts}
    return {
        "default_preflight": default_status,
        "saved_snapshot_plan": result,
        "destination_created": False,
        "document_flags_preserved": True,
    }
