from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from nx_mcp.runtime import NXToolError


@pytest.fixture
def fixture(monkeypatch):
    import sys

    from nx_mcp.simcenter import remesh

    class FemPart:
        pass

    class SimPart:
        pass

    fem, dependent, unrelated = FemPart(), SimPart(), SimPart()
    fem.FullPath, dependent.FullPath, unrelated.FullPath = "fixture.fem", "fixture.sim", "other.sim"
    dependent.FemPart, unrelated.FemPart = fem, object()
    cae = NS(FemPart=FemPart, SimPart=SimPart)
    monkeypatch.setitem(sys.modules, "NXOpen", NS(CAE=cae))
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr("nx_mcp.simcenter.solver_guard.require_solver_idle", lambda: {})
    meshes = [NS(Tag=1), NS(Tag=2)]
    state = {"count": 100, "commits": [], "fail": None}
    builders = []

    def create(mesh):
        def commit():
            state["commits"].append(mesh.Tag)
            state["count"] += 10
            if state["fail"] == mesh.Tag:
                raise RuntimeError("native failure after mesh mutation")
            return [mesh]

        builder = NS(CommitMesh=commit, Destroy=Mock())
        builders.append(builder)
        return builder

    fem.BaseFEModel = NS(MeshManager=NS(GetMeshes=lambda: meshes, CreateMesh3dTetBuilder=create))
    fem.PartUnits = 1

    class Parts(list):
        BaseWork = fem

    parts = Parts([fem, dependent, unrelated])

    def undo(*_):
        state["count"] = 100

    executor = NS(
        session=NS(Parts=parts, SetUndoMark=lambda *a: 1, UndoToMark=undo, DeleteUndoMark=Mock()),
        nxopen=NS(BasePart=NS(Units=NS(Millimeters=1)), Session=NS(MarkVisibility=NS(Visible=1))),
        objects=NS(invalidate_part=Mock()),
        _part_id=lambda p: p.FullPath,
    )
    monkeypatch.setattr(remesh, "settings", lambda *a: {"size_mm": 5})
    monkeypatch.setattr(
        "nx_mcp.simcenter.mesh_plan.mesh_counts",
        lambda *a: {"elements": state["count"], "nodes": 40},
    )
    return remesh, executor, fem, state, builders


def test_late_failure_rolls_back_and_retires_only_dependent_references(fixture):
    module, executor, fem, state, builders = fixture
    state["fail"] = 2
    with pytest.raises(NXToolError) as error:
        module.regenerate(executor, fem)
    assert error.value.code == "NX_SIM_REMESH_FAILED"
    assert error.value.details["mutation_outcome"] == "rolled_back"
    assert state["commits"] == [1, 2] and state["count"] == 100
    assert [c.args[0] for c in executor.objects.invalidate_part.call_args_list] == [
        "fixture.fem",
        "fixture.sim",
    ]
    for builder in builders:
        builder.Destroy.assert_called_once()


def test_success_returns_actual_counts_and_retires_references(fixture):
    module, executor, fem, state, builders = fixture
    result = module.regenerate(executor, fem)
    assert result["before_counts"]["elements"] == 100
    assert result["counts"]["elements"] == 120
    assert result["results_stale"] is True
    assert result["quality_validation"] == "not_performed"
    assert executor.objects.invalidate_part.call_count == 2


def test_unsupported_mesh_is_rejected_without_mutation_or_invalidation(fixture, monkeypatch):
    module, executor, fem, state, builders = fixture
    monkeypatch.setattr(module, "settings", Mock(side_effect=ValueError("unsupported mesh")))
    with pytest.raises(NXToolError) as error:
        module.regenerate(executor, fem)
    assert error.value.details["mutation_outcome"] == "not_started"
    assert state["commits"] == [] and not builders
    executor.objects.invalidate_part.assert_not_called()


def test_failed_undo_reports_partial_and_still_retires_references(fixture):
    module, executor, fem, state, builders = fixture
    state["fail"] = 1
    executor.session.UndoToMark = Mock(side_effect=RuntimeError("undo failed"))
    with pytest.raises(NXToolError) as error:
        module.regenerate(executor, fem)
    assert error.value.details["mutation_outcome"] == "partial"
    assert executor.objects.invalidate_part.call_count == 2


@pytest.mark.asyncio
async def test_public_tools_expose_typed_parameters_and_operation_identity(tmp_path, monkeypatch):
    from nx_mcp.server import create_server
    from nx_mcp.workspace import Workspace

    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(NS(), Workspace(tmp_path), enable_experimental=True)
    tools = {t.name: t for t in await server.list_tools()}
    for name in ("nx_sim_remesh", "nx_sim_face_size_edit"):
        assert "operation_id" in tools[name].inputSchema["properties"]
        assert tools[name].inputSchema["properties"]["document"]["type"] == "string"
    assert tools["nx_sim_face_size_edit"].inputSchema["properties"]["control"]["type"] == "string"
    schema = tools["nx_sim_remesh"].inputSchema
    assert "size_mm" in schema["properties"]
    assert "size_mm" not in schema.get("required", [])


@pytest.mark.parametrize("size", [True, 0, -1, float("nan"), float("inf"), 10001, "2"])
def test_invalid_global_size_rejected_before_mutation(fixture, size):
    module, executor, fem, state, builders = fixture
    with pytest.raises(NXToolError, match="size_mm"):
        module.regenerate(executor, fem, size_mm=size)
    assert state["commits"] == [] and builders == []
    executor.objects.invalidate_part.assert_not_called()


@pytest.mark.parametrize("fail", [None, 2])
def test_global_size_readback_and_atomic_rollback(fixture, monkeypatch, fail):
    module, executor, fem, state, builders = fixture
    manager = fem.BaseFEModel.MeshManager
    sizes = {1: 5.0, 2: 7.0}
    original = dict(sizes)
    unit = object()
    fem.UnitCollection = NS(FindObject=lambda name: unit if name == "MilliMeter" else None)
    create = manager.CreateMesh3dTetBuilder

    def build(mesh):
        builder = create(mesh)

        def set_size(key, value, requested_unit):
            assert key == "quad mesh overall edge size" and requested_unit is unit
            sizes[mesh.Tag] = value

        builder.PropertyTable = NS(SetBaseScalarWithDataPropertyValue=set_size)
        return builder

    manager.CreateMesh3dTetBuilder = build
    monkeypatch.setattr(
        module,
        "settings",
        lambda m, mesh: {
            "size_mm": sizes[mesh.Tag],
            "element_type": "tetra",
            "body_tags": [mesh.Tag + 10],
        },
    )
    undo = executor.session.UndoToMark

    def restore(*args):
        undo(*args)
        sizes.update(original)

    executor.session.UndoToMark = restore
    state["fail"] = fail
    if fail:
        with pytest.raises(NXToolError) as error:
            module.regenerate(executor, fem, size_mm=2)
        assert error.value.details["mutation_outcome"] == "rolled_back"
        assert sizes == original
    else:
        result = module.regenerate(executor, fem, size_mm=2)
        assert result["previous_sizes_mm"] == [5, 7]
        assert result["global_size_changed"] is True
        assert [r["size_mm"] for r in result["settings"]] == [2, 2]
        assert [r["body_tags"] for r in result["settings"]] == [[11], [12]]
    assert executor.objects.invalidate_part.call_count == 2
    for builder in builders:
        builder.Destroy.assert_called_once()
