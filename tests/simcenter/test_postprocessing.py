import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.simcenter.postprocessing import create_temperature_view, set_temperature_range


@pytest.fixture
def native(monkeypatch):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")
    nx.CAE = cae
    cae.Result = NS(Component=NS(Scalar=0))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    events = []
    params = NS(
        **{
            name: lambda *a: None
            for name in [
                "SetLoadcaseIteration",
                "SetGenericResultType",
                "SetResultComponent",
                "SetUnit",
            ]
        }
    )
    result = NS(
        GetLoadcases=lambda: [
            NS(GetIterations=lambda: [NS(GetResultTypes=lambda: [NS(Name="Temperature - Nodal")])])
        ]
    )

    def fail_main(_):
        raise RuntimeError("native main-view failure")

    post = NS(
        GetPostviewIds=lambda: [],
        CreatePostviewForResult=lambda *a: 7,
        PostviewRename=lambda *a: None,
        PostviewUpdate=lambda *a: None,
        SetMainPostviewIdInActivePart=fail_main,
        PostviewDelete=lambda v: events.append(("view", v)),
    )
    manager = NS(
        CreateSolutionResult=lambda *a: result,
        CreateResultParameters=lambda: params,
        DeleteResultParameters=lambda p: events.append(("params", p)),
        DeleteResult=lambda r: events.append(("result", r)),
    )
    sim = NS(
        Simulation=NS(ActiveSolution=object()), UnitCollection=NS(FindObject=lambda *a: object())
    )
    return (
        NS(Post=post, ResultManager=manager, Parts=NS(BaseWork=sim, BaseDisplay=sim)),
        sim,
        events,
    )


def test_failed_view_creation_cleans_in_dependency_order(native):
    session, sim, events = native
    with pytest.raises(RuntimeError, match="native main-view"):
        create_temperature_view(session, sim, loadcase_index=0)
    assert [kind for kind, _ in events] == ["view", "params", "result"]


def test_invalid_loadcase_releases_result_without_creating_view(native):
    session, sim, events = native
    with pytest.raises(ValueError, match="Loadcase"):
        create_temperature_view(session, sim, loadcase_index=1)
    assert [kind for kind, _ in events] == ["result"]


def test_existing_views_are_preserved(native):
    session, sim, events = native
    session.Post.GetPostviewIds = lambda: [99]
    with pytest.raises(ValueError, match="already exist"):
        create_temperature_view(session, sim, loadcase_index=0)
    assert events == []


@pytest.mark.parametrize("bounds", [(40, 20), (20, float("nan")), (True, 40)])
def test_invalid_ranges_rejected_before_native_access(bounds):
    with pytest.raises(ValueError, match="finite increasing"):
        set_temperature_range(None, 1, *bounds)


def test_iteration_update_restores_parameters_after_native_failure():
    from nx_mcp.simcenter.postprocessing import select_temperature_iteration

    field = NS(Name="Temperature - Nodal")
    events = []
    result = NS(
        GetLoadcases=lambda: [NS(GetIterations=lambda: [NS(GetResultTypes=lambda: [field])])]
    )
    before = NS(GetUnit=lambda: NS(Name="Celsius"), GetGenericResultType=lambda: field)
    updated = NS(SetLoadcaseIteration=lambda *a: None, SetGenericResultType=lambda *a: None)
    copies = iter([(result, before), (result, updated)])

    def apply(view, params):
        events.append(params)
        if params is updated:
            raise RuntimeError("native setter failed after mutation")

    session = NS(
        Post=NS(
            GetResultForPostview=lambda _: next(copies),
            PostviewSetResult=apply,
            PostviewUpdate=lambda _: None,
        ),
        ResultManager=NS(DeleteResultParameters=lambda p: None),
    )
    with pytest.raises(RuntimeError, match="native setter failed"):
        select_temperature_iteration(session, 2, loadcase_index=0)
    assert events == [updated, before]
