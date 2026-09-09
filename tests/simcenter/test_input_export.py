import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.input_export import export_flow_input
from nx_mcp.workspace import Workspace


@pytest.fixture
def setup(tmp_path, monkeypatch):
    cae = ModuleType("NXOpen.CAE")

    class SimPart:
        pass

    cae.SimPart = SimPart
    cae.SimSolutionSolveOption = NS(WriteSolverInputFile="export")
    cae.SimSolutionSetupCheckOption = NS(CompleteCheckAndOutputErrors="check")
    nx = ModuleType("NXOpen")
    nx.CAE = cae
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    root = tmp_path / "isolated"
    root.mkdir()
    source = root / "case.sim"
    source.write_bytes(b"source")
    calls = []

    def solve(*args):
        calls.append(args)
        (root / "actual-name.xml").write_text(
            '<SolutionFile class="Flow"><ElementList><Set><E>1</E></Set></ElementList><NodeList><N>1</N></NodeList></SolutionFile>'
        )

    solution = NS(SolverType="NX MULTIPHYSICS", AnalysisType="Flow", Name="Flow case", Solve=solve)
    sim = SimPart()
    sim.FullPath, sim.IsModified, sim.Simulation = str(source), False, NS(ActiveSolution=solution)
    session = NS(Parts=NS(BaseWork=sim))
    return session, Workspace(tmp_path), sim, root, calls


def test_native_output_is_discovered_and_fingerprinted(setup):
    session, workspace, sim, root, calls = setup
    result = export_flow_input(session, workspace, sim)
    assert result["input_path"] == str(root / "actual-name.xml")
    assert result["validation"]["mesh_counts"]["elements"] == 1
    assert not result["solver_launched"]
    assert calls == [("export", "check")]
    assert (root / "case.sim").read_bytes() == b"source"
    with pytest.raises(NXToolError) as exc:
        export_flow_input(session, workspace, sim)
    assert exc.value.code == "NX_SIM_OUTPUT_CONFLICT" and len(calls) == 1


def test_api_failure_preserves_partial_artifacts(setup):
    session, workspace, sim, root, calls = setup

    def fail(*args):
        (root / "partial.log").write_text("NX2TMG - FATAL ERROR 123")
        raise RuntimeError("native failure")

    sim.Simulation.ActiveSolution.Solve = fail
    with pytest.raises(NXToolError) as exc:
        export_flow_input(session, workspace, sim)
    assert exc.value.code == "NX_SIM_EXPORT_FAILED"
    assert exc.value.details["mutation_outcome"] == "partial"
    assert (root / "partial.log").is_file()


def test_zero_mesh_is_not_export_success(setup):
    session, workspace, sim, root, calls = setup
    sim.Simulation.ActiveSolution.Solve = lambda *args: (root / "empty.xml").write_text(
        "<SolutionFile><ElementList/><NodeList/></SolutionFile>"
    )
    with pytest.raises(NXToolError, match="failed verification"):
        export_flow_input(session, workspace, sim)


def test_wrong_solver_rejected_before_native_call(setup):
    session, workspace, sim, root, calls = setup
    sim.Simulation.ActiveSolution.SolverType = "unverified"
    with pytest.raises(NXToolError) as exc:
        export_flow_input(session, workspace, sim)
    assert exc.value.code == "NX_SIM_UNSUPPORTED" and not calls


@pytest.mark.parametrize("analysis", ["Thermal", "Flow", "Coupled Thermal-Flow"])
def test_supported_analysis_dispatch(setup, analysis):
    session, workspace, sim, root, calls = setup
    sim.Simulation.ActiveSolution.AnalysisType = analysis
    if analysis == "Coupled Thermal-Flow":
        sim.Simulation.ActiveSolution.PropertyTable = NS(
            GetScalarWithDataPropertyValue=lambda key: (20.0, NS(Name="Celsius")),
            GetIntegerPropertyValue=lambda key: 1,
        )
        original = sim.Simulation.ActiveSolution.Solve

        def coupled_export(*args):
            original(*args)
            path = root / "actual-name.xml"
            path.write_text(
                path.read_text()
                .replace('class="Flow"', 'class="Coupled Thermal-Flow"')
                .replace(
                    "</SolutionFile>",
                    "<Units><TemperatureConversionFactor>1</TemperatureConversionFactor>"
                    "<AbsoluteTemperatureShift>-273.15</AbsoluteTemperatureShift></Units>"
                    '<SolutionParameters><AmbientConditions><Property name="Fluid Temperature">'
                    '<Value>20</Value></Property><Property name="Ambient Pressure"><Value>1</Value></Property></AmbientConditions></SolutionParameters></SolutionFile>',
                )
            )

        sim.Simulation.ActiveSolution.Solve = coupled_export
    result = export_flow_input(session, workspace, sim)
    assert result["analysis_type"] == analysis and len(calls) == 1


