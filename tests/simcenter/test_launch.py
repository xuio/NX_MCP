import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.jobs import JobStore
from nx_mcp.simcenter.launch import launch_once
from nx_mcp.workspace import Workspace


def test_callback_runs_after_intent_and_never_again_on_reconnect(tmp_path):
    store = JobStore(Workspace(tmp_path))
    called = []

    def launch():
        assert JobStore(store.workspace).inspect("once")["state"] == "launch_requested"
        called.append(1)
        return {"foreground": False}

    first = launch_once(store, "once", {"input": "same"}, launch)
    second = launch_once(JobStore(store.workspace), "once", {"input": "same"}, launch)
    assert first["state"] == second["state"] == "launch_returned"
    assert second["replayed"] and called == [1]
    assert not second["results_validated"]


def test_exception_after_possible_launch_is_not_retried(tmp_path):
    store = JobStore(Workspace(tmp_path))
    called = []

    def launch():
        called.append(1)
        raise RuntimeError("response interrupted after possible native launch")

    with pytest.raises(NXToolError) as exc:
        launch_once(store, "uncertain", {"input": "same"}, launch)
    assert exc.value.code == "NX_SIM_LAUNCH_UNCERTAIN"
    assert store.inspect("uncertain")["state"] == "launch_uncertain"
    result = launch_once(JobStore(store.workspace), "uncertain", {"input": "same"}, launch)
    assert result["replayed"] and called == [1]


def test_failed_intent_persistence_never_calls_native(tmp_path, monkeypatch):
    store = JobStore(Workspace(tmp_path))
    called = []

    def failed(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(store, "transition", failed)
    with pytest.raises(OSError):
        launch_once(store, "disk", {"input": "same"}, lambda: called.append(1))
    assert called == []


def test_returned_launch_with_failed_observation_is_uncertain_and_never_replayed(
    tmp_path, monkeypatch
):
    store = JobStore(Workspace(tmp_path))
    transition = store.transition
    calls = []

    def persist(*args, **kwargs):
        if kwargs["state"] == "launch_returned":
            raise OSError("disk full after solver launch")
        return transition(*args, **kwargs)

    monkeypatch.setattr(store, "transition", persist)
    with pytest.raises(NXToolError) as raised:
        launch_once(store, "returned", {"input": "same"}, lambda: calls.append(1))
    assert raised.value.code == "NX_SIM_LAUNCH_UNCERTAIN"
    assert raised.value.details == {
        "job_id": "returned",
        "mutation_outcome": "unknown",
        "api_returned": True,
        "observation_persisted": False,
    }
    restarted = JobStore(store.workspace)
    assert restarted.inspect("returned")["state"] == "launch_requested"
    replay = launch_once(restarted, "returned", {"input": "same"}, lambda: calls.append(2))
    assert replay["replayed"] and calls == [1]


def test_unserializable_native_readback_cannot_erase_launch_intent(tmp_path):
    store = JobStore(Workspace(tmp_path))
    calls = []

    def launch():
        calls.append(1)
        return {"unexpected_native_object": object()}

    with pytest.raises(NXToolError) as raised:
        launch_once(store, "serialization", {"input": "same"}, launch)
    assert raised.value.code == "NX_SIM_LAUNCH_UNCERTAIN"
    replay = launch_once(JobStore(store.workspace), "serialization", {"input": "same"}, launch)
    assert replay["replayed"] and calls == [1]
