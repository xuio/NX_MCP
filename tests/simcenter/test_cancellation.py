import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.cancellation import cancel_unlaunched
from nx_mcp.simcenter.jobs import JobStore
from nx_mcp.workspace import Workspace


def test_cancel_survives_reconnect_and_prevents_launch(tmp_path):
    workspace = Workspace(tmp_path)
    store = JobStore(workspace)
    store.reserve("cancel", {"fixture": True})
    result = cancel_unlaunched(workspace, "cancel", 0)
    assert result["state"] == "cancelled" and result["revision"] == 1
    assert cancel_unlaunched(workspace, "cancel", 0)["replayed"]
    assert not JobStore(workspace).inspect("cancel")["launch_retry_allowed"]
    with pytest.raises(NXToolError):
        store.transition(
            "cancel",
            expected_revision=1,
            state="launch_requested",
            evidence={"fixture_intent": True},
        )
    assert store.inspect("cancel")["revision"] == 1


def test_launch_intent_or_stale_revision_never_gets_cancelled(tmp_path):
    workspace = Workspace(tmp_path)
    store = JobStore(workspace)
    store.reserve("launch", {"fixture": True})
    with pytest.raises(NXToolError) as error:
        cancel_unlaunched(workspace, "launch", 8)
    assert error.value.code == "NX_SIM_JOB_REVISION_CONFLICT"
    store.transition(
        "launch", expected_revision=0, state="launch_requested", evidence={"fixture_intent": True}
    )
    before = store.inspect("launch")
    with pytest.raises(NXToolError) as error:
        cancel_unlaunched(workspace, "launch", 1)
    assert error.value.code == "NX_SIM_CANCELLATION_UNAVAILABLE"
    assert store.inspect("launch") == before


def test_cancel_and_launch_race_have_one_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    workspace = Workspace(tmp_path)
    store = JobStore(workspace)
    store.reserve("race", {"fixture": True})

    def attempt(cancel):
        try:
            if cancel:
                return cancel_unlaunched(workspace, "race", 0)["state"]
            return store.transition(
                "race",
                expected_revision=0,
                state="launch_requested",
                evidence={"fixture_intent": True},
            )["state"]
        except NXToolError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, [True, False]))
    assert outcomes.count("rejected") == 1
    assert store.inspect("race")["revision"] == 1
