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
