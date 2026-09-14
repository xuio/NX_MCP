import sys
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.mass_flux_samples import mass_flux_samples


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
        AskNodeIndex=lambda label: label - 100,
        GetLoadcases=lambda: [
            NS(GetIterations=lambda: [NS(GetResultTypes=lambda: [NS(Name="Mass Flux - Nodal")])])
        ],
    )
    access = NS(
        IsResultDefined=lambda ids: [True] * len(ids),
        AskNodalResult=lambda indices: [20 + i for i in indices],
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
    unit = NS(Symbol="kg/sec-mm^2", Measure="Mass Flux")
    params.GetUnit = lambda: unit
    params.GetResultComponent = lambda: 0
    freed = []
    manager = NS(
        CreateResultParameters=lambda: params,
        CreateResultAccess=Mock(return_value=access),
        DeleteResultParameters=lambda _: freed.append("params"),
        DeleteResultAccess=lambda _: freed.append("access"),
        DeleteResult=lambda _: freed.append("result"),
    )
    monkeypatch.setattr(
        "nx_mcp.simcenter.mass_flux_samples.acquire_result", lambda *a: (result, False)
    )
    return (
        NS(ResultManager=manager),
        NS(UnitCollection=NS(FindObject=lambda _: unit)),
        result,
        access,
        freed,
    )


def test_selected_nodes_order_units_and_undefined_preserved(model):
    session, sim, result, access, freed = model
    access.IsResultDefined = lambda ids: [i != 2 for i in ids]
    access.AskNodalResult = Mock(side_effect=lambda ids: [-0.5 * i for i in ids])
    page = mass_flux_samples(session, sim, node_labels=[103, 102, 101])
    assert [r["label"] for r in page["items"]] == [103, 102, 101]
    assert [r["mass_flux"] for r in page["items"]] == [-1.5, None, -0.5]
    assert page["items"][1]["defined"] is False
    access.AskNodalResult.assert_called_once_with([3, 1])
    assert page["units"] == "kg/(s*mm^2)"
    assert page["coordinate_units"] == "mm"
    assert freed == ["access", "params"]


@pytest.mark.parametrize("labels", [[], [True], [0], [101, 101], list(range(1, 1026))])
def test_invalid_selection_before_acquisition(monkeypatch, labels):
    acquire = Mock(side_effect=AssertionError("must not acquire"))
    monkeypatch.setattr("nx_mcp.simcenter.mass_flux_samples.acquire_result", acquire)
    with pytest.raises(NXToolError):
        mass_flux_samples(None, None, node_labels=labels)
    acquire.assert_not_called()


@pytest.mark.parametrize(
    "bad", ["missing", "roundtrip", "nonfinite", "units", "availability", "coordinates"]
)
def test_invalid_native_data_rejects_and_cleans_up(model, monkeypatch, bad):
    session, sim, result, access, freed = model
    monkeypatch.setattr(
        "nx_mcp.simcenter.mass_flux_samples.acquire_result", lambda *a: (result, True)
    )
    if bad == "missing":
        result.AskNodeIndex = lambda _: 0
    if bad == "roundtrip":
        result.AskNodeLabel = lambda _: 999
    if bad == "nonfinite":
        access.AskNodalResult = lambda ids: [float("nan")] * len(ids)
    if bad == "units":
        sim.UnitCollection.FindObject = lambda _: NS(Symbol="kg/sec", Measure="Mass Flow")
    if bad == "availability":
        access.IsResultDefined = lambda ids: []
    if bad == "coordinates":
        result.AskNodeCoordinates = lambda ids: []
    with pytest.raises(NXToolError):
        mass_flux_samples(session, sim, node_labels=[101])
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
    monkeypatch.setattr("nx_mcp.simcenter.mass_flux_samples.mass_flux_samples", reader)
    host = NS(
        objects=NS(resolve=lambda *a, **k: sim),
        session=NS(Parts=NS(BaseWork=sim)),
        workspace=object(),
        _reference=lambda *a: {"id": "sim"},
    )
    if change == "none":
        r = SimcenterMixin._sim_mass_flux_samples(host, "sim", "a" * 64, [101])
        assert r["result_file"] == row
        assert reader.call_args.kwargs["node_labels"] == [101]
    else:
        with pytest.raises(NXToolError, match="Result"):
            SimcenterMixin._sim_mass_flux_samples(host, "sim", "a" * 64, [101])
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
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_mass_flux_samples")
    assert {"document", "result_sha256", "node_labels"} <= set(tool.inputSchema["required"])
    assert "operation_id" not in tool.inputSchema["properties"]
    assert tool.annotations.readOnlyHint is True
