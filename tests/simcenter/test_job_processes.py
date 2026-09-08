from nx_mcp.simcenter import job_processes


def test_missing_recorded_process_does_not_mutate_job(monkeypatch):
    identity = {"pid": 123, "creation_filetime_100ns": "10000", "executable_path": r"C:\solver.exe"}
    job = {
        "state": "running",
        "record": {"evidence": {"process_observations": [{"identity": identity}]}},
    }
    monkeypatch.setattr(
        job_processes, "inspect_process", lambda pid: {"pid": pid, "state": "missing"}
    )
    result = job_processes.observe_job_processes(job)
    assert result["processes"][0]["correlation"]["state"] == "original_process_not_present"
    assert job["state"] == "running" and not result["job_state_changed"]


def test_reused_pid_is_not_reported_as_the_solver(monkeypatch):
    identity = {"pid": 123, "creation_filetime_100ns": "10000", "executable_path": r"C:\solver.exe"}
    job = {
        "record": {
            "evidence": {
                "previous_processes": [{"identity": identity}],
                "process_observations": [{"pid": 123, "state": "missing"}],
            }
        }
    }
    monkeypatch.setattr(
        job_processes,
        "inspect_process",
        lambda pid: {
            "pid": pid,
            "state": "running",
            "identity": {**identity, "creation_filetime_100ns": "20000"},
        },
    )
    result = job_processes.observe_job_processes(job)
    assert result["processes"][0]["correlation"]["state"] == "identity_mismatch"


def test_bare_pids_or_ambiguous_bindings_are_not_queried(monkeypatch):
    def unexpected(pid):
        raise AssertionError("Incomplete binding must not query a process")

    monkeypatch.setattr(job_processes, "inspect_process", unexpected)
    for rows in ([], [{"pid": 1}], [{"identity": None}]):
        result = job_processes.observe_job_processes(
            {"record": {"evidence": {"process_observations": rows}}}
        )
        assert result["state"] == "unbound"


def test_reconnect_retains_binding_across_later_unrelated_evidence(tmp_path, monkeypatch):
    from nx_mcp.simcenter.jobs import JobStore
    from nx_mcp.workspace import Workspace

    identity = {"pid": 123, "creation_filetime_100ns": "10000", "executable_path": r"C:\solver.exe"}
    store = JobStore(Workspace(tmp_path))
    store.reserve("history", {"input": "fixture"})
    store.transition(
        "history", expected_revision=0, state="launch_requested", evidence={"intent": True}
    )
    store.transition(
        "history",
        expected_revision=1,
        state="running",
        evidence={"process_observations": [{"identity": identity}]},
    )
    store.transition(
        "history", expected_revision=2, state="solver_exited", evidence={"log_footer": True}
    )
    job = JobStore(store.workspace).inspect("history")
    assert job["process_binding_revision"] == 2
    assert "process_observations" not in job["record"]["evidence"]
    monkeypatch.setattr(
        job_processes, "inspect_process", lambda pid: {"pid": pid, "state": "missing"}
    )
    observed = job_processes.observe_job_processes(job)
    assert observed["processes"][0]["recorded_identity"] == identity
    assert not job["results_validated"] and not observed["job_state_changed"]
    store.transition(
        "history",
        expected_revision=3,
        state="failed",
        evidence={"process_observations": [{"pid": 123}]},
    )
    job = JobStore(store.workspace).inspect("history")
    assert job["process_binding_revision"] == 4
    assert job_processes.observe_job_processes(job)["state"] == "unbound"
