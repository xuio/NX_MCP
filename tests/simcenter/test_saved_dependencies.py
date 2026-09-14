"""Saved membership must not silently follow edited live CAD references."""
from types import SimpleNamespace

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import saved_dependencies
from nx_mcp.workspace import Workspace


@pytest.fixture
def sample(tmp_path, monkeypatch):
    paths = [tmp_path / ('original.' + suffix) for suffix in ('sim', 'fem', 'prt')]
    for p in paths:
        p.write_bytes(b'saved file')
    class Options:
        ComponentLoadMethod = 'original'
        LoadMethod = SimpleNamespace(AsSaved='as_saved')
    class Parts(list):
        LoadOptions = Options()
    session = SimpleNamespace(Parts=Parts([SimpleNamespace(
        FullPath=str(tmp_path / 'edited.prt'), IsModified=True)]))
    class Clone:
        OperationClass = SimpleNamespace(CLONE_OPERATION=0)
        calls = []
        fail_load = False
        def Initialise(self, _): self.calls.append('initialise')
        def AddAssembly(self, _):
            return SimpleNamespace(Failed=self.fail_load, UserAbort=False,
                                   NParts=0, FileNames=[], Statuses=[]), 0
        def StartIteration(self): self.items = iter(map(str, paths))
        def Iterate(self): return next(self.items, '')
        def StopIteration(self): self.calls.append('stop')
        def Terminate(self): self.calls.append('terminate')
    clone = Clone()
    monkeypatch.setattr(saved_dependencies, 'require_solver_idle', lambda: None)
    return session, Workspace(tmp_path), paths, clone


def test_saved_membership_excludes_edited_live_name(sample):
    session, ws, paths, clone = sample
    result = saved_dependencies.inspect_saved(session, ws, paths[0], clone)
    assert result['saved_paths'] == list(map(str, paths))
    assert result['document_flags_preserved'] and result['source_file_preserved']
    assert not result['clone_performed']
    assert clone.calls == ['initialise', 'terminate']
    assert session.Parts.LoadOptions.ComponentLoadMethod == 'original'


def test_load_diagnostics_reject_partial_inventory_and_restore(sample):
    session, ws, paths, clone = sample
    clone.fail_load = True
    with pytest.raises(NXToolError, match='diagnostics'):
        saved_dependencies.inspect_saved(session, ws, paths[0], clone)
    assert clone.calls == ['initialise', 'terminate']
    assert session.Parts.LoadOptions.ComponentLoadMethod == 'original'


@pytest.mark.parametrize('fault', ['duplicate', 'missing_source', 'over_limit', 'iteration'])
def test_invalid_inventory_restores_context(sample, fault):
    session, ws, paths, clone = sample
    values = {'duplicate': [str(paths[0])] * 2,
              'missing_source': [str(paths[1])],
              'over_limit': [str(paths[0])] * 18}
    def start(): clone.items = iter(values.get(fault, []))
    clone.StartIteration = start
    if fault == 'iteration':
        def fail(): raise RuntimeError('native iteration')
        clone.Iterate = fail
    with pytest.raises((NXToolError, RuntimeError)):
        saved_dependencies.inspect_saved(session, ws, paths[0], clone)
    assert clone.calls[-1] == 'terminate'
    assert session.Parts.LoadOptions.ComponentLoadMethod == 'original'
    if fault in ('over_limit', 'iteration'):
        assert 'stop' in clone.calls
