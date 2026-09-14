import pytest
from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.dependencies import select_saved_membership


@pytest.fixture
def data():
    primary = [{'path': 'a.sim', 'roles': ['simulation']},
               {'path': 'b.fem', 'roles': ['mesh']}]
    live = {'rows': primary + [{'path': 'edited.prt', 'roles': ['MasterCadPart']}],
            'unresolved': [{'path': 'edited.prt'}]}
    loaded = [{'path': 'saved.prt', 'fully_loaded': True, 'document_type': 'Part',
               'has_children': False, 'units': 'mm', 'modified': False}]
    return live, ['a.sim', 'b.fem', 'saved.prt'], loaded


def test_selects_saved_cad_and_keeps_actual_metadata(data):
    result = select_saved_membership(*data)
    assert [r['path'] for r in result['rows']] == data[1]
    assert result['rows'][2]['units'] == 'mm'
    assert result['rows'][2]['roles'] == ['saved_cad_membership']
    assert not result['unresolved']
    assert data[0]['rows'][2]['path'] == 'edited.prt'


@pytest.mark.parametrize('fault', ['unloaded', 'partial', 'assembly', 'wrong_type', 'different_fem', 'duplicate'])
def test_rejects_unverified_saved_dependencies(data, fault):
    live, paths, loaded = data
    if fault == 'unloaded': loaded.clear()
    if fault == 'partial': loaded[0]['fully_loaded'] = False
    if fault == 'assembly': loaded[0]['has_children'] = True
    if fault == 'wrong_type': loaded[0]['document_type'] = 'FemPart'
    if fault == 'different_fem': paths[1] = 'other.fem'
    if fault == 'duplicate': paths.append('SAVED.PRT')
    with pytest.raises(NXToolError):
        select_saved_membership(live, paths, loaded)