def test_native_coupled_mismatch_preserves_evidence_and_rejects_export(setup):
    from pathlib import Path

    session, workspace, sim, root, calls = setup
    solution = sim.Simulation.ActiveSolution
    solution.AnalysisType = "Coupled Thermal-Flow"
    solution.PropertyTable = NS(
        GetScalarWithDataPropertyValue=lambda key: (20.0, NS(Name="Celsius")),
        GetIntegerPropertyValue=lambda key: 1,
    )
    native_deck = Path(__file__).parent / "evidence/coupled-cae-scalar-deck.xml"
    solution.Solve = lambda *args: (root / "native.xml").write_bytes(native_deck.read_bytes())
    with pytest.raises(NXToolError) as exc:
        export_flow_input(session, workspace, sim)
    assert exc.value.code == "NX_SIM_EXPORT_FAILED"
    assert exc.value.details["coupled_ambient_validation"]["exported_value"] == 0
    assert exc.value.details["coupled_ambient_validation"]["native_value"] == 20
    assert not exc.value.details["coupled_ambient_validation"]["matches"]
    assert (root / "native.xml").read_bytes() == native_deck.read_bytes()


def test_unverified_analysis_rejected(setup):
    session, workspace, sim, root, calls = setup
    sim.Simulation.ActiveSolution.AnalysisType = "Coupled"
    with pytest.raises(NXToolError):
        export_flow_input(session, workspace, sim)
    assert not calls


def test_active_pressure_mismatch_rejects_export_and_preserves_temperature_guard(setup):
    from pathlib import Path

    session, workspace, sim, root, calls = setup
    nx = sys.modules["NXOpen"]
    nx.Expression = NS(UnitsOption=NS(Expression="expression"))
    expression = NS(Units=NS(Name="PressurePascals"), GetValueUsingUnits=lambda mode: 101325.0)
    wrapper = NS(GetExpression=lambda: expression, GetField=lambda: None)
    solution = sim.Simulation.ActiveSolution
    solution.AnalysisType = "Coupled Thermal-Flow"
    solution.PropertyTable = NS(
        GetScalarWithDataPropertyValue=lambda key: (0.0, NS(Name="Celsius")),
        GetIntegerPropertyValue=lambda key: 0,
        GetScalarFieldWrapperPropertyValue=lambda key: wrapper,
    )
    raw = (Path(__file__).parent / "evidence/finned-pressure-r1.xml").read_bytes()
    solution.Solve = lambda *args: (root / "native.xml").write_bytes(raw)
    with pytest.raises(NXToolError) as exc:
        export_flow_input(session, workspace, sim)
    assert exc.value.details["coupled_ambient_validation"]["matches"]
    assert not exc.value.details["coupled_pressure_validation"]["matches"]
    assert exc.value.details["coupled_pressure_validation"]["native_value"] == 101325
    assert (root / "native.xml").read_bytes() == raw


def test_scaled_pressure_field_is_rejected_before_native_export(setup):
    session, workspace, sim, root, calls = setup
    solution = sim.Simulation.ActiveSolution
    solution.AnalysisType = "Coupled Thermal-Flow"
    solution.PropertyTable = NS(
        GetScalarWithDataPropertyValue=lambda key: (0.0, NS(Name="Celsius")),
        GetIntegerPropertyValue=lambda key: 0,
        GetScalarFieldWrapperPropertyValue=lambda key: NS(
            GetExpression=lambda: None, GetField=lambda: object()
        ),
    )
    with pytest.raises(NXToolError) as exc:
        export_flow_input(session, workspace, sim)
    assert "field definitions/scales" in exc.value.details["reason"]
    assert not calls
    assert not list(root.glob("*.xml"))


def test_ui_authored_mpa_pressure_is_compared_in_pa(setup):
    from pathlib import Path

    session, workspace, sim, root, calls = setup
    sys.modules["NXOpen"].Expression = NS(UnitsOption=NS(Expression="expression"))
    expression = NS(
        Units=NS(Name="PressureNewtonPerSquareMilliMeter"), GetValueUsingUnits=lambda mode: 0.101325
    )
    wrapper = NS(GetExpression=lambda: expression, GetField=lambda: None)
    solution = sim.Simulation.ActiveSolution
    solution.AnalysisType = "Coupled Thermal-Flow"
    solution.PropertyTable = NS(
        GetScalarWithDataPropertyValue=lambda key: (20.0, NS(Name="Celsius")),
        GetIntegerPropertyValue=lambda key: 0,
        GetScalarFieldWrapperPropertyValue=lambda key: wrapper,
    )
    raw = (Path(__file__).parent / "evidence/ui-reference-ambient.xml").read_bytes()
    solution.Solve = lambda *args: (root / "native.xml").write_bytes(raw)
    result = export_flow_input(session, workspace, sim)
    assert result["coupled_ambient_validation"]["matches"]
    assert result["coupled_pressure_validation"]["matches"]
    assert result["coupled_pressure_validation"]["native_value"] == 101325
