import sys
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.region_results import temperature_regions


@pytest.fixture
def model(monkeypatch):
    cae = NS(
        Result=NS(Component=NS(Scalar=0), GroupContainer=NS(ThreeDimensional=3, TwoDimensional=2))
    )
    monkeypatch.setitem(sys.modules, "NXOpen", NS(CAE=cae))
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    result = NS(
        AskBasicUnits=lambda: [None, NS(Name="MilliMeter"), None, None, None],
        AskNumNodes=lambda: 3,
        AskNumElements=lambda: 2,
        GetLoadcases=lambda: [
            NS(GetIterations=lambda: [NS(GetResultTypes=lambda: [NS(Name="Temperature - Nodal")])])
        ],
        AskNumGroupsInContainer=lambda kind: 2,
        AskNumElementsOfGroup=lambda kind, i: [i + 1],
        AskElementNodes=lambda e: [1, 2] if e == 1 else [2, 3],
        AskNodeCoordinates=lambda ids: [NS(X=i, Y=0, Z=0) for i in ids],
        AskNodeLabel=lambda i: i + 100,
    )
    access = NS(
        IsResultDefined=lambda ids: [True] * len(ids),
        AskNodalResult=lambda ids: [{1: 10.0, 2: 30.0, 3: 50.0}[i] for i in ids],
    )
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
        DeleteResultAccess=lambda _: freed.append("access"),
        DeleteResultParameters=lambda _: freed.append("params"),
        DeleteResult=lambda _: freed.append("result"),
    )
    monkeypatch.setattr(
        "nx_mcp.simcenter.region_results.acquire_result", lambda *a: (result, False)
    )
    return (
        NS(ResultManager=manager),
        NS(UnitCollection=NS(FindObject=lambda _: object())),
        result,
        access,
        freed,
    )


def test_group_membership_shared_nodes_and_mean_are_explicit(model):
    session, sim, _, _, freed = model
    value = temperature_regions(session, sim)
    a, b = value["items"]
    assert [a["arithmetic_nodal_mean"], b["arithmetic_nodal_mean"]] == [20.0, 40.0]
    assert a["maximum"]["index"] == b["minimum"]["index"] == 2
    assert a["node_count"] == b["node_count"] == 2
    assert a["membership_sha256"] != b["membership_sha256"]
    assert value["result_freshness"] == "not_verified"
    assert freed == ["access", "params"]
    page = temperature_regions(session, sim, offset=1, limit=1)
    assert page["items"] == [b] and page["next_offset"] is None
    assert temperature_regions(session, sim, offset=2)["items"] == []


@pytest.mark.parametrize("failure", ["budget", "traversal", "node", "element", "empty", "values"])
def test_invalid_native_selection_or_limits_never_returns_partial_group(
    model, monkeypatch, failure
):
    session, sim, result, access, freed = model
    monkeypatch.setattr("nx_mcp.simcenter.region_results.acquire_result", lambda *a: (result, True))
    if failure == "node":
        result.AskElementNodes = lambda e: [99]
    if failure == "element":
        result.AskNumElementsOfGroup = lambda k, i: [99]
    if failure == "empty":
        result.AskNumElementsOfGroup = lambda k, i: []
    if failure == "values":
        access.AskNodalResult = lambda ids: [float("nan")] * len(ids)
    with pytest.raises(NXToolError):
        temperature_regions(
            session,
            sim,
            maximum_entities=4 if failure == "budget" else 5 if failure == "traversal" else 100,
        )
    assert freed[-1] == "result"
    if failure != "budget":
        assert freed[:2] == ["access", "params"]


def test_invalid_inputs_do_not_acquire_native_result(monkeypatch):
    acquire = Mock(side_effect=AssertionError("unexpected acquisition"))
    monkeypatch.setattr("nx_mcp.simcenter.region_results.acquire_result", acquire)
    for args in ({"dimension": "fluid"}, {"maximum_entities": True}, {"limit": 51}, {"offset": -1}):
        with pytest.raises(NXToolError):
            temperature_regions(None, None, **args)
    acquire.assert_not_called()


def test_partial_and_empty_fields_preserve_geometry_and_report_coverage(model):
    session, sim, result, access, freed = model
    access.IsResultDefined = lambda ids: [i == 1 for i in ids]
    access.AskNodalResult = Mock(return_value=[10.0])
    first, second = temperature_regions(session, sim)["items"]
    access.AskNodalResult.assert_called_once_with([1])
    assert first["node_count"] == 2
    assert first["defined_node_count"] == first["undefined_node_count"] == 1
    assert first["arithmetic_nodal_mean"] == 10
    assert first["bounds"]["maximum"] == [2, 0, 0]
    assert second["defined_node_count"] == 0
    assert second["undefined_node_count"] == 2
    assert second["minimum"] is second["maximum"] is second["arithmetic_nodal_mean"] is None
    assert second["bounds"]["maximum"] == [3, 0, 0]
