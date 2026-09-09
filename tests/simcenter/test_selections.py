import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.selections import face_inventory


@pytest.fixture
def setup(monkeypatch):
    nx, cae, uf = [ModuleType(name) for name in ("NXOpen", "NXOpen.CAE", "NXOpen.UF")]

    class SimPart:
        pass

    class FemPart:
        pass

    cae.SimPart, cae.FemPart = SimPart, FemPart
    sim, fem = SimPart(), FemPart()
    fem.Bodies, fem.PartUnits = [NS(Tag=10)], 1
    sim.FemPart = fem
    component = NS(
        Prototype=fem,
        Name="mesh occurrence",
        FindOccurrence=lambda p: NS(Tag=p.Tag + 100, OwningPart=sim),
    )
    sim.ComponentAssembly = NS(RootComponent=NS(GetChildren=lambda: [component]))
    sf = NS(
        BodyAskFaces=lambda tag: (2, [2, 1]),
        FaceAskBoundingBox=lambda tag: [0, 0, tag, 10, 10, tag],
    )
    uf.UFSession = NS(GetUFSession=lambda: NS(Sf=sf))
    nx.TaggedObjectManager = NS(GetTaggedObject=lambda tag: NS(Tag=tag))
    nx.CAE, nx.UF = cae, uf
    for module in (nx, cae, uf):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    return NS(Parts=NS(BaseWork=sim)), sim, sf, component


def test_bounds_are_labeled_as_fem_prototype_coordinates(setup):
    session, sim, _, _ = setup
    result = face_inventory(session, sim)
    assert result["coordinate_frame"] == "fem_part_absolute" and result["units"] == "mm"
    assert [row["face"].Tag for row in result["rows"]] == [101, 102]
    assert result["rows"][0]["bounds"]["minimum"] == [0, 0, 1]


def test_unresolved_occurrence_is_not_silently_skipped(setup):
    session, sim, _, component = setup
    component.FindOccurrence = lambda p: None
    with pytest.raises(NXToolError) as exc:
        face_inventory(session, sim)
    assert exc.value.code == "NX_SIM_SELECTION_OWNER"


def test_inconsistent_native_count_rejected(setup):
    session, sim, sf, _ = setup
    sf.BodyAskFaces = lambda tag: (3, [1, 2])
    with pytest.raises(NXToolError) as exc:
        face_inventory(session, sim)
    assert exc.value.code == "NX_SIM_READBACK_MISMATCH"


def test_fem_faces_are_prototypes_not_sim_occurrences(setup, monkeypatch):
    session, sim, _, component = setup
    fem = sim.FemPart
    session.Parts.BaseWork = fem
    nx = sys.modules["NXOpen"]
    nx.TaggedObjectManager.GetTaggedObject = lambda tag: NS(Tag=tag, OwningPart=fem)
    component.FindOccurrence = lambda _: (_ for _ in ()).throw(
        AssertionError("No occurrence lookup")
    )
    result = face_inventory(session, fem)
    assert result["selection_scope"] == "fem_prototype"
    assert result["component_name"] is None
    assert [row["face"].Tag for row in result["rows"]] == [1, 2]
    assert all(row["face"].OwningPart == fem for row in result["rows"])
