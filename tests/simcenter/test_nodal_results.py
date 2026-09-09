import sys
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.nodal_results import temperature_nodes


@pytest.fixture
def model(monkeypatch):
    cae = NS(Result=NS(Component=NS(Scalar=0)))
    monkeypatch.setitem(sys.modules, "NXOpen", NS(CAE=cae))
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    result = NS(
        AskBasicUnits=lambda: [None, NS(Name="MilliMeter"), None, None, None],
        AskNumNodes=lambda: 3,
        AskNodeCoordinates=lambda indices: [NS(X=i, Y=0, Z=0) for i in indices],
        AskNodeLabel=lambda i: i + 100,
        GetLoadcases=lambda: [
            NS(GetIterations=lambda: [NS(GetResultTypes=lambda: [NS(Name="Temperature - Nodal")])])
        ],
    )
    access = NS(AskNodalResult=lambda indices: [20 + i for i in indices])
    params = NS(
        **{
            n: Mock()
            for n in [
                "SetLoadcaseIteration",
                "SetGenericResultType",
                "SetResultComponent",
                "SetUnit",
            ]
        }
    )
    freed = []
    manager = NS(
        CreateResultParameters=lambda: params,
        CreateResultAccess=Mock(return_value=access),
        DeleteResultParameters=lambda _: freed.append("params"),
        DeleteResultAccess=lambda _: freed.append("access"),
        DeleteResult=lambda _: freed.append("result"),
    )
    monkeypatch.setattr("nx_mcp.simcenter.nodal_results.acquire_result", lambda *a: (result, False))
    return (
        NS(ResultManager=manager),
        NS(UnitCollection=NS(FindObject=lambda _: object())),
        result,
        access,
        freed,
    )


def test_bounded_pages_native_indices_labels_and_display_ownership(model):
    session, sim, _, _, freed = model
    first = temperature_nodes(session, sim, limit=2)
    last = temperature_nodes(session, sim, offset=2, limit=2)
    end = temperature_nodes(session, sim, offset=3, limit=2)
    assert [r["index"] for r in first["items"] + last["items"]] == [1, 2, 3]
    assert [r["label"] for r in first["items"] + last["items"]] == [101, 102, 103]
    assert first["next_offset"] == 2 and last["next_offset"] is None
    assert end["items"] == [] and end["next_offset"] is None
    assert session.ResultManager.CreateResultAccess.call_count == 2
    assert freed == ["access", "params", "access", "params"]
    assert first["units"] == "degC" and first["coordinate_units"] == "mm"


@pytest.mark.parametrize("change", ["units", "cardinality", "nonfinite", "selection"])
def test_unreadable_data_never_returns_partial_page_and_releases_owned_result(
    model, monkeypatch, change
):
    session, sim, result, access, freed = model
    monkeypatch.setattr("nx_mcp.simcenter.nodal_results.acquire_result", lambda *a: (result, True))
    if change == "units":
        result.AskBasicUnits = lambda: [None] * 5
    if change == "cardinality":
        access.AskNodalResult = lambda indices: []
    if change == "nonfinite":
        access.AskNodalResult = lambda indices: [float("nan")] * len(indices)
    with pytest.raises(NXToolError):
        temperature_nodes(session, sim, iteration_index=9 if change == "selection" else 0)
    assert freed[-1] == "result"
    if change in ("cardinality", "nonfinite"):
        assert freed == ["access", "params", "result"]


@pytest.mark.parametrize(
    "args", [{"offset": -1}, {"limit": 201}, {"limit": True}, {"loadcase_index": 1.2}]
)
def test_invalid_paging_before_result_acquisition(monkeypatch, args):
    acquire = Mock(side_effect=AssertionError("must not acquire"))
    monkeypatch.setattr("nx_mcp.simcenter.nodal_results.acquire_result", acquire)
    with pytest.raises(NXToolError):
        temperature_nodes(None, None, **args)
    acquire.assert_not_called()


@pytest.mark.parametrize("change", ["before", "during", "none"])
def test_native_page_binds_exact_result_file_and_discards_changed_page(monkeypatch, change):
    from nx_mcp.simcenter import nodal_results, result_identity
    from nx_mcp.simcenter.native import SimcenterMixin

    class SimPart:
        Simulation = NS(ActiveSolution=object())

    cae = NS(SimPart=SimPart)
    monkeypatch.setitem(sys.modules, "NXOpen", NS(CAE=cae))
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    sim = SimPart()
    row = {"path": "case.bun", "bytes": 5, "sha256": "a" * 64}
    different = {**row, "sha256": "b" * 64}
    inspector = Mock(
        side_effect=[
            {"files": [different if change == "before" else row]},
            {"files": [different if change == "during" else row]},
        ]
    )
    monkeypatch.setattr(result_identity, "inspect_result_identity", inspector)
    reader = Mock(return_value={"items": [{"index": 1}], "total": 1})
    monkeypatch.setattr(nodal_results, "temperature_nodes", reader)
    host = NS(
        objects=NS(resolve=lambda *a, **k: sim),
        session=NS(Parts=NS(BaseWork=sim)),
        workspace=object(),
        _reference=lambda *a: {"id": "sim"},
    )
    if change == "none":
        result = SimcenterMixin._sim_temperature_nodes(host, "sim", "a" * 64)
        assert result["result_file"] == row
    else:
        with pytest.raises(NXToolError) as error:
            SimcenterMixin._sim_temperature_nodes(host, "sim", "a" * 64)
        assert error.value.code == "NX_SIM_RESULT_CHANGED"
    assert reader.call_count == (0 if change == "before" else 1)
