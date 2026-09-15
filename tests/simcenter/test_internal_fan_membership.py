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
    sim = NS(FullPath="D:/study/copy.sim", IsModified=False)
    fan = NS(Tag=1, JournalIdentifier="fan", OwningPart=sim)
    other = NS(Tag=2, JournalIdentifier="opening", OwningPart=sim)
    members = [fan, other]
    step_members = []
    writes = []
    state = {"flow": 0.001, "wrapper": 5, "invariants": {"targets": [8], "heat": 0}}
    inventory = {"objects": [1, 2], "expressions": [5], "fields": []}
    initial = deepcopy((state, inventory))

    def container(name, values):
        return NS(
            JournalIdentifier=name,
            OwningPart=sim,
            GetBcs=lambda: list(values),
            GetUnfolderedBcs=lambda: list(values),
            GetFolders=lambda: [],
        )

    step = container("step", step_members)
    sol = container("solution", members)
    sol.SolverType = "NX MULTIPHYSICS"
    sol.AnalysisType = "Coupled Thermal-Flow"
    sol.StepCount = 1
    sol.ConflictBcOverrideCount = 0
    sol.GetStepByIndex = lambda _: step

    def change(obj, enabled):
        writes.append(enabled)
        if enabled:
            members.append(obj)
        else:
            members.remove(obj)
        sim.IsModified = True

    sol.AddBc = lambda obj: change(obj, True)
    sol.RemoveBc = lambda obj: change(obj, False)
    sim.Simulation = NS(ActiveSolution=sol, Solutions=[sol])

    def undo(*_):
        members[:] = [fan, other]
        step_members.clear()
        state.clear()
        state.update(deepcopy(initial[0]))
        inventory.clear()
        inventory.update(deepcopy(initial[1]))
        sim.IsModified = False

    session = NS(
        Parts=NS(BaseWork=sim),
        SetUndoMark=lambda *_: 1,
        UndoToMark=undo,
        DeleteUndoMark=lambda *_: None,
        UpdateManager=NS(DoUpdate=lambda _: 0),
    )
    monkeypatch.setattr(mod, "inspect", lambda *args, **kwargs: deepcopy(state))
    monkeypatch.setattr(
        mod,
        "snapshot",
        lambda _: {
            **deepcopy(inventory),
            "solution_bcs": sorted(x.Tag for x in members),
            "modified": sim.IsModified,
        },
    )
    return NS(
        session=session,
        sim=sim,
        fan=fan,
        other=other,
        members=members,
        step=step,
        step_members=step_members,
        sol=sol,
        writes=writes,
        state=state,
        inventory=inventory,
    )


def test_remove_restore_and_idempotent_noops_preserve_fan_and_other_bc(rig):
    a = mod.set_membership(rig.session, rig.sim, rig.fan, False)
    assert a["changed"] and not a["enabled_in_active_solution"]
    assert rig.members == [rig.other]
    assert rig.inventory == {"objects": [1, 2], "expressions": [5], "fields": []}
    assert rig.state["flow"] == 0.001
    assert not mod.set_membership(rig.session, rig.sim, rig.fan, False)["changed"]
    b = mod.set_membership(rig.session, rig.sim, rig.fan, True)
    assert b["enabled_in_active_solution"] and rig.fan in rig.members
    assert not mod.set_membership(rig.session, rig.sim, rig.fan, True)["changed"]
    assert rig.writes == [False, True]
    assert a["native_export_effectiveness"] == "not_verified"


@pytest.mark.parametrize("value", [None, 0, 1, "false", [], {}])
def test_non_boolean_rejected_without_mutation(rig, value):
    with pytest.raises(NXToolError):
        mod.set_membership(rig.session, rig.sim, rig.fan, value)
    assert rig.writes == []


