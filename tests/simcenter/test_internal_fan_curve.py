import sys
from copy import deepcopy
from types import ModuleType, SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import internal_fan_curve as mod


@pytest.fixture
def rig(monkeypatch):
    nx = ModuleType("NXOpen")
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    state = {"mode": 3, "wrapper": None, "heat": 0, "targets": [1],
             "members": [7], "modified": False, "fields": [9]}
    initial = deepcopy(state)
    table = object()
    wrapper = NS(Tag=10, GetField=lambda: table, GetFieldScaleFactor=lambda: 1.0,
                 GetExpression=lambda: None)
    def bind(_, value):
        state["wrapper"] = value
        state["modified"] = True
    props = NS(GetScalarFieldWrapperPropertyValue=lambda _: state["wrapper"],
               SetScalarFieldWrapperPropertyValue=bind,
               SetIntegerPropertyValue=lambda _, value: state.update(mode=value),
               GetIntegerPropertyValue=lambda _: state["mode"])
    fan = NS(PropertyTable=props)
    sol = NS(SolverType="NX MULTIPHYSICS", AnalysisType="Flow", StepCount=1)
    sim = NS(Simulation=NS(ActiveSolution=sol, Solutions=[sol]),
             FieldManager=NS(CreateScalarFieldWrapperWithField=lambda *_: wrapper))
    def inspect(*_):
        if state["mode"] != 3:
            raise NXToolError("NX_SIM_UNSUPPORTED_CONFIGURATION", "not constant flow")
        return {"flow": .001}
    def undo(*_):
        state.clear()
        state.update(deepcopy(initial))
    session = NS(Parts=NS(BaseWork=sim), SetUndoMark=lambda *_: 1,
                 UndoToMark=undo, DeleteUndoMark=lambda *_: None,
                 UpdateManager=NS(DoUpdate=lambda _: 0))
    monkeypatch.setattr(mod, "inspect", inspect)
    monkeypatch.setattr(mod, "preserved", lambda *_: deepcopy({k: state[k] for k in ["heat", "targets"]}))
    monkeypatch.setattr(mod, "snapshot", lambda *_: deepcopy({k: state[k] for k in ["fields", "modified"]}))
    monkeypatch.setattr(mod, "capture_effective_membership", lambda *_: {
        "comparison_verified": True, "members": list(state["members"])})
    monkeypatch.setattr(mod, "inspect_fan_table", lambda *_: {"manifest": {"pressure_convention": "static"}})
    return session, sim, fan, table, state, wrapper


def test_binding_preserves_settings(rig):
    result = mod.assign(*rig[:4])
    assert result["mode"] == "fan_curve" and result["membership_preserved"]
    assert rig[4]["mode"] == 4 and rig[4]["wrapper"] is rig[5]
    assert not result["saved"] and result["native_export_acceptance"] == "pending"


@pytest.mark.parametrize("failure", ["update", "heat", "targets", "membership", "field", "scale", "mode", "rollback"])
def test_failed_readback_rolls_back_or_reports_partial(rig, failure):
    session, sim, fan, table, state, wrapper = rig
    if failure in ("update", "rollback"):
        session.UpdateManager.DoUpdate = lambda _: 1
    elif failure in ("heat", "targets", "membership"):
        key = {"heat": "heat", "targets": "targets", "membership": "members"}[failure]
        session.UpdateManager.DoUpdate = lambda _: (state.update({key: 99}) or 0)
    elif failure == "field":
        wrapper.GetField = lambda: None
    elif failure == "scale":
        wrapper.GetFieldScaleFactor = lambda: 2
    else:
        fan.PropertyTable.SetIntegerPropertyValue = lambda *_: None
    if failure == "rollback":
        session.UndoToMark = lambda *_: None
    with pytest.raises(NXToolError) as exc:
        mod.assign(session, sim, fan, table)
    assert exc.value.details["mutation_outcome"] == ("partial" if failure == "rollback" else "rolled_back")
    if failure != "rollback":
        assert state["mode"] == 3 and state["wrapper"] is None


def test_total_curve_rejected_before_mutation(rig, monkeypatch):
    monkeypatch.setattr(mod, "inspect_fan_table", lambda *_: {"manifest": {"pressure_convention": "total"}})
    with pytest.raises(NXToolError):
        mod.assign(*rig[:4])
    assert rig[4]["wrapper"] is None


def test_busy_solver_blocks_before_resolution(monkeypatch):
    from nx_mcp.simcenter import solver_guard
    from nx_mcp.simcenter.native import SimcenterMixin
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")
    nx.CAE = cae
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    def busy():
        raise NXToolError("NX_SIM_SOLVER_BUSY", "busy")
    monkeypatch.setattr(solver_guard, "require_solver_idle", busy)
    with pytest.raises(NXToolError) as exc:
        SimcenterMixin._sim_internal_fan_curve(NS(), "doc", "fan", "table")
    assert exc.value.code == "NX_SIM_SOLVER_BUSY"
