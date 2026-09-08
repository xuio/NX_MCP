from pathlib import Path

import pytest

from nx_mcp.simcenter.flow_audit import inspect_flow_log

LOG = (Path(__file__).parent / "fixtures/flow-steady-excerpt.log").read_text()


def test_native_flow_residuals_and_units():
    r = inspect_flow_log(LOG)
    assert len(r["residual_history"]) == 60
    assert r["last_iteration"] == 15 and r["final_residual_criteria_met"] is True
    assert sum(row["rate_overflow"] for row in r["residual_history"]) == 2
    assert r["reported_imbalances"]["mass"]["value"] == 0.008865
    assert r["boundary_flows"][0]["volume_flow_m3_s"] == pytest.approx(0.0001912)
    assert r["rounded_boundary_mass_sum_kg_s"] == 0
    assert r["numerical_convergence"] == "not_established"


def test_incomplete_last_iteration_cannot_reuse_previous_complete_table():
    cut = LOG.index("| U - Mom", LOG.index("Step 15"))
    r = inspect_flow_log(LOG[:cut])
    assert r["last_iteration"] == 15 and not r["final_equations_complete"]
    assert r["final_residual_criteria_met"] is None


def test_missing_equation_and_repeated_history_are_not_complete_evidence():
    r = inspect_flow_log(LOG.replace("P - Mass", "unknown equation"))
    assert not r["final_equations_complete"] and r["final_residual_criteria_met"] is None
    assert inspect_flow_log(LOG + LOG)["final_residual_criteria_met"] is None


def test_nonfinite_numeric_rejected():
    with pytest.raises(ValueError, match="Nonfinite"):
        inspect_flow_log(LOG.replace("7.568e-07", "1e999"))


def test_unknown_format_and_completion_alone_are_not_convergence():
    r = inspect_flow_log("Solve completed at: today")
    assert r["completion_marker_present"] and r["final_residual_criteria_met"] is None
    assert r["boundary_flows"] == []


def test_actual_coupled_diagnostic_retains_failure_and_energy_equation():
    log = (Path(__file__).parent / "evidence/coupled-diagnostic.log").read_text()
    report = inspect_flow_log(log)
    assert report["format"] == "observed_simcenter_2606_steady_coupled"
    assert any(r["equation"] == "H - Energy" for r in report["residual_history"])
    # Flow residuals alone cannot establish coupled convergence.
    assert report["final_residual_criteria_met"] is None
    summary = report["coupled_summary"]
    assert summary["iteration_limit_reached_without_convergence"]
    assert summary["numerical_convergence"] == "failed"
    assert summary["ambient_temperature_degC"] == 0
    assert summary["applied_solid_power_W"] == pytest.approx(0.1)
    assert summary["heat_to_fluid_W"] == pytest.approx(0.09971)
    assert summary["maximum_coupled_temperature_change_degC"] == 1.185
    assert summary["normalized_coupled_heat_imbalance"] == 0.05549
    assert summary["warnings"]["coincident_thermal_nodes"]
    assert len(summary["temperature_summaries"]) == 3
    assert inspect_flow_log(log + log)["coupled_summary"] is None
