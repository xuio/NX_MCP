"""Prepare one isolated R=.5 K/W numerical job. Does not launch a solver."""


def run(executor):
    import shutil, json
    from pathlib import Path
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    root = executor.workspace.resolve("ui-benchmarks/B-contact-numerical-20260909-r1")
    root.mkdir()
    source = executor.workspace.resolve(
        "ui-benchmarks/B-contact-resistance-export-20260909-r1/contact_resistance_r1.sim"
    )
    path = root / "contact_numerical_r1.sim"
    shutil.copy2(source, path)
    opened = executor._sim_open(str(path))
    sim = executor.session.Parts.BaseWork
    sid = executor._reference(sim, "part", sim, "SIM")["id"]
    executor._sim_save(sid)
    result = executor._sim_prepare_solve(sid, "contact-resistance-r1")
    result["benchmark_document"] = sid
    result["benchmark_path"] = str(path)
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\contact-job-prepared.json").write_text(
        json.dumps(result, indent=2)
    )
    return result
