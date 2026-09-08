import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.fluid_domain import create_wrapped_region


@pytest.fixture
def native(monkeypatch):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")
    nx.CAE = cae
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    nx.BasePart = NS(Units=NS(Millimeters=1))
    nx.Point3d = lambda *p: p

    class FemPart:
        pass

    cae.FemPart = FemPart
    cae.FluidDomainBuilder = NS(IntExtType=NS(Point=1), OutputOptionsType=NS(BodyOnly=0))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    events = []

    def fail():
        raise RuntimeError("native wrapping failed")

    builder = NS(
        GeometrySelection=NS(Add=lambda _: None),
        SetCavityPoint=lambda _: None,
        Resolution=NS(),
        ClosingSize=NS(),
        CommitFluidDomain=fail,
        Destroy=lambda: events.append("destroy"),
    )

    class Domains(list):
        def CreateBuilder(self, recipe):
            return builder

    fem = FemPart()
    fem.PartUnits = 1
    fem.Points = NS(CreatePoint=lambda p: NS(Coordinates=p))
    fem.BaseFEModel = NS(FluidDomains=Domains())
    session = NS(
        Parts=NS(BaseWork=fem),
        SetUndoMark=lambda *a: events.append("mark") or 1,
        UndoToMark=lambda *a: events.append("undo"),
        DeleteUndoMark=lambda *a: None,
    )
    return session, fem, [NS(OwningPart=fem)], events


def test_native_wrap_failure_destroys_builder_before_rollback(native):
    session, fem, bodies, events = native
    with pytest.raises(RuntimeError, match="native wrapping failed"):
        create_wrapped_region(session, fem, bodies, [1, 2, 3], 2, "Region")
    assert events == ["mark", "destroy", "undo"]


def test_invalid_resolution_rejected_before_mutation(native):
    session, fem, bodies, events = native
    with pytest.raises(NXToolError) as error:
        create_wrapped_region(session, fem, bodies, [1, 2, 3], float("nan"), "Region")
    assert error.value.code == "NX_INVALID_ARGUMENT"
    assert events == []


@pytest.mark.parametrize(
    "volume,bounds",
    [(0, [0, 0, 0, 1, 1, 1]), (float("nan"), [0, 0, 0, 1, 1, 1]), (1, [1, 0, 0, 0, 1, 1])],
)
def test_invalid_native_geometry_rejected(native, monkeypatch, volume, bounds):
    from nx_mcp.simcenter.fluid_domain import inspect_region_geometry

    _, fem, bodies, events = native
    bodies[0].Tag = 10
    uf = ModuleType("NXOpen.UF")
    uf.UFSession = NS(
        GetUFSession=lambda: NS(
            Sf=NS(
                BodyAskBoundingBox=lambda tag: bounds,
                BodyAskVolumeAndCentroid=lambda tag: (volume, [0.5, 0.5, 0.5]),
            )
        )
    )
    monkeypatch.setitem(sys.modules, "NXOpen.UF", uf)
    with pytest.raises(NXToolError) as error:
        inspect_region_geometry(fem, bodies)
    assert error.value.code == "NX_SIM_INVALID_REGION"
    assert events == []
