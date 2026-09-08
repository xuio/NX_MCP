import pytest

from nx_mcp.simcenter.process_identity import correlate_process, inspect_process


@pytest.fixture
def identity():
    return {
        "pid": 123,
        "creation_filetime_100ns": "123456789",
        "executable_path": r"C:\NX\solver.exe",
    }


def test_pid_reuse_is_not_the_original_solver(identity):
    actual = {**identity, "creation_filetime_100ns": "123456790"}
    result = correlate_process(identity, {"pid": 123, "state": "running", "identity": actual})
    assert result["state"] == "identity_mismatch"
    assert result["solver_success"] == "not_established"


def test_missing_or_access_denied_are_not_success(identity):
    assert (
        correlate_process(identity, {"pid": 123, "state": "missing"})["state"]
        == "original_process_not_present"
    )
    assert (
        correlate_process(identity, {"pid": 123, "state": "unavailable", "win32_error": 5})["state"]
        == "unknown"
    )


def test_same_creation_but_other_executable_is_rejected(identity):
    actual = {**identity, "executable_path": r"C:\other.exe"}
    assert (
        correlate_process(identity, {"pid": 123, "state": "running", "identity": actual})["state"]
        == "identity_mismatch"
    )


def test_windows_path_case_and_exit(identity):
    actual = {**identity, "executable_path": r"c:\nx\SOLVER.EXE"}
    result = correlate_process(
        identity, {"pid": 123, "state": "exited", "identity": actual, "exit_code": 0}
    )
    assert result["state"] == "same_process_exited"
    assert result["solver_success"] == "not_established"


@pytest.mark.parametrize("pid", [True, 0, -1, 2**32, "123"])
def test_invalid_process_query(pid):
    with pytest.raises(ValueError):
        inspect_process(pid)


def test_wrong_observation_pid_is_unknown(identity):
    assert correlate_process(identity, {"pid": 124, "state": "missing"})["state"] == "unknown"


def test_retained_exited_handle_without_image_path(identity):
    observation = {
        "pid": 123,
        "state": "exited",
        "identity": {**identity, "executable_path": None},
        "exit_code": 0,
        "image_path_state": "unavailable_after_exit",
        "image_path_error": 31,
    }
    assert correlate_process(identity, observation)["state"] == "same_process_exited"
    observation["identity"]["creation_filetime_100ns"] = "9999"
    assert correlate_process(identity, observation)["state"] == "identity_mismatch"


def test_missing_image_path_does_not_identify_a_running_process(identity):
    observation = {
        "pid": 123,
        "state": "running",
        "identity": {**identity, "executable_path": None},
    }
    assert correlate_process(identity, observation)["state"] == "unknown"
