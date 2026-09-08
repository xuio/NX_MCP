import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.log_reader import read_log
from nx_mcp.workspace import Workspace, WorkspaceViolation


def test_complete_line_cursors_hold_partial_lines_and_redact(tmp_path):
    file = tmp_path / "solver.log"
    file.write_bytes(b"iteration 1\nlicense server 1234@private\npartial")
    workspace = Workspace(tmp_path)
    first = read_log(workspace, "solver.log")
    assert "1234" not in first["text"] and first["redacted_line_count"] == 1
    assert first["trailing_partial_line_held"]
    with file.open("ab") as stream:
        stream.write(b" finished\n")
    second = read_log(
        workspace, "solver.log", offset=first["next_offset"], file_identity=first["file_identity"]
    )
    assert second["text"] == "partial finished\n"
    assert not second["more_bytes_at_snapshot"]


def test_stale_and_unaligned_cursors_and_oversized_lines_fail(tmp_path):
    file = tmp_path / "solver.log"
    file.write_bytes(b"abc\n")
    workspace = Workspace(tmp_path)
    for kwargs in ({"offset": 1}, {"offset": 10}, {"file_identity": "other"}):
        with pytest.raises(NXToolError):
            read_log(workspace, "solver.log", **kwargs)
    file.write_bytes(b"x" * 257)
    with pytest.raises(NXToolError, match="exceeds"):
        read_log(workspace, "solver.log", maximum_bytes=256)
    with pytest.raises(WorkspaceViolation):
        read_log(workspace, "../outside.log")


def test_job_log_requires_matching_output_owner(tmp_path):
    from nx_mcp.simcenter.jobs import JobStore
    from nx_mcp.simcenter.log_reader import read_job_log
    from nx_mcp.simcenter.output_claims import claim_output

    workspace = Workspace(tmp_path)
    store = JobStore(workspace)
    folder = str(tmp_path / "outputs")
    store.reserve("owned", {"isolated_output_directory": folder})
    claim_output(store, "owned", folder)
    (tmp_path / "outputs" / "solve.log").write_text("iteration 1\n")
    result = read_job_log(store, "owned", "solve.log")
    assert result["text"] == "iteration 1\n" and not result["job_state_changed"]
    for name in ("../solve.log", r"..\solve.log", "C:solve.log", "solve.txt"):
        with pytest.raises(NXToolError):
            read_job_log(store, "owned", name)
    store.reserve("other", {"isolated_output_directory": folder})
    with pytest.raises(NXToolError) as error:
        read_job_log(store, "other", "solve.log")
    assert error.value.code == "NX_SIM_OUTPUT_CONFLICT"
    (tmp_path / "outputs" / ".nx-sim-output-owner.json").write_text("{")
    with pytest.raises(NXToolError) as error:
        read_job_log(store, "owned", "solve.log")
    assert error.value.code == "NX_SIM_OUTPUT_UNBOUND"


def test_job_log_listing_and_device_rejection(tmp_path):
    from nx_mcp.simcenter.jobs import JobStore
    from nx_mcp.simcenter.log_reader import list_job_logs, read_job_log
    from nx_mcp.simcenter.output_claims import claim_output

    store = JobStore(Workspace(tmp_path))
    directory = tmp_path / "output"
    store.reserve("listed", {"isolated_output_directory": str(directory)})
    claim_output(store, "listed", str(directory))
    for name in ("z.log", "A.LOG", "input.xml"):
        (directory / name).write_text("example\n")
    (directory / "linked.log").symlink_to(directory / "z.log")
    first = list_job_logs(store, "listed", limit=1)
    second = list_job_logs(store, "listed", offset=1, limit=1)
    assert first["logs"][0]["log_name"] == "A.LOG" and first["next_offset"] == 1
    assert second["logs"][0]["log_name"] == "z.log" and second["next_offset"] is None
    assert first["total"] == 2
    assert read_job_log(store, "listed", "A.LOG")["text"] == "example\n"
    for name in ("CON.log", "NUL.log", "com1.log", "LPT9.log"):
        with pytest.raises(NXToolError):
            read_job_log(store, "listed", name)
