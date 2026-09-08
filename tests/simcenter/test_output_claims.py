from concurrent.futures import ThreadPoolExecutor

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.jobs import JobStore
from nx_mcp.simcenter.launch import launch_isolated
from nx_mcp.simcenter.output_claims import claim_output
from nx_mcp.workspace import Workspace, WorkspaceViolation


def test_two_jobs_racing_across_stores_launch_only_one_callback(tmp_path):
    calls = []

    def compete(name):
        store = JobStore(Workspace(tmp_path), name)
        try:
            return launch_isolated(
                store,
                "same-id",
                {"case": name},
                lambda: calls.append(name),
                output_directory="runs/shared",
            )["state"]
        except NXToolError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(compete, ["ledger-a", "ledger-b"]))
    assert outcomes.count("launch_returned") == 1
    assert len(calls) == 1
    assert set(outcomes) <= {"launch_returned", "NX_SIM_OUTPUT_CONFLICT", "NX_SIM_OUTPUT_UNCERTAIN"}


def test_reconnect_and_terminal_owner_cannot_be_overwritten(tmp_path):
    store = JobStore(Workspace(tmp_path))
    calls = []
    first = launch_isolated(
        store, "first", {"case": 1}, lambda: calls.append(1), output_directory="run"
    )
    replay = launch_isolated(
        JobStore(store.workspace),
        "first",
        {"case": 1},
        lambda: calls.append(2),
        output_directory="run",
    )
    assert replay["replayed"] and calls == [1]
    store.transition(
        "first", expected_revision=first["revision"], state="failed", evidence={"fixture": True}
    )
    with pytest.raises(NXToolError, match="Another job owns"):
        launch_isolated(
            store, "second", {"case": 2}, lambda: calls.append(3), output_directory="run"
        )
    assert store.inspect("second")["state"] == "accepted" and calls == [1]


def test_interrupted_claim_never_launches_or_overwrites(tmp_path):
    directory = tmp_path / "run"
    directory.mkdir()
    record = directory / ".nx-sim-output-owner.json"
    record.write_text("{")
    calls = []
    with pytest.raises(NXToolError) as exc:
        launch_isolated(
            JobStore(Workspace(tmp_path)),
            "first",
            {"case": 1},
            lambda: calls.append(1),
            output_directory="run",
        )
    assert exc.value.code == "NX_SIM_OUTPUT_UNCERTAIN"
    assert record.read_text() == "{" and not calls


def test_workspace_escape_and_root_rejected(tmp_path):
    store = JobStore(Workspace(tmp_path))
    store.reserve("one", {"case": 1})
    with pytest.raises(WorkspaceViolation):
        claim_output(store, "one", "../escape")
    with pytest.raises(NXToolError, match="dedicated output"):
        claim_output(store, "one", ".")


def test_same_owner_reconnect_and_symlink_alias_share_claim(tmp_path):
    store = JobStore(Workspace(tmp_path))
    store.reserve("one", {"case": 1})
    claim_output(store, "one", "run")
    (tmp_path / "alias").symlink_to(tmp_path / "run", target_is_directory=True)
    assert claim_output(store, "one", "alias")["replayed"]
    store.reserve("two", {"case": 2})
    with pytest.raises(NXToolError, match="Another job owns"):
        claim_output(store, "two", "alias")
