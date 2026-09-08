import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.native import SimcenterMixin
from nx_mcp.workspace import Workspace


def test_modified_and_referenced_parts_are_rejected_before_close(monkeypatch, tmp_path):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")
    cae.FemPart = type("FemPart", (), {})
    cae.SimPart = type("SimPart", (), {})
    nx.CAE = cae
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr("nx_mcp.simcenter.solver_guard.require_solver_idle", lambda: None)
    monkeypatch.setattr("nx_mcp.assembly_loading.dependent_assemblies", lambda *_: [])
    fem = cae.FemPart()
    fem.FullPath = str(tmp_path / "fixture.fem")
    fem.IsModified = True
    sim = cae.SimPart()
    sim.FullPath = str(tmp_path / "parent.sim")
    sim.FemPart = fem
    executor = NS(
        objects=NS(resolve=lambda *a, **k: fem),
        workspace=Workspace(tmp_path),
        session=NS(Parts=[fem, sim]),
    )
    with pytest.raises(NXToolError) as error:
        SimcenterMixin._sim_close(executor, "fem-id")
    assert error.value.code == "NX_SIM_UNSAVED_DOCUMENT"
    fem.IsModified = False
    with pytest.raises(NXToolError) as error:
        SimcenterMixin._sim_close(executor, "fem-id")
    assert error.value.code == "NX_SIM_DOCUMENT_IN_USE"
    assert error.value.details["dependent_documents"] == [sim.FullPath]
    assert error.value.details["mutation_outcome"] == "not_started"


def test_partial_native_close_invalidates_removed_part(monkeypatch, tmp_path):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")
    cae.FemPart, cae.SimPart = type("FemPart", (), {}), type("SimPart", (), {})
    nx.CAE = cae
    nx.BasePart = NS(CloseWholeTree=NS(FalseValue=0), CloseModified=NS(DontCloseModified=2))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr("nx_mcp.simcenter.solver_guard.require_solver_idle", lambda: None)
    monkeypatch.setattr("nx_mcp.assembly_loading.dependent_assemblies", lambda *_: [])
    part = cae.SimPart()
    part.FullPath, part.IsModified, part.Tag = str(tmp_path / "fixture.sim"), False, 1
    parts = [part]

    def close(*args):
        assert args[1] == 2
        parts.clear()
        raise RuntimeError("Native error after unloading")

    part.Close = close
    invalidated = []
    executor = NS(
        objects=NS(resolve=lambda *a, **k: part, invalidate_part=invalidated.append),
        workspace=Workspace(tmp_path),
        session=NS(Parts=parts),
        _part_generations={1: "g1"},
        _history=[{"part_id": "p1"}],
        _checkpoints={"c1": {"part_id": "p1"}},
        _reference=lambda *args: {"id": "old", "part_id": "p1", "owner_part_path": part.FullPath},
    )
    with pytest.raises(NXToolError) as error:
        SimcenterMixin._sim_close(executor, "old")
    assert error.value.code == "NX_SIM_CLOSE_INCOMPLETE"
    assert error.value.details["mutation_outcome"] == "partial"
    assert invalidated == ["p1"] and not executor._part_generations
    assert not executor._history and not executor._checkpoints
