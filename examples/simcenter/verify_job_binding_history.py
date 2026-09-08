"""Read-only history/process inspection of an existing isolated solver job."""


def run(executor):
    import importlib

    from nx_mcp.simcenter import job_processes, jobs

    importlib.reload(jobs)
    importlib.reload(job_processes)
    store = jobs.JobStore(executor.workspace, "ui-benchmarks/F-input-export-20260908-r2/jobs")
    before_flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    job = store.inspect("isolated-flow-01")
    if job["state"] == "unknown":
        raise ValueError("Existing job history cannot be verified")
    assert job["process_binding_revision"] is not None
    assert job["process_binding_evidence"]
    observed = job_processes.observe_job_processes(job)
    assert observed["state"] == "observed"
    after = store.inspect("isolated-flow-01")
    assert job == after
    assert {p.FullPath: bool(p.IsModified) for p in executor.session.Parts} == before_flags
    return {
        "job_id": job["job_id"],
        "job_revision": job["revision"],
        "binding_revision": job["process_binding_revision"],
        "observations": observed,
        "job_unchanged": True,
        "document_flags_preserved": True,
        "scope": "Existing real solver identities read from verified history; no relaunch or job transition",
        "solver_success": "not_established_by_this_check",
    }
