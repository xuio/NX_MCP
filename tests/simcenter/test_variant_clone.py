"""Disk-transaction recovery checks; these do not establish NX API support."""

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import solver_guard, variant_clone
from nx_mcp.simcenter.variant_plan import plan_variant
from nx_mcp.workspace import Workspace


@pytest.fixture
def case(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    rows = []
    for suffix, role in [("sim", "simulation"), ("fem", "mesh"), ("prt", "AssociatedCadPart")]:
        source = tmp_path / ("source." + suffix)
        source.write_bytes(b"saved revision")
        rows.append(
            {
                "path": str(source),
                "roles": [role],
                "modified": False,
                "file_state": "exists",
                "fully_loaded": True,
                "units": "mm",
            }
        )
    plan = plan_variant(ws, {"rows": rows, "unresolved": []}, folder="variants/one", name="One")

    class Options:
        LoadMethod = SimpleNamespace(AsSaved="as_saved")
        ComponentLoadMethod = "original"

    class Parts(list):
        LoadOptions = Options()

    session = SimpleNamespace(
        Parts=Parts([SimpleNamespace(FullPath=r["path"], IsModified=False) for r in rows])
    )

    class Clone:
        OperationClass = SimpleNamespace(CLONE_OPERATION=0)
        Action = SimpleNamespace(CLONE=0)
        NamingTechnique = SimpleNamespace(USER_NAME=3)

        def __init__(self):
            self.calls = []
            self.fault = None
            self.names = {}

        def Initialise(self, value):
            self.calls.append("initialise")
            if self.fault == "initialise":
                raise RuntimeError("another clone context is active")
            self.names = {}

        def Terminate(self):
            self.calls.append("terminate")

        def AddAssembly(self, path):
            return SimpleNamespace(
                Failed=self.fault == "load", UserAbort=False, NParts=0, FileNames=[], Statuses=[]
            ), 0

        def StartIteration(self):
            self.iterator = iter([r["path"] for r in rows])

        def Iterate(self):
            if self.fault == "iteration":
                raise RuntimeError("inventory failed")
            return next(self.iterator, "")

        def StopIteration(self):
            self.calls.append("stop_iteration")

        def SetDefAction(self, value):
            pass

        def SetDefNaming(self, value):
            pass

        def SetDefAssocFileCopy(self, value):
            self.associated = value

        def AskDefAssocFileCopy(self):
            return self.associated

        def SetNaming(self, source, mode, target):
            self.names[source] = target

        def SetLogfile(self, path):
            Path(path).write_text("clone log")

        def SetDryrun(self, value):
            self.dry_run = value

        def InitNamingFailures(self):
            return SimpleNamespace(NFailures=0, Statuses=[])

        def PerformClone(self, failures):
            self.calls.append("dry_run" if self.dry_run else "clone")
            if self.fault == "naming":
                return SimpleNamespace(NFailures=1, Statuses=[1234])
            if not self.dry_run or self.fault == "dry_write":
                for source, target in self.names.items():
                    Path(target).write_bytes(Path(source).read_bytes())
                    if self.fault == "partial":
                        raise RuntimeError("native interrupted after first file")
            return failures

    clone = Clone()
    nx, uf = ModuleType("NXOpen"), ModuleType("NXOpen.UF")
    nx.UF = uf
    uf.UFSession = SimpleNamespace(GetUFSession=lambda: SimpleNamespace(Clone=clone))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.UF", uf)
    monkeypatch.setattr(solver_guard, "require_solver_idle", lambda: None)
    return session, ws, plan, clone


def execute(case):
    return variant_clone.execute_clone_plan(*case[:3])


def test_commit_replay_does_not_repeat_native_calls(case):
    result = execute(case)
    assert result["state"] == "native_files_cloned" and not result["replayed"]
    calls = list(case[3].calls)
    assert calls.count("clone") == 1 and calls.count("dry_run") == 1
    assert execute(case)["replayed"]
    assert case[3].calls == calls
    assert case[0].Parts.LoadOptions.ComponentLoadMethod == "original"
    Path(case[2]["mapping"][0]["destination"]).write_bytes(b"tampered")
    with pytest.raises(NXToolError, match="Cannot verify existing clone receipt"):
        execute(case)
    assert case[3].calls == calls


@pytest.mark.parametrize("state", ["accepted", "cloning", "failed"])
def test_incomplete_receipt_cannot_restart(case, state):
    execute(case)
    receipt = Path(case[2]["folder"]) / "variant-state.json"
    data = json.loads(receipt.read_text())
    data["state"] = state
    receipt.write_text(json.dumps(data))
    calls = list(case[3].calls)
    with pytest.raises(NXToolError) as caught:
        execute(case)
    assert caught.value.code == "NX_SIM_CLONE_INCOMPLETE"
    assert case[3].calls == calls


def test_changed_source_stops_before_creating_transaction(case):
    Path(case[2]["mapping"][1]["source"]["path"]).write_bytes(b"new source")
    with pytest.raises(NXToolError) as caught:
        execute(case)
    assert caught.value.code == "NX_SIM_SOURCE_CHANGED"
    assert not Path(case[2]["folder"]).exists() and not case[3].calls


@pytest.mark.parametrize(
    "fault", ["initialise", "load", "iteration", "naming", "dry_write", "partial"]
)
def test_failures_preserve_recovery_evidence_and_restore_load_options(case, fault):
    case[3].fault = fault
    with pytest.raises(NXToolError) as caught:
        execute(case)
    assert caught.value.code == "NX_SIM_CLONE_FAILED"
    assert not caught.value.details["retry_allowed"]
    assert case[0].Parts.LoadOptions.ComponentLoadMethod == "original"
    if fault == "initialise":
        assert "terminate" not in case[3].calls
    else:
        assert "terminate" in case[3].calls
    if fault == "iteration":
        assert "stop_iteration" in case[3].calls
    if fault != "partial":
        assert "clone" not in case[3].calls
    if fault in ("partial", "dry_write"):
        assert Path(case[2]["mapping"][0]["destination"]).exists()
    calls = list(case[3].calls)
    with pytest.raises(NXToolError) as replay:
        execute(case)
    assert replay.value.code == "NX_SIM_CLONE_INCOMPLETE"
    assert calls == case[3].calls
