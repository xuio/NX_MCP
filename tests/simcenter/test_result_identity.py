import hashlib
import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.simcenter.result_identity import inspect_result_identity
from nx_mcp.workspace import Workspace, WorkspaceViolation


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")
    nx.CAE = cae
    cae.SimSolution = NS(
        EnumVerifyResults=NS(
            VerificationSuccess=0, ChecksumCalFailed=1, ResultsChanged=2, ResultsOutOfDate=3
        )
    )
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    target = tmp_path / "result.bun"
    target.write_bytes(b"field data")
    sol = NS(
        ResultReferenceCount=1,
        GetResultReferenceByIndex=lambda _: NS(GetResultFile=lambda: (str(tmp_path), target.name)),
        VerifyResults=lambda: 2,
    )
    return sol, Workspace(tmp_path), target


def test_native_changed_status_is_not_freshness_acceptance(fixture):
    sol, workspace, target = fixture
    result = inspect_result_identity(sol, workspace)
    assert result["native_verification"]["state"] == "results_changed"
    assert result["files"][0]["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert result["result_freshness"] == "not_verified"
    assert result["engineering_accepted"] is False


def test_missing_file_and_budget_are_not_silent_successes(fixture):
    sol, workspace, target = fixture
    with pytest.raises(ValueError, match="budget"):
        inspect_result_identity(sol, workspace, maximum_bytes=2)
    target.unlink()
    with pytest.raises(FileNotFoundError):
        inspect_result_identity(sol, workspace)


def test_no_result_associations_is_not_success(fixture):
    sol, workspace, _ = fixture
    sol.ResultReferenceCount = 0
    with pytest.raises(ValueError, match="No associated result"):
        inspect_result_identity(sol, workspace)


def test_outside_workspace_association_is_rejected(fixture):
    sol, workspace, target = fixture
    sol.GetResultReferenceByIndex = lambda _: NS(
        GetResultFile=lambda: (str(target.parent.parent), "external.bun")
    )
    with pytest.raises(WorkspaceViolation):
        inspect_result_identity(sol, workspace)


def test_windows_path_and_handle_ctime_conventions(fixture, monkeypatch):
    import os

    sol, workspace, _ = fixture
    original = os.fstat

    def windows_handle(fd):
        value = original(fd)
        return NS(
            st_dev=value.st_dev,
            st_ino=value.st_ino,
            st_size=value.st_size,
            st_mtime_ns=value.st_mtime_ns,
            st_ctime_ns=value.st_ctime_ns + 12345,
        )

    monkeypatch.setattr(os, "fstat", windows_handle)
    assert inspect_result_identity(sol, workspace)["files"][0]["bytes"] == 10
