"""Reconcile the isolated-flow-01 fixture; never launch or cancel a solver."""


def run(executor):
    import datetime
    import json

    from nx_mcp.simcenter.dependencies import inspect_direct
    from nx_mcp.simcenter.jobs import JobStore
    from nx_mcp.simcenter.process_identity import correlate_process, inspect_process
    from nx_mcp.simcenter.result_identity import fingerprint_file
    from nx_mcp.simcenter.revisions import audit_saved_revision
    from nx_mcp.simcenter.solver_manifest import input_identity

    folder = "ui-benchmarks/F-input-export-20260908-r2"
    store = JobStore(executor.workspace, folder + "/jobs")
    job = store.inspect("isolated-flow-01")
    if job["state"] == "solver_exited":
        return {"job": job, "replayed": True}
    if job["state"] != "running":
        raise ValueError("Expected retained running observations; do not guess process identity")
    previous = job["record"]["evidence"]["process_observations"]
    observations = []
    for row in previous:
        current = inspect_process(row["pid"])
        observations.append(current)
        if current["state"] == "missing":
            continue
        correlation = correlate_process(row["identity"], current)
        if current["state"] != "exited" or correlation["state"] != "same_process_exited":
            return {"job": job, "observations": observations, "terminal_verified": False}
    root = executor.workspace.resolve(folder)
    base = "flow_input_r2-Flow_benchmark"
    log, result, deck = [root / (base + suffix) for suffix in (".log", ".bun", ".xml")]
    intent = json.loads((store._directory("isolated-flow-01") / "state-00001.json").read_text())
    started = datetime.datetime.fromisoformat(intent["observed_at"]).timestamp()
    if any(not p.is_file() or p.stat().st_mtime <= started for p in (log, result)):
        raise ValueError("Missing or stale terminal outputs")
    text = log.read_text(errors="replace")
    if "Solve completed at:" not in text or "FATAL ERROR" in text.upper():
        raise ValueError("No successful completion footer; inspect native diagnostics")
    identity = input_identity(deck.read_bytes())
    if identity["xml_content_sha256"] != job["manifest"]["input_xml_content_sha256"]:
        raise ValueError("Native launch exported different input content")
    sim = executor.session.Parts.BaseWork
    current = inspect_direct(executor.session, sim, executor.workspace)
    docs = [{k: v for k, v in row.items() if k != "part"} for row in current["rows"]]
    revision = audit_saved_revision(
        executor.workspace, job["manifest"]["prepared_input"]["dependencies"], docs
    )
    evidence = {
        "process_observations": observations,
        "previous_processes": previous,
        "completion_footer": True,
        "input": identity,
        "saved_revision_audit": revision,
        "log": fingerprint_file(log, maximum_bytes=8 * 1024 * 1024),
        "result": fingerprint_file(result, maximum_bytes=128 * 1024 * 1024),
        "scope": "fixture-specific terminal reconciliation; generic automatic binding and cancellation remain incomplete",
        "numerical_acceptance": "not_established",
    }
    return {
        "job": store.transition(
            "isolated-flow-01",
            expected_revision=job["revision"],
            state="solver_exited",
            evidence=evidence,
        )
    }
