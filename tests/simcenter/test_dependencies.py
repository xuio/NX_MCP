import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.simcenter.dependencies import inspect_direct
from nx_mcp.workspace import Workspace


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")
    nx.CAE = cae

    class SimPart:
        pass

    class FemPart:
        pass

    cae.SimPart, cae.FemPart = SimPart, FemPart
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    sim, fem, cad = SimPart(), FemPart(), NS()
    for i, part in enumerate((sim, fem, cad)):
        part.Tag = i + 1
        part.FullPath = str(tmp_path / f"{i}.prt")
        part.IsModified = False
        part.IsFullyLoaded = True
        part.PartUnits = 1
        part.ComponentAssembly = None
    sim.FemPart = fem
    fem.AssociatedCadPart = cad
    fem.MasterCadPart = cad
    fem.IdealizedPart = None
    fem.FullPathForAssociatedCadPart = cad.FullPath
    return NS(Parts=NS(BaseWork=sim, BaseDisplay=sim)), sim, fem, cad, Workspace(tmp_path)


def test_shared_cad_is_one_document_with_two_roles(fixture):
    session, sim, _, cad, workspace = fixture
    result = inspect_direct(session, sim, workspace)
    assert len(result["rows"]) == 3
    assert result["rows"][2]["roles"] == ["AssociatedCadPart", "MasterCadPart"]
    assert result["rows"][2]["path"] == cad.FullPath
    assert not result["complete_analysis_package"]


def test_unloaded_association_and_unsaved_flags_are_explicit(fixture):
    session, sim, fem, _, workspace = fixture
    fem.AssociatedCadPart = fem.MasterCadPart = None
    fem.IsModified = True
    result = inspect_direct(session, sim, workspace)
    assert result["unresolved"][0]["reason"] == "not_loaded_or_unresolved"
    assert result["rows"][1]["modified"]


def test_recursive_assembly_gap_is_not_silently_omitted(fixture):
    session, sim, _, cad, workspace = fixture
    cad.ComponentAssembly = NS(RootComponent=NS(GetChildren=lambda: [object()]))
    result = inspect_direct(session, sim, workspace)
    assert result["unresolved"][0]["reason"] == "assembly_children_not_enumerated"
