from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.material_assignment import assign_material


def setup(monkeypatch, *, mismatch=False, rollback_fails=False):
    import nx_mcp.simcenter.material_assignment as module
    import nx_mcp.simcenter.solver_guard as guard

    monkeypatch.setattr(guard, "require_solver_idle", lambda: None)
    events = []
    material = object()
    options = NS(Dispose=lambda: events.append("dispose"))
    table = NS(SetPhysicalMaterialPropertyValue=lambda *args: events.append("assign"))
    collector = NS(
        CollectorNeutralType="Solid",
        ElementPropertyTable=NS(
            GetNamedPropertyTablePropertyValue=lambda _: NS(PropertyTable=table)
        ),
    )
    fem = NS(
        PartUnits=1,
        BaseFEModel=NS(MeshManager=NS(GetMeshCollectors=lambda: [collector])),
        MaterialManager=NS(PhysicalMaterials=[material]),
        NewMaterialOptions=lambda: options,
    )
    before = {"state_sha256": "initial", "orientation": {"native_selector": 0}}
    after = {
        "state_sha256": "new",
        "orientation": before["orientation"],
        "material": {"id": "wrong" if mismatch else "material"},
        "material_inherited": False,
    }
    states = iter([before, after])
    monkeypatch.setattr(module, "inspect_collector", lambda *args: next(states))

    def undo(*args):
        events.append("undo")
        if rollback_fails:
            raise RuntimeError("rollback failed")

    session = NS(
        Parts=NS(
            SetDisplay=lambda *args: (None, None), SetWork=lambda *args: events.append("activate")
        ),
        SetUndoMark=lambda *args: 1,
        UndoToMark=undo,
        DeleteUndoMark=lambda *args: events.append("delete_mark"),
    )
    nx = NS(BasePart=NS(Units=NS(Millimeters=1)), Session=NS(MarkVisibility=NS(Visible=1)))
    return (session, nx, fem, collector, material, lambda *args: {"id": "material"}), events


def test_conflict_rejected_before_activation(monkeypatch):
    args, events = setup(monkeypatch)
    with pytest.raises(NXToolError) as error:
        assign_material(*args, "stale")
    assert error.value.code == "NX_SIM_REVISION_MISMATCH" and events == []


@pytest.mark.parametrize("rollback_fails,outcome", [(False, "rolled_back"), (True, "partial")])
def test_readback_mismatch_rolls_back_and_reports_outcome(monkeypatch, rollback_fails, outcome):
    args, events = setup(monkeypatch, mismatch=True, rollback_fails=rollback_fails)
    with pytest.raises(NXToolError) as error:
        assign_material(*args, "initial")
    assert error.value.details["mutation_outcome"] == outcome
    assert events[:4] == ["activate", "assign", "dispose", "undo"]


def test_explicit_assignment_returns_actual_state(monkeypatch):
    args, events = setup(monkeypatch)
    result, mark = assign_material(*args, "initial")
    assert mark == 1 and result["collector_state"]["state_sha256"] == "new"
    assert events == ["activate", "assign", "dispose"]
