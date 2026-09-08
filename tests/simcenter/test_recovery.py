from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.recovery import authoring_snapshot, rollback_creation


def test_destroy_failure_does_not_skip_undo():
    sim = NS(Simulation=NS(Loads=[], Constraints=[]), Expressions=[])
    before = authoring_snapshot(sim)
    events = []

    def destroy():
        events.append("destroy")
        raise RuntimeError("cleanup failed")

    session = NS(
        UndoToMark=lambda *a: events.append("undo"),
        DeleteUndoMark=lambda *a: events.append("delete"),
    )
    with pytest.raises(NXToolError) as exc:
        rollback_creation(
            session, sim, 1, NS(Destroy=destroy), before, RuntimeError("creation failed")
        )
    assert events == ["destroy", "undo", "delete"]
    assert exc.value.details["creation_snapshot_restored"]
    assert exc.value.details["mutation_outcome"] == "partial"


def test_verified_rollback_reports_original_native_code():
    sim = NS(Simulation=NS(Loads=[], Constraints=[]), Expressions=[])
    error = RuntimeError("native failure")
    error.ErrorCode = 123
    session = NS(UndoToMark=lambda *a: None, DeleteUndoMark=lambda *a: None)
    with pytest.raises(NXToolError) as exc:
        rollback_creation(session, sim, 1, None, authoring_snapshot(sim), error)
    assert exc.value.nx_code == 123
    assert exc.value.details["mutation_outcome"] == "rolled_back"


def test_unrestored_creation_keeps_checkpoint():
    sim = NS(Simulation=NS(Loads=[], Constraints=[]), Expressions=[])
    before = authoring_snapshot(sim)
    sim.Expressions.append(NS(Tag=99))

    def unexpected(*args):
        raise AssertionError("checkpoint must remain")

    session = NS(UndoToMark=lambda *a: None, DeleteUndoMark=unexpected)
    with pytest.raises(NXToolError) as exc:
        rollback_creation(session, sim, 1, None, before, RuntimeError("failed"))
    assert exc.value.code == "NX_SIM_RECOVERY_INCOMPLETE"
    assert not exc.value.details["creation_snapshot_restored"]
