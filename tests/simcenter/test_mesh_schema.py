import sys
from types import ModuleType
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.mesh_schema import inspect


@pytest.fixture
def rig(monkeypatch):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")
    cae.FemPart = type("FemPart", (), {})
    nx.CAE = cae
    nx.BasePart = NS(Units=NS(Millimeters=1))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr("nx_mcp.simcenter.solver_guard.require_solver_idle", Mock())
    fem = cae.FemPart()
    fem.Tag, fem.PartUnits, fem.IsModified = 1, 1, False
    fem.Expressions, fem.Bodies = [], [NS(Tag=4)]
    props = NS(GetPropertyCount=lambda: 1, GetPropertyNameByIndex=lambda _: "surface meshing method",
               GetPropertyDescriptorName=lambda _: "Method\nA\nB")
    builder = NS(PropertyTable=props, Destroy=Mock(), AutoSizeOption=True,
                 AutoResetOption=False, CheckElementSizeOption=True,
                 ElementType=NS(GetElementTypeNames=lambda: ["Fluid Linear Tetrahedron"],
                                ElementTypeName="Fluid Linear Tetrahedron"))
    manager = NS(GetMeshes=lambda: [], GetMeshCollectors=lambda: [],
                 CreateMesh3dTetBuilder=Mock(return_value=builder))
    fem.BaseFEModel = NS(MeshManager=manager, MeshControls=[])

    class Parts(list):
        BaseWork = fem

    session = NS(Parts=Parts([fem]), SetUndoMark=Mock(return_value=42),
                 UndoToMark=Mock(), DeleteUndoMark=Mock())
    nx.Session = NS(GetSession=lambda: session, MarkVisibility=NS(Invisible=0))
    monkeypatch.setattr("nx_mcp.simcenter.properties.read_properties",
                        lambda *_: [{"name": "surface meshing method", "value": 0}])
    return NS(nxopen=nx, session=session), fem, builder


def test_readback_without_commit_and_restoration(rig):
    executor, fem, builder = rig
    result = inspect(executor, fem)
    assert result["state_restored"] and result["generated_meshes"] == 0
    assert result["properties"][0]["value"] == 0
    assert result["property_descriptors"][0]["descriptor"] == "Method\nA\nB"
    builder.Destroy.assert_called_once()
    executor.session.UndoToMark.assert_called_once_with(42, None)


@pytest.mark.parametrize("failure", ["inactive", "units", "solver"])
def test_preconditions_do_not_create_builder(rig, monkeypatch, failure):
    executor, fem, _ = rig
    if failure == "inactive":
        executor.session.Parts.BaseWork = None
    elif failure == "units":
        fem.PartUnits = 2
    else:
        monkeypatch.setattr("nx_mcp.simcenter.solver_guard.require_solver_idle",
                            Mock(side_effect=NXToolError("BUSY", "solver busy")))
    with pytest.raises(NXToolError):
        inspect(executor, fem)
    fem.BaseFEModel.MeshManager.CreateMesh3dTetBuilder.assert_not_called()


@pytest.mark.parametrize("failure", ["create", "read", "destroy"])
def test_failures_still_undo(rig, monkeypatch, failure):
    executor, fem, builder = rig
    if failure == "create":
        fem.BaseFEModel.MeshManager.CreateMesh3dTetBuilder.side_effect = RuntimeError("create")
    elif failure == "read":
        monkeypatch.setattr("nx_mcp.simcenter.properties.read_properties",
                            Mock(side_effect=RuntimeError("read")))
    else:
        builder.Destroy.side_effect = RuntimeError("destroy")
    with pytest.raises(RuntimeError):
        inspect(executor, fem)
    executor.session.UndoToMark.assert_called_once()
    if failure != "create":
        builder.Destroy.assert_called_once()


def test_leaked_inventory_is_partial(rig):
    executor, fem, builder = rig
    builder.Destroy.side_effect = lambda: fem.Expressions.append(NS(Tag=99))
    with pytest.raises(NXToolError) as error:
        inspect(executor, fem)
    assert error.value.details["mutation_outcome"] == "partial"


def test_property_limit_prevents_unbounded_inspection(rig):
    executor, fem, builder = rig
    builder.PropertyTable.GetPropertyCount = lambda: 513
    with pytest.raises(ValueError, match="512"):
        inspect(executor, fem)
    builder.Destroy.assert_called_once()
    executor.session.UndoToMark.assert_called_once()


@pytest.mark.asyncio
async def test_public_read_only_schema(tmp_path, monkeypatch):
    from nx_mcp.server import create_server
    from nx_mcp.workspace import Workspace

    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    tool = next(t for t in await create_server(Mock(), Workspace(tmp_path),
                enable_experimental=True).list_tools() if t.name == "nx_sim_mesh_schema")
    assert tool.annotations.readOnlyHint
    assert "operation_id" not in tool.inputSchema["properties"]
