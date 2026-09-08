"""Fault injection for native clone inventory diagnostics and session restoration."""

import runpy
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from nx_mcp.simcenter import solver_guard


@pytest.mark.parametrize(
    "failed,count,user_abort", [(True, 1, False), (False, 1, False), (False, 0, True)]
)
def test_zero_return_does_not_hide_load_failure(tmp_path, monkeypatch, failed, count, user_abort):
    source = tmp_path / "source.sim"
    source.write_bytes(b"saved source")
    options = SimpleNamespace(ComponentLoadMethod="original")

    class Options:
        LoadMethod = SimpleNamespace(AsSaved="as_saved")
        ComponentLoadMethod = options.ComponentLoadMethod

    class Parts(list):
        LoadOptions = Options()

    parts = Parts([SimpleNamespace(FullPath=str(source), IsModified=True)])
    calls = []

    class Clone:
        OperationClass = SimpleNamespace(CLONE_OPERATION=0)

        def Initialise(self, operation):
            calls.append("initialise")

        def AddAssembly(self, path):
            return SimpleNamespace(
                Failed=failed,
                UserAbort=user_abort,
                NParts=count,
                FileNames=["missing.fem"] if count else [],
                Statuses=[720090] if count else [],
            ), 0

        def StartIteration(self):
            pytest.fail("Must reject load diagnostics before enumerating a partial clone set")

        def Terminate(self):
            calls.append("terminate")

    nx = ModuleType("NXOpen")
    uf = ModuleType("NXOpen.UF")
    uf.UFSession = SimpleNamespace(GetUFSession=lambda: SimpleNamespace(Clone=Clone()))
    nx.UF = uf
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.UF", uf)
    monkeypatch.setattr(solver_guard, "require_solver_idle", lambda: None)
    executor = SimpleNamespace(
        workspace=SimpleNamespace(resolve=lambda path: source),
        session=SimpleNamespace(Parts=parts),
    )
    fixture = Path(__file__).parents[2] / "examples/simcenter/probe_clone_inventory.py"
    result = runpy.run_path(str(fixture))["run"](executor)
    assert result["state"] == "failed"
    assert result["add_return_code"] == 0
    assert result["parts"] == [] and not result["clone_performed"]
    assert result["source_file_preserved"] and result["document_flags_preserved"]
    assert result["load_method_restored"]
    assert parts.LoadOptions.ComponentLoadMethod == "original"
    assert calls == ["initialise", "terminate"]
