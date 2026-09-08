"""Audit the fixed thermal fixture without launching a solver or changing its job state."""


def run(executor):
    import datetime
    import json
    from pathlib import Path

    from nx_mcp.simcenter.dependencies import inspect_direct
    from nx_mcp.simcenter.jobs import JobStore
    from nx_mcp.simcenter.result_identity import fingerprint_file
    from nx_mcp.simcenter.results import temperature_extrema
    from nx_mcp.simcenter.revisions import audit_saved_revision
    from nx_mcp.simcenter.solver_log import inspect_solver_log
    from nx_mcp.simcenter.solver_manifest import input_identity
    from nx_mcp.simcenter.thermal_balance import inspect_thermal_balances

    sim = executor.session.Parts.BaseWork
    if not sim.FullPath.endswith(r"A-thermal-export-20260908-r1\thermal_input_r1.sim"):
        raise ValueError("Wrong active analysis")
    root = Path(sim.FullPath).parent
    store = JobStore(executor.workspace, str(root / "jobs"))
    job = store.inspect("isolated-thermal-01")
    intent = json.loads((store._directory("isolated-thermal-01") / "state-00001.json").read_text())
    start = datetime.datetime.fromisoformat(intent["observed_at"]).timestamp()
    log, result, deck = [
        root / ("thermal_input_r1-Conduction" + s) for s in (".log", ".bun", ".xml")
    ]
    if any(not p.is_file() or p.stat().st_mtime <= start for p in (log, result)):
        raise ValueError("Missing or stale outputs")
    report = inspect_solver_log(log.read_text(errors="replace"))
    if report["state"] == "failed" or "Solve completed at:" not in log.read_text(errors="replace"):
        raise ValueError("No successful completion log")
    identity = input_identity(deck.read_bytes())
    if identity["xml_content_sha256"] != job["manifest"]["input_xml_content_sha256"]:
        raise ValueError("Launch input differs from audited preparation")
    temperatures = temperature_extrema(executor.session, sim)
    rise = temperatures["maximum"] - 20
    error_percent = abs(rise - 2.5) / 2.5 * 100
    current = inspect_direct(executor.session, sim, executor.workspace)
    rows = [{k: v for k, v in r.items() if k != "part"} for r in current["rows"]]
    return {
        "temperatures": temperatures,
        "rise_k": rise,
        "expected_rise_k": 2.5,
        "rise_error_percent": error_percent,
        "temperature_tolerance_percent": 1.0,
        "temperature_check_passed": error_percent <= 1 and abs(temperatures["minimum"] - 20) < 1e-6,
        "tolerance_basis": "Initial linear tetrahedron discretization check; refinement still required",
        "log_report": report,
        "thermal_balances": inspect_thermal_balances(log.read_text(errors="replace"), power_unit="mN-mm/s"),
        "input": identity,
        "result": fingerprint_file(result, maximum_bytes=128 * 1024 * 1024),
        "saved_revision_audit": audit_saved_revision(
            executor.workspace, job["manifest"]["prepared_input"]["dependencies"], rows
        ),
        "job_id": job["job_id"],
        "recorded_job_state": job["state"],
        "process_binding": "not_observed_during_this_short_solve",
        "scope": "Numerical fixture audit, not full lifecycle or convergence acceptance",
    }
