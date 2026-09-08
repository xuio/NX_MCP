import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.descriptors import descriptor_inventory


def test_native_names_filter_before_paging(monkeypatch):
    cae, uf_module, nx = (ModuleType(n) for n in ("NXOpen.CAE", "NXOpen.UF", "NXOpen"))
    cae.SimPart = type("SimPart", (), {})
    names = ["Heat Load", "Heat Flux", "Gravity"]
    calls = []
    uf = NS(
        Sf=NS(SolutionAskLanguageNx=lambda tag: calls.append(tag) or 123),
        Sfl=NS(
            AskNumLoadDescriptorsNx=lambda tag: len(names),
            AskNthLoadDescriptorNx=lambda tag, index: index,
            AskLoadDescriptorNameNx=lambda index: names[index],
        ),
    )
    uf_module.UFSession = NS(GetUFSession=lambda: uf)
    nx.CAE, nx.UF = cae, uf_module
    for module in (cae, uf_module, nx):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    sim = cae.SimPart()
    sim.FullPath = "case.sim"
    sim.Simulation = NS(
        ActiveSolution=NS(
            Tag=456, Name="Thermal", SolverType="NX MULTIPHYSICS", AnalysisType="Thermal"
        )
    )
    session = NS(Parts=NS(BaseWork=sim))
    nx.Session = NS(GetSession=lambda: session)
    first = descriptor_inventory(sim, name_contains="heat", limit=1)
    second = descriptor_inventory(sim, name_contains="heat", offset=1, limit=1)
    assert first["total"] == 2 and first["unfiltered_total"] == 3
    assert first["descriptors"][0]["descriptor_name"] == "Heat Load"
    assert second["descriptors"][0]["descriptor_name"] == "Heat Flux"
    assert first["next_offset"] == 1 and second["next_offset"] is None
    assert not first["builder_creation_tested_by_call"] and calls == [456, 456]
    with pytest.raises(NXToolError, match="kind must"):
        descriptor_inventory(sim, kind="simulation_object")
    assert calls == [456, 456]
    session.Parts.BaseWork = None
    for category in ("load", "constraint"):
        with pytest.raises(NXToolError, match="SIM work part") as error:
            descriptor_inventory(sim, kind=category)
        assert error.value.details["next_step"] == "nx_sim_activate"
    assert calls == [456, 456]


def test_allowable_steps_keep_native_indices_and_require_sim_work(monkeypatch):
    cae, uf_module, nx = (ModuleType(n) for n in ("NXOpen.CAE", "NXOpen.UF", "NXOpen"))
    cae.SimPart = type("SimPart", (), {})
    sim = cae.SimPart()
    sim.FullPath = "coupled.sim"
    sim.Simulation = NS(
        ActiveSolution=NS(
            Tag=45,
            Name="coupled",
            SolverType="NX MULTIPHYSICS",
            AnalysisType="Coupled Thermal-Flow",
        )
    )
    session = NS(Parts=NS(BaseWork=sim))
    calls = []
    uf = NS(
        Sf=NS(SolutionAskLanguageNx=lambda tag: 123, SolutionAskDescriptorNx=lambda tag: 678),
        Sfl=NS(
            SolutionAskNumAllowableStepDescriptorsNx=lambda tag: calls.append(tag) or 2,
            SolutionAskNthAllowableStepDescriptorNx=lambda tag, index: index,
            StepDescriptorAskNameNx=lambda index: ["Other", "Step - Thermal Flow"][index],
        ),
    )
    uf_module.UFSession = NS(GetUFSession=lambda: uf)
    nx.CAE, nx.UF = cae, uf_module
    nx.Session = NS(GetSession=lambda: session)
    for module in (cae, uf_module, nx):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    page = descriptor_inventory(sim, kind="solution_step", name_contains="thermal", limit=1)
    assert page["descriptors"] == [
        {"descriptor_name": "Step - Thermal Flow", "kind": "solution_step", "step_type_index": 1}
    ]
    assert page["total"] == 1 and page["unfiltered_total"] == 2
    assert page["solution_applicability"] == "native_allowable_step" and calls == [678]
    session.Parts.BaseWork = None
    with pytest.raises(NXToolError, match="SIM work part"):
        descriptor_inventory(sim, kind="solution_step")
    assert calls == [678]
