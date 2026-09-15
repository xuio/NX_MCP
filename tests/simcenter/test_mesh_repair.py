"""Boundary-preservation and quality acceptance tests; not native NX validation."""
import copy

import pytest

from nx_mcp.simcenter.mesh_repair import boundary_digest, validate_improvement

POINTS = {1: (0, 0, 0), 2: (1, 0, 0), 3: (0, 1, 0), 4: (0, 0, 1),
          5: (0, 0, -1), 6: (0.1, 0.1, 0.1)}


def test_shared_face_internal_within_mesh_but_preserved_between_meshes():
    same = boundary_digest([("a", [1, 2, 3, 4]), ("a", [1, 2, 3, 5])], POINTS.__getitem__)
    separate = boundary_digest([("a", [1, 2, 3, 4]), ("b", [1, 2, 3, 5])], POINTS.__getitem__)
    assert same['triangles'] == 6 and separate['triangles'] == 8
    assert same['sha256'] != separate['sha256']


def test_interior_refinement_preserves_boundary_but_movement_does_not():
    initial = boundary_digest([('a', [1, 2, 3, 4])], POINTS.__getitem__)
    refined = boundary_digest([('a', v) for v in [[1, 2, 3, 6], [1, 2, 4, 6],
                                                [1, 3, 4, 6], [2, 3, 4, 6]]], POINTS.__getitem__)
    assert refined == initial
    moved = {**POINTS, 4: (0, 0, 1.00000001)}
    assert boundary_digest([('a', [1, 2, 3, 4])], moved.__getitem__) != initial


@pytest.mark.parametrize('cells', [
    [('a', [1, 2, 3, 4]), ('a', [4, 3, 2, 1])],
    [('a', [1, 2, 3, 4]), ('a', [1, 2, 3, 5]), ('a', [1, 2, 3, 6])],
    [('a', [1, 1, 2, 3])], [('a', [1, 2, 3])], [],
])
def test_rejects_duplicate_nonmanifold_or_unsupported_connectivity(cells):
    with pytest.raises(ValueError):
        boundary_digest(cells, POINTS.__getitem__)


def quality(errors=2):
    return {'settings': {'error_limit': 100}, 'element_count': 10,
            'tests': [{'type': k, 'errors': errors if k == 'AspectRatio' else 0, 'warnings': 0}
                      for k in ['AspectRatio', 'JacobianSign', 'JacobianZero', 'Volume']]}


def test_accepts_improvement_with_unchanged_criteria():
    validate_improvement(quality(2), quality(1))


@pytest.mark.parametrize('failure', ['criteria', 'no_improvement', 'jacobian', 'warning', 'empty'])
def test_rejects_quality_regressions(failure):
    before, after = quality(2), quality(1)
    if failure == 'criteria':
        after['settings']['error_limit'] = 1000
    elif failure == 'no_improvement':
        after = copy.deepcopy(before)
    elif failure == 'jacobian':
        after['tests'][1]['errors'] = 1
    elif failure == 'warning':
        after['tests'][0]['warnings'] = 1
    else:
        after['element_count'] = 0
    with pytest.raises(ValueError):
        validate_improvement(before, after)


@pytest.mark.parametrize('mode,outcome', [('good', None), ('boundary', 'rolled_back'),
                                        ('native_error', 'rolled_back'), ('bad_undo', 'partial')])
def test_native_transaction_restores_rejected_changes_and_invalidates_refs(monkeypatch, mode, outcome):
    import sys
    from types import ModuleType
    from types import SimpleNamespace as NS

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter import mesh_repair, mesh_state, remesh, solver_guard
    from nx_mcp.simcenter import quality as native_quality

    events = []
    state = {'changed': False}

    class Fem:
        PartUnits = 1

    class Sim:
        pass

    class Parts(list):
        pass

    fem, sim = Fem(), Sim()
    sim.FemPart = fem
    cae = ModuleType('NXOpen.CAE')
    cae.FemPart, cae.SimPart = Fem, Sim
    cae.ModelCheck = NS(TestValueTypes=NS(TestType=NS(AspectRatio=1)))
    nx = ModuleType('NXOpen')
    nx.CAE = cae
    monkeypatch.setitem(sys.modules, 'NXOpen', nx)
    monkeypatch.setitem(sys.modules, 'NXOpen.CAE', cae)
    parts = Parts([fem, sim])
    parts.BaseWork = fem

    def undo(*args):
        events.append('undo')
        if mode != 'bad_undo':
            state['changed'] = False

    session = NS(Parts=parts, SetUndoMark=lambda *args: 1, UndoToMark=undo,
                 DeleteUndoMark=lambda *args: None)
    executor = NS(session=session, nxopen=NS(BasePart=NS(Units=NS(Millimeters=1)),
                  Session=NS(MarkVisibility=NS(Visible=1))), _part_id=lambda p: id(p),
                  objects=NS(invalidate_part=lambda p: events.append(('invalidate', p))))
    mesh = NS(Tag=100)
    manager = NS(GetMeshes=lambda: [mesh])
    label_map = NS(GetElement=lambda n: n, Dispose=lambda: events.append('map_disposed'))
    fem.BaseFEModel = NS(MeshManager=manager, FeelementLabelMap=label_map)

    def attempt(types, targets):
        assert types == [1] and targets == [7]
        state['changed'] = True
        if mode == 'native_error':
            raise RuntimeError('native failed')

    builder = NS(SelectionList=NS(Add=lambda meshes: None),
                 ExecuteCheck=lambda: NS(Dispose=lambda: events.append('result_disposed')),
                 AttemptFixFailingSelectedElements=attempt,
                 Destroy=lambda: events.append('builder_destroyed'))
    fem.ModelCheckMgr = NS(CreateElementQualityCheckBuilder=lambda: builder)
    monkeypatch.setattr(solver_guard, 'require_solver_idle', lambda: None)
    monkeypatch.setattr(native_quality, 'inspect_elements', lambda f, labels: {'count': 1})
    monkeypatch.setattr(remesh, 'settings', lambda *args: {'size_mm': 3})
    monkeypatch.setattr(mesh_state, 'capture', lambda *args, **kwargs: {'changed': state['changed']})
    monkeypatch.setattr(mesh_repair, 'capture_boundary',
                        lambda *args: {'hash': 2 if state['changed'] and mode in ['boundary', 'bad_undo'] else 1})
    monkeypatch.setattr(native_quality, 'check_mesh_quality', lambda *args: quality(1 if state['changed'] else 2))
    if outcome is None:
        result = mesh_repair.repair(executor, fem, [7], 100)
        assert result['after']['tests'][0]['errors'] == 1
        assert result['solver_launched'] is False and state['changed']
        assert 'undo' not in events
    else:
        with pytest.raises(NXToolError) as caught:
            mesh_repair.repair(executor, fem, [7], 100)
        assert caught.value.details['mutation_outcome'] == outcome
        assert 'undo' in events
    assert all(v in events for v in ['map_disposed', 'result_disposed', 'builder_destroyed'])
    assert ('invalidate', id(fem)) in events and ('invalidate', id(sim)) in events