@pytest.mark.parametrize(
    "fault",
    [
        "folder",
        "override",
        "step",
        "multistep",
        "multisolution",
        "owner",
        "unreadable",
        "missing_object",
        "inactive",
    ],
)
def test_unsupported_membership_rejected_before_writing(rig, fault):
    if fault == "folder":
        rig.sol.GetFolders = lambda: [rig.other]
    elif fault == "override":
        rig.sol.ConflictBcOverrideCount = 1
    elif fault == "step":
        rig.step_members.append(rig.fan)
    elif fault == "multistep":
        rig.sol.StepCount = 2
    elif fault == "multisolution":
        rig.sim.Simulation.Solutions.append(NS())
    elif fault == "owner":
        rig.other.OwningPart = NS()
    elif fault == "unreadable":
        rig.sol.GetBcs = lambda: (_ for _ in ()).throw(RuntimeError("unreadable"))
    elif fault == "missing_object":
        rig.inventory["objects"].remove(1)
    else:
        rig.session.Parts.BaseWork = None
    with pytest.raises(NXToolError):
        mod.set_membership(rig.session, rig.sim, rig.fan, False)
    assert rig.writes == []


@pytest.mark.parametrize(
    "fault",
    [
        "update",
        "noop",
        "other_bc",
        "step_changed",
        "flow_changed",
        "object_deleted",
        "expression_added",
        "rollback",
    ],
)
def test_bad_native_readback_restores_state_or_reports_partial(rig, fault):
    def update(_):
        if fault in ("update", "rollback"):
            return 1
        if fault == "other_bc":
            rig.members.remove(rig.other)
        elif fault == "step_changed":
            rig.step_members.append(rig.other)
        elif fault == "flow_changed":
            rig.state["flow"] = 0.009
        elif fault == "object_deleted":
            rig.inventory["objects"].remove(1)
        elif fault == "expression_added":
            rig.inventory["expressions"].append(99)
        return 0

    rig.session.UpdateManager.DoUpdate = update
    if fault == "noop":
        rig.sol.RemoveBc = lambda _: None
    if fault == "rollback":
        rig.session.UndoToMark = lambda *_: None
    with pytest.raises(NXToolError) as error:
        mod.set_membership(rig.session, rig.sim, rig.fan, False)
    assert error.value.details["mutation_outcome"] == (
        "partial" if fault == "rollback" else "rolled_back"
    )
    if fault != "rollback":
        assert rig.members == [rig.fan, rig.other]
        assert not rig.step_members
        assert rig.state["flow"] == 0.001 and not rig.sim.IsModified


def test_busy_solver_rejected_before_resolving_objects(monkeypatch):
    from nx_mcp.simcenter import solver_guard
    from nx_mcp.simcenter.native import SimcenterMixin

    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")
    nx.CAE = cae
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)

    def busy():
        raise NXToolError("NX_SIM_SOLVER_BUSY", "busy")

    monkeypatch.setattr(solver_guard, "require_solver_idle", busy)
    with pytest.raises(NXToolError) as error:
        SimcenterMixin._sim_internal_fan_membership(NS(), "doc", "fan", False)
    assert error.value.code == "NX_SIM_SOLVER_BUSY"


@pytest.mark.asyncio
async def test_membership_public_mutation_schema_and_routing(tmp_path, monkeypatch):
    from nx_mcp.server import create_server
    from nx_mcp.workspace import Workspace

    calls = []

    class Bridge:
        async def call(self, method, params):
            calls.append((method, params))
            return {"status": "success"}

    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(Bridge(), Workspace(tmp_path), enable_experimental=True)
    tool = next(t for t in await server.list_tools() if t.name == "nx_sim_internal_fan_membership")
    assert tool.inputSchema["properties"]["enabled"]["type"] == "boolean"
    assert "operation_id" in tool.inputSchema["properties"]
    assert "enabled" in tool.inputSchema["required"]
    await server.call_tool(tool.name, {"document": "doc", "boundary": "fan", "enabled": False})
    assert calls[-1][0] == tool.name
    assert calls[-1][1]["enabled"] is False
