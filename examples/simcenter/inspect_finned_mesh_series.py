def run(executor):
    import json
    import runpy
    import time

    from nx_mcp.simcenter.results import temperature_extrema
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    audit = runpy.run_path(
        r"Z:\nx-mcp-integration\simcenter-discovery\inspect_finned_boundary_fields.py"
    )["run"]
    s = executor.session
    old_work, old_display = s.Parts.BaseWork, s.Parts.BaseDisplay
    output = executor.workspace.resolve("ui-benchmarks/E-finned-boundary-comparison-r1.json")
    rows = []
    started = time.monotonic()
    try:
        for key, folder in [
            ("2mm", "E-finned-tight-20260908-r1"),
            ("1mm", "E-finned-refined-run-20260908-r1"),
            ("0.5mm", "E-finned-fine-run-20260908-r1"),
        ]:
            matches = [p for p in s.Parts if folder in p.FullPath and p.FullPath.endswith(".sim")]
            assert len(matches) == 1
            sim = matches[0]
            _, status = s.Parts.SetDisplay(sim, False, False)
            if status:
                status.Dispose()
            s.Parts.SetWork(sim)
            row = {
                "mesh": key,
                "boundary_fields": audit(executor),
                "temperature": temperature_extrema(s, sim),
                "fluid_temperature": temperature_extrema(s, sim, location="element_nodal"),
            }
            rows.append(row)
            output.write_text(json.dumps(rows, indent=2))
    finally:
        _, status = s.Parts.SetDisplay(old_display, False, False)
        if status:
            status.Dispose()
        s.Parts.SetWork(old_work)
    return {
        "rows": rows,
        "elapsed_seconds": time.monotonic() - started,
        "solver_launched": False,
        "acceptance": False,
    }
