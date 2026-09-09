import sys
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from nx_mcp.simcenter.mesh_controls import inspect_control


def test_control_reader_destroys_builder_on_failure(monkeypatch):
    cae = NS(MeshControlBuilder=NS(Types=NS(BoundaryLayers=1)))
    monkeypatch.setitem(sys.modules, "NXOpen", NS(CAE=cae))
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    builder = NS(
        MainType=1,
        FirstLayerThickness=NS(
            GetValueUsingUnits=Mock(side_effect=RuntimeError("native getter failed"))
        ),
        Destroy=Mock(),
    )
    fem = NS(BaseFEModel=NS(MeshControls=NS(CreateBuilder=lambda _: builder)))
    nx = NS(Expression=NS(UnitsOption=NS(Expression=1)))
    with pytest.raises(RuntimeError, match="native getter failed"):
        inspect_control(fem, object(), nx, lambda *args: {"id": "control"})
    builder.Destroy.assert_called_once()


@pytest.mark.asyncio
async def test_controls_surface_is_explicit_about_mutation_and_units(tmp_path, monkeypatch):
    from nx_mcp.server import create_server
    from nx_mcp.workspace import Workspace

    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(NS(), Workspace(tmp_path), enable_experimental=True)
    tools = {t.name: t for t in await server.list_tools()}
    assert "operation_id" in tools["nx_sim_boundary_layers"].inputSchema["properties"]
    assert "first_layer_mm" in tools["nx_sim_boundary_layers"].inputSchema["properties"]
    assert "operation_id" not in tools["nx_sim_mesh_controls"].inputSchema["properties"]
    assert tools["nx_sim_mesh_controls"].annotations.readOnlyHint is True


def test_control_reader_preserves_values_units_and_target_cardinality(monkeypatch):
    cae = NS(MeshControlBuilder=NS(Types=NS(BoundaryLayers=1)))
    monkeypatch.setitem(sys.modules, "NXOpen", NS(CAE=cae))
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    expr = NS(
        Units=NS(Name="MilliMeter"),
        GetValueUsingUnits=lambda _: 0.1,
        GetFormula=lambda: "layer_height",
    )
    builder = NS(
        MainType=1,
        FirstLayerThickness=expr,
        NumberOfLayers=3,
        GrowthRate=1.2,
        HeightDefinedBy=2,
        BlDimension=3,
        Selection=NS(GetArray=lambda: ["face1", "face2"]),
        BlTargetSelection=NS(GetArray=lambda: []),
        Destroy=Mock(),
    )
    fem = NS(
        BaseFEModel=NS(MeshControls=NS(CreateBuilder=lambda _: builder)),
        UnitCollection=NS(FindObject=lambda name: name, Convert=lambda a, b, v: v),
    )
    nx = NS(Expression=NS(UnitsOption=NS(Expression=1)))
    result = inspect_control(fem, "control", nx, lambda obj, *args: {"id": obj})
    assert result["first_layer_mm"] == 0.1
    assert result["thickness_expression"] == "layer_height"
    assert result["layers"] == 3 and result["growth_rate"] == 1.2
    assert result["faces"] == [{"id": "face1"}, {"id": "face2"}]
    assert result["body_targets"] == [] and result["mesh_effect"] == "not_verified"
    builder.Destroy.assert_called_once()
