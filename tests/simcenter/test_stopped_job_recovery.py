import hashlib

import pytest
from test_job_observer import observed  # noqa: F401
from test_preparation import context  # noqa: F401

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import launch_gate
from nx_mcp.simcenter import stopped_job_recovery as recovery


@pytest.fixture
def stopped(observed, monkeypatch):  # noqa: F811
    workspace, store, deck = observed
    launch_gate.claim_launch_gate(store, "observe-01")
    identity = {"pid": 100, "creation_filetime_100ns": "1000", "executable_path": r"C:\NX\nx.exe"}
    request = {"request_sha256": store.inspect("observe-01")["request_sha256"], "revision": 2,
               "input_sha256": hashlib.sha256(deck.read_bytes()).hexdigest(),
               "log_name": deck.with_suffix('.log').name,
               "log_sha256": hashlib.sha256(deck.with_suffix('.log').read_bytes()).hexdigest(),
               "runtime_identity": identity, "solver_identity": {**identity, "pid": 101},
               "reason": "Verified stopped diagnostic and retired runtime",
               "association_attestation": "operator_verified_job_runtime_and_solver"}
    monkeypatch.setattr(recovery, "require_solver_idle", lambda: {})
    monkeypatch.setattr(recovery, "inspect_process", lambda pid: {"pid": pid, "state": "missing"})
    return workspace, store, deck, request


def test_recovery_preserves_history_outputs_and_future_gate(stopped):
    workspace, store, deck, request = stopped
    before = store.inspect("observe-01")
    assert recovery.recover_stopped_job(store, "observe-01", request)["released"]
    assert store.inspect("observe-01") == before
    assert deck.is_file() and deck.with_suffix('.bun').is_file()
    assert recovery.recover_stopped_job(store, "observe-01", request)["replayed"]
    store.reserve("next-job", {"fixture": True})
    launch_gate.claim_launch_gate(store, "next-job")
    assert recovery.recover_stopped_job(store, "observe-01", request)["other_gate_untouched"]
    with pytest.raises(NXToolError, match="never relaunch"):
        launch_gate.claim_launch_gate(store, "observe-01")


@pytest.mark.parametrize('fault', ['revision', 'hash', 'input', 'log', 'runtime_running',
                                   'solver_running', 'reused', 'unknown', 'busy', 'attestation'])
def test_failed_checks_retain_gate(stopped, monkeypatch, fault):
    workspace, store, deck, request = stopped
    if fault == 'revision':
        request['revision'] = 9
    elif fault == 'hash':
        request['request_sha256'] = '0'*64
    elif fault in ('input', 'log'):
        request[fault+'_sha256'] = '0'*64
    elif fault == 'attestation':
        request['association_attestation'] = 'guess'
    elif fault == 'busy':
        def busy():
            raise NXToolError('NX_SIM_SOLVER_BUSY', 'busy')
        monkeypatch.setattr(recovery, 'require_solver_idle', busy)
    else:
        def inspect(pid):
            identity = request['runtime_identity'] if pid == 100 else request['solver_identity']
            if fault == 'unknown':
                return {'pid': pid, 'state': 'unavailable'}
            if fault == 'reused':
                return {'pid': pid, 'state': 'running', 'identity': {**identity, 'creation_filetime_100ns': '999'}}
            live = pid == (100 if fault == 'runtime_running' else 101)
            return {'pid': pid, 'state': 'running' if live else 'missing', 'identity': identity}
        monkeypatch.setattr(recovery, 'inspect_process', inspect)
    with pytest.raises(NXToolError):
        recovery.recover_stopped_job(store, 'observe-01', request)
    assert workspace.resolve('.nx-sim-launch-owner.json').exists()
    assert not (store._directory('observe-01')/'launch-gate-release.json').exists()


def test_second_verification_detects_new_activity(stopped, monkeypatch):
    workspace, store, _, request = stopped
    calls = []
    def idle():
        calls.append(1)
        if len(calls) == 2:
            raise NXToolError('NX_SIM_SOLVER_BUSY', 'new solver')
    monkeypatch.setattr(recovery, 'require_solver_idle', idle)
    with pytest.raises(NXToolError):
        recovery.recover_stopped_job(store, 'observe-01', request)
    assert workspace.resolve('.nx-sim-launch-owner.json').exists()


def test_crash_after_receipt_can_finish_without_rewriting(stopped, monkeypatch):
    from pathlib import Path
    workspace, store, _, request = stopped
    real = Path.unlink
    gate = workspace.resolve('.nx-sim-launch-owner.json')
    def fail(path, *args, **kwargs):
        if path == gate:
            raise OSError('crash fixture')
        return real(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', fail)
    with pytest.raises(OSError):
        recovery.recover_stopped_job(store, 'observe-01', request)
    receipt = store._directory('observe-01')/'launch-gate-release.json'
    before = receipt.read_bytes()
    monkeypatch.setattr(Path, 'unlink', real)
    assert recovery.recover_stopped_job(store, 'observe-01', request)['replayed']
    assert receipt.read_bytes() == before
