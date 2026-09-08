import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import scenario_apply


def test_second_source_failure_rolls_back_the_first_source(monkeypatch):
    nx = ModuleType("NXOpen")
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    sim = NS(
        Simulation=NS(
            ActiveSolution=NS(SolverType="NX MULTIPHYSICS", AnalysisType="Thermal"),
            Loads=[],
            Constraints=[],
        ),
        Expressions=[],
    )
    undo = []

    def rollback(mark, _):
        undo.append(mark)
        sim.Simulation.Loads.clear()
        sim.Expressions.clear()

    session = NS(
        Parts=NS(BaseWork=sim),
        SetUndoMark=lambda *args: 42,
        UndoToMark=rollback,
        DeleteUndoMark=lambda *args: None,
    )
    targets = [NS(Tag=i, OwningPart=sim) for i in (1, 2)]
    plan = {
        "assignments": [
            {
                "source": name,
                "accounting_id": name,
                "power_W": 2,
                "provenance": {"kind": "assumed", "source": "test"},
            }
            for name in ("SOC", "SSD")
        ],
        "scenario_sha256": "abc",
        "workload_revision": "r1",
    }
    calls = []

    def create(*args):
        calls.append(args[4])
        sim.Simulation.Loads.append(NS(Tag=100 + len(calls)))
        sim.Expressions.append(NS(Tag=200 + len(calls)))
        if len(calls) == 2:
            raise NXToolError("NX_SIM_TEST_FAILURE", "second source failed after partial creation")
        return {"power_w": 2, "target_count": 1}

    monkeypatch.setattr(scenario_apply, "create_body_power", create)
    with pytest.raises(NXToolError) as error:
        scenario_apply.apply_scenario(session, sim, plan, targets)
    assert calls == ["SOC", "SSD"]
    assert error.value.details["mutation_outcome"] == "rolled_back"
    assert undo == [42] and not sim.Simulation.Loads and not sim.Expressions


def test_existing_loads_rejected_before_mutation(monkeypatch):
    monkeypatch.setitem(sys.modules, "NXOpen", ModuleType("NXOpen"))
    sim = NS(
        Simulation=NS(
            ActiveSolution=NS(SolverType="NX MULTIPHYSICS", AnalysisType="Thermal"),
            Loads=[NS(Tag=1)],
        )
    )
    session = NS(Parts=NS(BaseWork=sim))
    with pytest.raises(NXToolError) as error:
        scenario_apply.apply_scenario(session, sim, {}, [])
    assert error.value.code == "NX_SIM_SCENARIO_CONFLICT"
    assert error.value.details["mutation_outcome"] == "not_started"
    assert len(sim.Simulation.Loads) == 1
