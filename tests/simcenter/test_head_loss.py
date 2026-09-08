import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.head_loss import set_opening_head_loss


def fixture(monkeypatch):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")
    nx.CAE = cae
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    cae.SimPart = type("SimPart", (), {})
    sim = cae.SimPart()
    value = {"current": 0.0, "writes": 0, "bad": False, "marks": 0}

    def write(key, new, unit):
        value["writes"] += 1
        value["current"] = new + 1 if value["bad"] else new

    value.update(mode=0, proportional=0)
    props = NS(
        GetIntegerPropertyValue=lambda key: value["mode" if key == "Type" else "proportional"],
        GetBaseScalarWithDataPropertyValue=lambda key: (value["current"], None),
        SetBaseScalarWithDataPropertyValue=write,
    )
    table = NS(Name="loss", DescriptorType="Head Loss", PropertyTable=props)
    boundary = NS(
        Name="outlet",
        OwningPart=sim,
        DescriptorName="Opening",
        PropertyTable=NS(GetNamedPropertyTablePropertyValue=lambda key: table),
    )
    sim.Simulation = NS(
        ActiveSolution=NS(SolverType="NX MULTIPHYSICS", AnalysisType="Flow"),
        SimulationObjects=[boundary],
    )

    def mark(*args):
        value["marks"] += 1
        value["before"] = value["current"]
        return 1

    session = NS(
        Parts=NS(BaseWork=sim),
        SetUndoMark=mark,
        UndoToMark=lambda *args: value.update(current=value["before"]),
        DeleteUndoMark=lambda *args: None,
    )
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr("nx_mcp.simcenter.solver_guard.require_solver_idle", lambda: None)
    monkeypatch.setattr("nx_mcp.simcenter.head_loss.read_properties", lambda *args: [])
    return session, sim, boundary, value


def test_conflict_and_noop_do_not_write(monkeypatch):
    session, sim, boundary, value = fixture(monkeypatch)
    with pytest.raises(NXToolError, match="expected value"):
        set_opening_head_loss(session, sim, boundary, 2, expected_coefficient=3)
    result = set_opening_head_loss(session, sim, boundary, 0, expected_coefficient=0)
    assert result["action"] == "unchanged" and value["writes"] == value["marks"] == 0
    with pytest.raises(NXToolError, match="nonnegative"):
        set_opening_head_loss(session, sim, boundary, True, expected_coefficient=0)


def test_mismatched_commit_is_rolled_back(monkeypatch):
    session, sim, boundary, value = fixture(monkeypatch)
    value["bad"] = True
    with pytest.raises(NXToolError, match="rolled back"):
        set_opening_head_loss(session, sim, boundary, 2, expected_coefficient=0)
    assert value["current"] == 0 and value["writes"] == 1
    value["bad"] = False
    result = set_opening_head_loss(session, sim, boundary, 2, expected_coefficient=0)
    assert result["coefficient"] == value["current"] == 2
    assert result["results_require_revalidation"]


@pytest.mark.parametrize("mode,proportional", [(1, 0), (0, 1)])
@pytest.mark.parametrize("requested", [0, 2])
def test_inactive_coefficient_rejects_updates_and_noops(monkeypatch, mode, proportional, requested):
    session, sim, boundary, state = fixture(monkeypatch)
    state.update(mode=mode, proportional=proportional)
    with pytest.raises(NXToolError) as error:
        set_opening_head_loss(session, sim, boundary, requested, expected_coefficient=0)
    assert error.value.code == "NX_SIM_HEAD_LOSS_MODE"
    assert state["writes"] == state["marks"] == 0


def test_wrong_descriptor_rejects_before_write(monkeypatch):
    session, sim, boundary, state = fixture(monkeypatch)
    boundary.PropertyTable.GetNamedPropertyTablePropertyValue(
        "Head Loss"
    ).DescriptorType = "External Conditions"
    with pytest.raises(NXToolError, match="descriptor"):
        set_opening_head_loss(session, sim, boundary, 2, expected_coefficient=0)
    assert state["writes"] == state["marks"] == 0
