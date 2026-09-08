import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.prepared_input import capture_prepared_input, validate_prepared_input
from nx_mcp.workspace import Workspace


@pytest.fixture
def setup(tmp_path):
    (tmp_path / "mesh.fem").write_bytes(b"mesh version one")
    (tmp_path / "input.xml").write_text('<SolutionFile class="Flow"/>')
    docs = [{"path": "mesh.fem", "modified": False, "fully_loaded": True}]
    workspace = Workspace(tmp_path)
    return workspace, docs, capture_prepared_input(workspace, "input.xml", docs)


def test_matching_snapshot_is_not_solve_acceptance(setup):
    workspace, docs, prepared = setup
    result = validate_prepared_input(workspace, prepared, docs)
    assert result["prepared_inputs_match"]
    assert result["solve_readiness"] == "not_established"


def test_unsaved_geometry_rejects_unchanged_disk_hash(setup):
    workspace, docs, prepared = setup
    docs[0]["modified"] = True
    with pytest.raises(NXToolError) as exc:
        validate_prepared_input(workspace, prepared, docs)
    assert exc.value.code == "NX_SIM_REVISION_CHANGED"
    with pytest.raises(NXToolError) as exc:
        capture_prepared_input(workspace, "input.xml", docs)
    assert exc.value.code == "NX_SIM_REVISION_UNSAVED"


def test_changed_mesh_or_input_rejected(setup):
    workspace, docs, prepared = setup
    workspace.resolve("mesh.fem").write_bytes(b"mesh version two")
    with pytest.raises(NXToolError) as exc:
        validate_prepared_input(workspace, prepared, docs)
    assert exc.value.code == "NX_SIM_REVISION_CHANGED"
    workspace.resolve("mesh.fem").write_bytes(b"mesh version one")
    workspace.resolve("input.xml").write_text('<SolutionFile class="Thermal"/>')
    with pytest.raises(NXToolError) as exc:
        validate_prepared_input(workspace, prepared, docs)
    assert exc.value.code == "NX_SIM_INPUT_CHANGED"


def test_budget_and_dependency_set_enforced(setup):
    workspace, docs, prepared = setup
    with pytest.raises(ValueError):
        capture_prepared_input(workspace, "input.xml", docs, maximum_bytes=1)
    with pytest.raises(NXToolError) as exc:
        validate_prepared_input(
            workspace,
            prepared,
            docs + [{"path": "new.prt", "modified": False, "fully_loaded": True}],
        )
    assert exc.value.code == "NX_SIM_REVISION_CHANGED"
