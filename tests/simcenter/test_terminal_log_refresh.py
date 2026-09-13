import hashlib
import os

import pytest
from test_job_observer import observed  # noqa: F401
from test_preparation import context  # noqa: F401

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import job_observer, launch_gate, solver_guard
from nx_mcp.simcenter import terminal_log_refresh as refresh


@pytest.fixture
def late_footer(observed, monkeypatch):  # noqa: F811
    workspace, store, deck = observed
    log = deck.with_suffix('.log')
    stamp = log.stat().st_mtime
    prefix = b'failure diagnosis\r\n Solve completed at:\r\n ==='
    log.write_bytes(prefix)
    os.utime(log, (stamp, stamp))
    job_observer.observe_terminal(workspace, 'observe-01')
    launch_gate.claim_launch_gate(store, 'observe-01')
    log.write_bytes(prefix+b'==\r\n Time: Mon Sep 14 01:39:24 2026\r\n\r\n')
    monkeypatch.setattr(refresh, 'require_solver_idle', lambda: {'solver_processes': 0})
    monkeypatch.setattr(solver_guard, 'require_solver_idle', lambda: {'solver_processes': 0})
    return workspace, store, deck


def run(store, deck):
    return refresh.refresh_terminal_log(store, 'observe-01', expected_revision=3,
        expected_log_sha256=hashlib.sha256(deck.with_suffix('.log').read_bytes()).hexdigest())


def test_refresh_retains_history_and_enables_verified_release(late_footer):
    workspace, store, deck = late_footer
    old = (store._directory('observe-01')/'state-00003.json').read_bytes()
    with pytest.raises(NXToolError, match='Terminal artifacts changed'):
        launch_gate.release_launch_gate(store, 'observe-01')
    result = run(store, deck)
    assert result['revision'] == 4 and not result['results_validated']
    assert result['evidence']['terminal_log_refresh']['exact_prefix_verified']
    assert (store._directory('observe-01')/'state-00003.json').read_bytes() == old
    assert workspace.resolve('.nx-sim-launch-owner.json').exists()
    assert launch_gate.release_launch_gate(store, 'observe-01')['released']
    assert deck.with_suffix('.bun').read_bytes() == b'native result fixture'
    with pytest.raises(NXToolError):
        run(store, deck)


@pytest.mark.parametrize('change', ['prefix', 'append', 'result', 'input', 'no_append', 'bad_date', 'missing_result', 'wrong_gate'])
def test_changed_evidence_preserves_gate_and_history(late_footer, change):
    workspace, store, deck = late_footer
    log = deck.with_suffix('.log')
    raw = log.read_bytes()
    if change == 'prefix':
        log.write_bytes(raw.replace(b'failure', b'success'))
    elif change == 'append':
        log.write_bytes(raw+b'Fatal error after completion\n')
    elif change == 'result':
        deck.with_suffix('.bun').write_bytes(b'changed result')
    elif change == 'input':
        deck.write_bytes(deck.read_bytes()+b' ')
    elif change == 'no_append':
        log.write_bytes(raw[:store.inspect('observe-01')['record']['evidence']['log']['bytes']])
    elif change == 'bad_date':
        log.write_bytes(raw.replace(b'01:39:24', b'99:39:24'))
    elif change == 'missing_result':
        deck.with_suffix('.bun').unlink()
    else:
        workspace.resolve('.nx-sim-launch-owner.json').write_text('{}')
    with pytest.raises((NXToolError, OSError)):
        run(store, deck)
    assert store.inspect('observe-01')['revision'] == 3
    assert workspace.resolve('.nx-sim-launch-owner.json').exists()


@pytest.mark.parametrize('when', [1, 2])
def test_solver_busy_on_either_check_retains_history(late_footer, monkeypatch, when):
    workspace, store, deck = late_footer
    calls = []
    def check():
        calls.append(True)
        if len(calls) == when:
            raise NXToolError('NX_SIM_SOLVER_BUSY', 'busy')
        return {}
    monkeypatch.setattr(refresh, 'require_solver_idle', check)
    with pytest.raises(NXToolError):
        run(store, deck)
    assert store.inspect('observe-01')['revision'] == 3


def test_artifact_changes_between_snapshots_fail(late_footer, monkeypatch):
    workspace, store, deck = late_footer
    calls = []
    def check():
        calls.append(True)
        if len(calls) == 2:
            deck.with_suffix('.log').write_bytes(deck.with_suffix('.log').read_bytes()+b'late')
        return {}
    monkeypatch.setattr(refresh, 'require_solver_idle', check)
    with pytest.raises(NXToolError):
        run(store, deck)
    assert store.inspect('observe-01')['revision'] == 3


def test_uninspected_hash_fails(late_footer):
    workspace, store, deck = late_footer
    with pytest.raises(NXToolError):
        refresh.refresh_terminal_log(store, 'observe-01', expected_revision=3,
                                     expected_log_sha256='0'*64)
    assert store.inspect('observe-01')['revision'] == 3
