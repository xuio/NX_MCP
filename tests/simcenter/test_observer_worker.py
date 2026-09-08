import json

from test_job_observer import observed  # noqa: F401
from test_preparation import context  # noqa: F401

from nx_mcp.simcenter import observer_worker


class FakeThread:
    starts = 0

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.alive = False

    def start(self):
        type(self).starts += 1
        self.alive = True

    def is_alive(self):
        return self.alive


def test_launch_retry_reuses_live_observer(observed, monkeypatch):  # noqa: F811
    workspace, store, deck = observed
    registry = {}
    FakeThread.starts = 0
    monkeypatch.setattr(observer_worker.threading, "Thread", FakeThread)
    first = observer_worker.ensure_observer(registry, workspace, "observe-01")
    second = observer_worker.ensure_observer(registry, workspace, "observe-01")
    assert first["state"] == "started" and second["reused"]
    assert FakeThread.starts == 1 and store.inspect("observe-01")["state"] == "launch_returned"
    next(iter(registry.values()))["thread"].alive = False
    assert observer_worker.ensure_observer(registry, workspace, "observe-01")["state"] == "started"
    assert FakeThread.starts == 2  # observation restarts; no solver callback exists here


def test_worker_commits_terminal_and_does_not_release_gate(observed):  # noqa: F811
    workspace, store, deck = observed
    path = store._directory("observe-01") / "observer-test.log"
    observer_worker._run(workspace, "observe-01", "simcenter-jobs", path, 1)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert rows[-1]["worker"] == "finished"
    assert store.inspect("observe-01")["state"] == "solver_exited"
    assert not (store._directory("observe-01") / "launch-gate-release.json").exists()


def test_worker_failure_redacts_exception_text(observed, monkeypatch):  # noqa: F811
    workspace, store, deck = observed

    def fail(*args):
        raise RuntimeError("password=should-not-be-logged")

    monkeypatch.setattr(observer_worker, "observe_terminal", fail)
    path = store._directory("observe-01") / "observer-error.log"
    observer_worker._run(workspace, "observe-01", "simcenter-jobs", path, 1)
    assert "should-not-be-logged" not in path.read_text()
    assert json.loads(path.read_text().splitlines()[-1])["worker"] == "failed"
    assert store.inspect("observe-01")["state"] == "launch_returned"
