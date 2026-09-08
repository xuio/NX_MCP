from concurrent.futures import ThreadPoolExecutor

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.jobs import JobStore
from nx_mcp.workspace import Workspace, WorkspaceViolation


@pytest.fixture
def store(tmp_path):
    return JobStore(Workspace(tmp_path))


def test_reconnect_preserves_identity_and_prevents_launch_retry(store):
    first = store.reserve("test-01", {"model_sha256": "fixture", "power_W": 1})
    assert first["state"] == "accepted"
    store.transition(
        "test-01",
        expected_revision=0,
        state="launch_requested",
        evidence={"intent": "call native solve once"},
    )
    reconnect = JobStore(store.workspace)
    replay = reconnect.reserve("test-01", {"power_W": 1, "model_sha256": "fixture"})
    assert replay["replayed"] and replay["state"] == "launch_requested"
    assert not replay["launch_retry_allowed"]
    with pytest.raises(NXToolError) as exc:
        reconnect.reserve("test-01", {"power_W": 2, "model_sha256": "fixture"})
    assert exc.value.code == "NX_SIM_JOB_CONFLICT"


def test_competing_writers_cannot_claim_two_launches(store):
    store.reserve("race", {"input": "same"})

    def claim(_):
        try:
            return store.transition(
                "race", expected_revision=0, state="launch_requested", evidence={"intent": "launch"}
            )
        except NXToolError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(claim, range(8)))
    assert sum(isinstance(row, dict) for row in rows) == 1
    assert store.inspect("race")["revision"] == 1


@pytest.mark.parametrize("where", ["request", "initial", "later"])
def test_interruption_fails_closed_without_overwriting(store, where):
    directory = store.root / "interrupted"
    if where == "request":
        directory.mkdir(parents=True)
        target = directory / "request.json"
    else:
        store.reserve("interrupted", {"input": "one"})
        target = directory / ("state-00000.json" if where == "initial" else "state-00001.json")
    target.write_bytes(b"{")
    result = JobStore(store.workspace).reserve("interrupted", {"input": "one"})
    assert result["state"] == "unknown" and not result["launch_retry_allowed"]
    assert target.read_bytes() == b"{"
    with pytest.raises(NXToolError):
        store.transition(
            "interrupted",
            expected_revision=0,
            state="launch_requested",
            evidence={"intent": "launch"},
        )


def test_terminal_state_does_not_imply_valid_results(store):
    store.reserve("terminal", {"input": "one"})
    for revision, state in enumerate(["launch_requested", "running", "solver_exited", "completed"]):
        result = store.transition(
            "terminal", expected_revision=revision, state=state, evidence={"observation": state}
        )
    assert result["results_validated"] is False
    assert result["numerical_convergence"] == "not_established"
    with pytest.raises(NXToolError):
        store.transition(
            "terminal", expected_revision=4, state="launch_requested", evidence={"intent": "launch"}
        )


def test_paths_and_nonfinite_manifests_rejected_before_reservation(store):
    with pytest.raises(NXToolError):
        store.reserve("../escape", {"input": "one"})
    with pytest.raises(ValueError):
        store.reserve("nan", {"value": float("nan")})
    assert not (store.root / "nan").exists()
    with pytest.raises(WorkspaceViolation):
        JobStore(store.workspace, "../outside")


def test_missing_history_and_tampered_chain_are_unknown(store):
    store.reserve("chain", {"input": "one"})
    store.transition(
        "chain", expected_revision=0, state="launch_requested", evidence={"intent": "launch"}
    )
    path = store.root / "chain" / "state-00000.json"
    path.write_text(path.read_text().replace('"evidence":{}', '"evidence":{"changed":true}'))
    assert store.inspect("chain")["state"] == "unknown"
