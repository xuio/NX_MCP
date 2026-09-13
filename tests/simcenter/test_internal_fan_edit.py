import sys
from copy import deepcopy
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import internal_fan_edit as mod


@pytest.fixture
def rig(monkeypatch):
    nx = ModuleType("NXOpen")
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    state = {"flow": 0.002, "wrapper": 10, "invariants": {"targets": [4], "heat": 0}}
    initial = deepcopy(state)
    inventory = {
        "objects": [1],
        "solution_bcs": [1],
        "expressions": [1],
        "fields": [],
        "modified": False,
    }
    old_inventory = deepcopy(inventory)
    writes = []

    def create(value, unit):
        inventory["expressions"].append(2)
        return float(value)

    def bind(key, wrapper):
        writes.append((key, wrapper))
        state.update(flow=wrapper, wrapper=11)
        inventory["modified"] = True

    boundary = NS(PropertyTable=NS(SetScalarFieldWrapperPropertyValue=bind))
    sim = NS(
        Simulation=NS(
            ActiveSolution=NS(SolverType="NX MULTIPHYSICS", AnalysisType="Flow", StepCount=1)
        ),
        UnitCollection=NS(FindObject=lambda _: "unit"),
        Expressions=NS(CreateSystemNumberExpression=create),
        FieldManager=NS(CreateScalarFieldWrapperWithExpression=lambda e: e),
    )

    def undo(*_):
        state.clear()
        state.update(deepcopy(initial))
        inventory.clear()
        inventory.update(deepcopy(old_inventory))

    session = NS(
        Parts=NS(BaseWork=sim),
        SetUndoMark=lambda *_: 1,
        UndoToMark=undo,
        DeleteUndoMark=lambda *_: None,
        UpdateManager=NS(DoUpdate=lambda _: 0),
    )
    monkeypatch.setattr(mod, "inspect", lambda *_: deepcopy(state))
    monkeypatch.setattr(mod, "snapshot", lambda *_: deepcopy(inventory))
    return session, sim, boundary, state, inventory, writes


def test_flow_change_only_and_noop(rig):
    s, sim, fan, state, inventory, writes = rig
    result = mod.edit(s, sim, fan, 0.001)
    assert result["actual_m3_s"] == 0.001
    assert inventory["expressions"] == [1, 2]
    assert state["invariants"] == {"targets": [4], "heat": 0}
    assert writes == [("Volume Flow", 0.001)]
    assert not mod.edit(s, sim, fan, 0.001)["changed"]
    assert len(writes) == 1


@pytest.mark.parametrize("bad", [True, 0, -1, float("inf"), float("nan"), "0.1"])
def test_invalid_flow_never_mutates(rig, bad):
    with pytest.raises(NXToolError):
        mod.edit(*rig[:3], bad)
    assert not rig[5]


@pytest.mark.parametrize("failure", ["update", "invariant", "binding", "rollback"])
def test_failure_restores_binding_inventory_or_reports_partial(rig, failure):
    s, sim, fan, state, inventory, writes = rig
    if failure in ("update", "rollback"):
        s.UpdateManager.DoUpdate = lambda _: 1
    elif failure == "invariant":

        def update(_):
            state["invariants"]["heat"] = 10
            return 0

        s.UpdateManager.DoUpdate = update
    else:
        fan.PropertyTable.SetScalarFieldWrapperPropertyValue = lambda *_: None
    if failure == "rollback":
        s.UndoToMark = lambda *_: None
    with pytest.raises(NXToolError) as e:
        mod.edit(s, sim, fan, 0.001)
    assert e.value.details["mutation_outcome"] == (
        "partial" if failure == "rollback" else "rolled_back"
    )
    if failure != "rollback":
        assert state["flow"] == 0.002 and state["wrapper"] == 10
        assert inventory["expressions"] == [1]


def test_busy_solver_blocks_before_reference_resolution(monkeypatch):
    from nx_mcp.simcenter import solver_guard
    from nx_mcp.simcenter.native import SimcenterMixin

    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")
    nx.CAE = cae
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)

    def busy():
        raise NXToolError("NX_SIM_SOLVER_BUSY", "busy")

    monkeypatch.setattr(solver_guard, "require_solver_idle", busy)
    with pytest.raises(NXToolError) as e:
        SimcenterMixin._sim_internal_fan_flow(NS(), "doc", "fan", 0.001)
    assert e.value.code == "NX_SIM_SOLVER_BUSY"


@pytest.mark.parametrize(
    "bad", [None, "owner", "mode", "field", "formula", "units", "member", "targets"]
)
def test_inspection_rejects_unsupported_binding(bad):
    sim = NS(Simulation=NS(ActiveSolution=NS(GetBcs=lambda: [NS(Tag=3)])))
    expression = NS(GetFormula=lambda: ".002", Units=NS(Name="CubicMeterPerSecond"))
    wrapper = NS(Tag=8, GetExpression=lambda: expression, GetField=lambda: None)
    selectors = {"Mode Option": 3, "Alignment": 0, "Swirl": 0, "Controller Type": 0}
    prop = NS(
        GetIntegerPropertyValue=lambda k: selectors[k],
        GetScalarFieldWrapperPropertyValue=lambda _: wrapper,
        GetScalarWithDataPropertyValue=lambda _: (0.002, NS(Name="CubicMeterPerSecond")),
        GetVectorPropertyValue=lambda _: NS(Tag=7, Vector=NS(X=0.0, Y=0.0, Z=1.0)),
        GetBaseScalarWithDataPropertyValue=lambda _: (0.0, NS(Name="Watt")),
    )
    fan = NS(
        Tag=3,
        Name="fan",
        OwningPart=sim,
        DescriptorName="Internal Fan",
        PropertyTable=prop,
        TargetSetManager=NS(
            GetTargetSetMembers=lambda _: (0, [NS(Obj=NS(Tag=9), SubType=0, SubId=0)])
        ),
    )
    if bad == "owner":
        fan.OwningPart = None
    elif bad == "mode":
        selectors["Mode Option"] = 4
    elif bad == "field":
        wrapper.GetField = lambda: object()
    elif bad == "formula":
        expression.GetFormula = lambda: "other_expression * 2"
    elif bad == "units":
        expression.Units.Name = "CubicMilliMeterPerSecond"
    elif bad == "member":
        sim.Simulation.ActiveSolution.GetBcs = lambda: []
    elif bad == "targets":
        fan.TargetSetManager.GetTargetSetMembers = lambda _: (0, [])
    if bad is None:
        assert mod.inspect(fan, sim)["flow"] == 0.002
    else:
        with pytest.raises(NXToolError):
            mod.inspect(fan, sim)
