"""Large native decks retain the same identity and rejection guarantees."""
import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import mesh_guard, prepared_input, solver_log
from nx_mcp.simcenter.validation_limits import MAX_INPUT_BYTES, MAX_MESH_ENTITIES
from nx_mcp.workspace import Workspace


def test_deck_above_old_limit_prepares_revalidates_and_detects_change(tmp_path):
    deck = tmp_path / 'input.xml'
    deck.write_bytes(b'<SolutionFile><!--' + b' ' * (65 * 1024 * 1024) + b'--></SolutionFile>')
    (tmp_path / 'mesh.fem').write_bytes(b'saved mesh')
    workspace = Workspace(tmp_path)
    docs = [{'path': 'mesh.fem', 'modified': False, 'fully_loaded': True}]
    snapshot = prepared_input.capture_prepared_input(workspace, 'input.xml', docs)
    assert snapshot['input']['bytes'] > 64 * 1024 * 1024
    assert prepared_input.validate_prepared_input(workspace, snapshot, docs)['prepared_inputs_match']
    with deck.open('ab') as stream:
        stream.write(b'\n')
    with pytest.raises(NXToolError) as error:
        prepared_input.validate_prepared_input(workspace, snapshot, docs)
    assert error.value.code == 'NX_SIM_INPUT_CHANGED'


def test_finite_input_limit_still_rejects_before_parsing(monkeypatch):
    raw = b'<SolutionFile/>'
    monkeypatch.setattr(solver_log, 'MAX_INPUT_BYTES', len(raw))
    assert solver_log.inspect_input_xml(raw)['state'] == 'well_formed'
    assert solver_log.inspect_input_xml(raw + b' ')['reason'] == 'input_exceeds_validation_limit'


def test_explicit_mesh_budget_supports_refined_case_but_remains_bounded():
    mesh_guard.validate_budget(1_745_207)
    mesh_guard.validate_budget(MAX_MESH_ENTITIES)
    with pytest.raises(NXToolError):
        mesh_guard.validate_budget(MAX_MESH_ENTITIES + 1)
    assert MAX_INPUT_BYTES == 256 * 1024 * 1024
