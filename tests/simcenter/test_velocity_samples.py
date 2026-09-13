import sys
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.velocity_samples import velocity_samples


@pytest.fixture
def model(monkeypatch):
    cae = NS(
        Result=NS(
            Component=NS(X=1, Y=2, Z=3, Magnitude=4), CoordinateSystem=NS(AbsoluteRectangular=5)
        )
    )
    monkeypatch.setitem(sys.modules, "NXOpen", NS(CAE=cae))
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    result = NS(
        AskBasicUnits=lambda: [None, NS(Name="MilliMeter"), None, None, None],
        AskNumElements=lambda: 2,
        AskNumNodes=lambda: 4,
        AskElementIndex=lambda label: {101: 1, 202: 2}.get(label, 0),
        AskElementLabel=lambda i: {1: 101, 2: 202}[i],
        AskElementNodes=lambda i: [1, 3, 2, 4],
        AskNodeCoordinates=lambda ids: [NS(X=i, Y=2 * i, Z=0) for i in ids],
        AskNodeLabel=lambda i: i + 1000,
        GetLoadcases=lambda: [
            NS(
                GetIterations=lambda: [
                    NS(GetResultTypes=lambda: [NS(Name="Velocity - Element-Nodal")])
                ]
            )
        ],
    )
    state = {}
    params = NS(SetLoadcaseIteration=Mock(), SetGenericResultType=Mock())
    for field in ["ResultComponent", "CoordinateSystem", "Unit"]:
        setattr(params, "Set" + field, lambda v, f=field: state.update({f: v}))
        setattr(params, "Get" + field, lambda f=field: state[f])
    access = NS(
        IsResultDefined=lambda ids: [i == 1 for i in ids],
        AskElementNodalResult=Mock(side_effect=lambda e, n: float(n * state["ResultComponent"])),
    )
    freed = []
    manager = NS(
        CreateResultParameters=lambda: params,
        CreateResultAccess=lambda *a: access,
        DeleteResultAccess=lambda _: freed.append("access"),
        DeleteResultParameters=lambda _: freed.append("params"),
        DeleteResult=lambda _: freed.append("result"),
    )
    monkeypatch.setattr(
        "nx_mcp.simcenter.velocity_samples.acquire_result", lambda *a: (result, False)
    )
    return (
        NS(ResultManager=manager),
        NS(UnitCollection=NS(FindObject=lambda n: n)),
        result,
        access,
        params,
        freed,
    )


def test_component_units_connectivity_and_undefined_elements(model):
    session, sim, result, access, params, freed = model
    r = velocity_samples(session, sim, element_labels=[202, 101], component="z")
    assert [e["element_label"] for e in r["items"]] == [202, 101]
    assert r["items"][0]["defined"] is False
    assert all(n["velocity"] is None for n in r["items"][0]["nodes"])
    assert [n["node_label"] for n in r["items"][1]["nodes"]] == [1001, 1003, 1002, 1004]
    assert [n["velocity"] for n in r["items"][1]["nodes"]] == [3, 9, 6, 12]
    assert access.AskElementNodalResult.call_count == 4
    assert r["units"] == "mm/s" and r["vector_coordinate_system"] == "absolute_rectangular"
    assert params.GetUnit() == "MilliMeterPerSecond"
    assert freed == ["access", "params"]
    assert r["result_freshness"] == "not_verified"


@pytest.mark.parametrize("labels", [[], [True], [0], [101, 101], list(range(1, 1026))])
def test_invalid_labels_rejected_before_native_access(monkeypatch, labels):
    acquire = Mock(side_effect=AssertionError("must not acquire"))
    monkeypatch.setattr("nx_mcp.simcenter.velocity_samples.acquire_result", acquire)
    with pytest.raises(NXToolError):
        velocity_samples(None, None, element_labels=labels)
    acquire.assert_not_called()


@pytest.mark.parametrize(
    "bad",
    ["missing_label", "roundtrip", "nonfinite", "connectivity", "availability", "unit", "frame"],
)
def test_invalid_native_data_rejected_with_owned_result_cleanup(model, monkeypatch, bad):
    session, sim, result, access, params, freed = model
    monkeypatch.setattr(
        "nx_mcp.simcenter.velocity_samples.acquire_result", lambda *a: (result, True)
    )
    if bad == "missing_label":
        result.AskElementIndex = lambda _: 0
    if bad == "roundtrip":
        result.AskElementLabel = lambda _: 999
    if bad == "nonfinite":
        access.AskElementNodalResult = lambda *a: float("nan")
    if bad == "connectivity":
        result.AskElementNodes = lambda _: [1, 1]
    if bad == "availability":
        access.IsResultDefined = lambda _: [1]
    if bad == "unit":
        params.GetUnit = lambda: "wrong"
    if bad == "frame":
        params.GetCoordinateSystem = lambda: -1
    with pytest.raises(NXToolError):
        velocity_samples(session, sim, element_labels=[101])
    assert freed[-1] == "result"


@pytest.mark.parametrize("change", ["before", "during", "none"])
def test_adapter_discards_changed_result_pages(monkeypatch, change):
    from nx_mcp.simcenter import result_identity
    from nx_mcp.simcenter.native import SimcenterMixin

    class SimPart:
        Simulation = NS(ActiveSolution=object())

    cae = NS(SimPart=SimPart)
    monkeypatch.setitem(sys.modules, "NXOpen", NS(CAE=cae))
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    sim = SimPart()
    row = {"path": "case.bun", "bytes": 5, "sha256": "a" * 64}
    changed = {**row, "sha256": "b" * 64}
    monkeypatch.setattr(
        result_identity,
        "inspect_result_identity",
        Mock(
            side_effect=[
                {"files": [changed if change == "before" else row]},
                {"files": [changed if change == "during" else row]},
            ]
        ),
    )
    reader = Mock(return_value={"items": []})
    monkeypatch.setattr("nx_mcp.simcenter.velocity_samples.velocity_samples", reader)
    host = NS(
        objects=NS(resolve=lambda *a, **k: sim),
        session=NS(Parts=NS(BaseWork=sim)),
        workspace=object(),
        _reference=lambda *a: {"id": "sim"},
    )
    if change == "none":
        r = SimcenterMixin._sim_velocity_samples(host, "sim", "a" * 64, [101], "z")
        assert r["result_file"] == row
        assert reader.call_args.kwargs["element_labels"] == [101]
    else:
        with pytest.raises(NXToolError, match="Result"):
            SimcenterMixin._sim_velocity_samples(host, "sim", "a" * 64, [101])
    assert reader.call_count == (0 if change == "before" else 1)


@pytest.mark.asyncio
async def test_public_tool_is_readonly_and_requires_bound_result(tmp_path, monkeypatch):
    from nx_mcp.server import create_server
    from nx_mcp.workspace import Workspace

    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")

    class Bridge:
        async def call(self, method, params):
            return {"status": "success", "method": method, "params": params}

    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_velocity_samples")
    assert {"document", "result_sha256", "element_labels"} <= set(tool.inputSchema["required"])
    assert "operation_id" not in tool.inputSchema["properties"]
    assert tool.inputSchema["properties"]["component"]["enum"] == ["x", "y", "z", "magnitude"]
