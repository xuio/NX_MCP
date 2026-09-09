import pytest

from nx_mcp.simcenter.local_size import validate


@pytest.mark.parametrize(
    "faces,size",
    [
        ([], 1),
        (["a"], True),
        (["a"], 0),
        (["a"], float("nan")),
        (["a"], 10001),
        ("a", 1),
        (["a"] * 1001, 1),
    ],
)
def test_invalid_requests_rejected_before_nx(faces, size):
    with pytest.raises(ValueError):
        validate(faces, size)


def test_valid_face_size():
    validate(["a", "b"], 0.1)


@pytest.mark.asyncio
async def test_face_size_schema_has_units_and_operation_identity(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from nx_mcp.server import create_server
    from nx_mcp.workspace import Workspace

    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(SimpleNamespace(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_face_size")
    assert set(tool.inputSchema["required"]) == {"document", "faces", "size_mm"}
    assert "operation_id" in tool.inputSchema["properties"]


def test_face_size_inspector_reports_expression_units_and_faces(monkeypatch):
    import sys
    from types import SimpleNamespace as NS
    from unittest.mock import Mock

    from nx_mcp.simcenter.mesh_controls import inspect_control

    cae = NS(MeshControlBuilder=NS(Types=NS(FaceDensitySize=4, BoundaryLayers=10)))
    monkeypatch.setitem(sys.modules, "NXOpen", NS(CAE=cae))
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    builder = NS(
        MainType=4,
        OverallSize=NS(
            Units=NS(Name="MilliMeter"),
            GetValueUsingUnits=lambda _: 1.0,
            GetFormula=lambda: "fine_size",
        ),
        Selection=NS(GetArray=lambda: ["face"]),
        Destroy=Mock(),
    )
    fem = NS(
        BaseFEModel=NS(MeshControls=NS(CreateBuilder=lambda _: builder)),
        UnitCollection=NS(Convert=lambda a, b, v: v, FindObject=lambda _: None),
    )
    nx = NS(Expression=NS(UnitsOption=NS(Expression=1)))
    row = inspect_control(fem, "control", nx, lambda obj, *args: {"id": obj})
    assert row["kind"] == "face_size" and row["size_mm"] == 1
    assert row["size_expression"] == "fine_size"
    assert row["faces"] == [{"id": "face"}] and row["mesh_effect"] == "not_verified"
    builder.Destroy.assert_called_once()
