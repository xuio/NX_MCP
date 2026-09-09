from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from nx_mcp.simcenter.mesh_state import capture, compare, digest


def example():
    return [
        (1, [0.0, 0.0, 0.0]),
        (2, [1.0, 0.0, 0.0]),
        (3, [0.0, 1.0, 0.0]),
        (4, [0.0, 0.0, 1.0]),
    ], [(1, "Tetrahedron", "Mesh[1]", "Collector[1]", [1, 2, 3, 4])]


def state(nodes, elements, path="fixture.fem"):
    return digest(nodes, elements, units="mm", owner_path=path)


@pytest.mark.parametrize("change", ["coordinates", "order", "shape", "mesh", "collector"])
def test_same_counts_do_not_hide_mesh_changes(change):
    nodes, elements = example()
    before = state(nodes, elements)
    nodes, elements = deepcopy(nodes), [list(e) for e in elements]
    if change == "coordinates":
        nodes[1][1][0] = 1.000001
    elif change == "order":
        elements[0][4] = [2, 1, 3, 4]
    elif change == "shape":
        elements[0][1] = "OtherShape"
    elif change == "mesh":
        elements[0][2] = "Mesh[2]"
    elif change == "collector":
        elements[0][3] = "Collector[2]"
    after = state(nodes, elements)
    assert before["counts"] == after["counts"]
    assert compare(before, after)["state"] == "changed"


def test_signed_zero_and_repeated_snapshot_are_stable_but_not_full_freshness():
    nodes, elements = example()
    before = state(nodes, elements)
    nodes[0][1][0] = -0.0
    result = compare(before, state(nodes, elements))
    assert result["state"] == "matches" and result["full_model_freshness"] == "not_verified"
    assert compare(before, state(nodes, elements, "different.fem"))["state"] == "not_verified"


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "nonfinite"])
def test_invalid_topology_never_returns_partial_digest(mutation):
    nodes, elements = example()
    if mutation == "duplicate":
        nodes.append(nodes[-1])
    elif mutation == "missing":
        elements[0][4][0] = 99
    else:
        nodes[0][1][0] = float("nan")
    with pytest.raises(ValueError):
        state(nodes, elements)


def test_maps_disposed_when_second_acquisition_fails(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "NXOpen", NS(BasePart=NS(Units=NS(Millimeters=1))))
    nodes = NS(Dispose=Mock())

    class Model:
        FenodeLabelMap = nodes

        @property
        def FeelementLabelMap(self):
            raise RuntimeError("native acquisition failed")

    with pytest.raises(RuntimeError):
        capture(NS(PartUnits=1, BaseFEModel=Model()))
    nodes.Dispose.assert_called_once()


def test_budget_rejection_releases_both_maps_before_traversal(monkeypatch):
    import sys

    from nx_mcp.runtime import NXToolError

    monkeypatch.setitem(sys.modules, "NXOpen", NS(BasePart=NS(Units=NS(Millimeters=1))))
    nodes = NS(NumNodes=10, Dispose=Mock())
    elements = NS(NumElements=10, Dispose=Mock())
    with pytest.raises(NXToolError) as error:
        capture(
            NS(PartUnits=1, BaseFEModel=NS(FenodeLabelMap=nodes, FeelementLabelMap=elements)),
            maximum_entities=5,
        )
    assert error.value.code == "NX_SIM_INSPECTION_LIMIT"
    nodes.Dispose.assert_called_once()
    elements.Dispose.assert_called_once()


@pytest.mark.parametrize(
    "field,value", [("sha256", "bad"), ("counts", {}), ("owner_path", None), ("units", None)]
)
def test_incomplete_snapshot_cannot_match(field, value):
    nodes, elements = example()
    snapshot = state(nodes, elements)
    snapshot[field] = value
    assert compare(snapshot, snapshot)["state"] == "not_verified"


def test_same_digest_with_inconsistent_counts_is_unverified():
    nodes, elements = example()
    before = state(nodes, elements)
    after = deepcopy(before)
    after["counts"]["nodes"] += 1
    assert compare(before, after)["state"] == "not_verified"


@pytest.mark.asyncio
async def test_public_schema_has_bounded_explicit_budget(tmp_path, monkeypatch):
    from nx_mcp.server import create_server
    from nx_mcp.workspace import Workspace

    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(NS(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_mesh_state")
    assert tool.inputSchema["properties"]["maximum_entities"]["default"] == 200000
    assert tool.inputSchema["properties"]["maximum_entities"]["type"] == "integer"


def test_native_traversal_failure_releases_both_maps_and_returns_no_snapshot(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "NXOpen", NS(BasePart=NS(Units=NS(Millimeters=1))))
    nodes = NS(
        NumNodes=1,
        AskNextNodeLabel=Mock(side_effect=RuntimeError("node read failed")),
        Dispose=Mock(),
    )
    elements = NS(NumElements=0, Dispose=Mock())
    fem = NS(
        PartUnits=1,
        FullPath="fixture.fem",
        BaseFEModel=NS(FenodeLabelMap=nodes, FeelementLabelMap=elements),
    )
    with pytest.raises(RuntimeError, match="node read failed"):
        capture(fem)
    nodes.Dispose.assert_called_once()
    elements.Dispose.assert_called_once()
