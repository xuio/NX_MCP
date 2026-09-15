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
    assert r["rounded_boundary_mass_sum_kg_s"] is None
    roles = {row["name"]: "Opening" for row in r["boundary_flows"]}
    assert inspect_flow_log(LOG, roles)["rounded_boundary_mass_sum_kg_s"] == 0
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


def test_fluid_energy_history_and_internal_transport_are_not_external_mass():
    text = (Path(__file__).parent / "fixtures/mated-fan-steady-excerpt.log").read_text()
    roles = {
        "MATED_INTERNAL_FAN_Q1E4_HEAT1W": "Internal Fan",
        "LEFT_AMBIENT_MATED": "Opening",
        "RIGHT_AMBIENT_MATED": "Opening",
    }
    report = inspect_flow_log(text, roles)
    assert report["last_iteration"] == 12
    assert report["final_equations_complete"]
    assert report["final_residual_criteria_met"] is True
    assert report["rounded_boundary_mass_sum_kg_s"] == 0
    assert report["boundary_flows"][0]["flow_scope"] == "internal"
    assert report["boundary_flows"][0]["positive_direction"] != "into_domain"
    assert inspect_flow_log(text)["rounded_boundary_mass_sum_kg_s"] is None
    roles["MATED_INTERNAL_FAN_Q1E4_HEOTHER"] = "Opening"
    assert inspect_flow_log(text, roles)["rounded_boundary_mass_sum_kg_s"] is None


def test_missing_final_fluid_energy_row_is_not_accepted():
    text = (Path(__file__).parent / "fixtures/mated-fan-steady-excerpt.log").read_text()
    start = text.rfind("| H - Energy")
    text = text[:start] + text[start:].replace("H - Energy", "Unknown", 1)
    assert inspect_flow_log(text)["final_residual_criteria_met"] is None


def _sst_history(turbulence_residual="1.0e-06", startup=False):
    header = (
        "Steady-state convergence history - Flow simulation\n"
        "Flow converged when RMS residual less than: 1e-4\n"
        "Flow laminar/turbulent model: SST\n"
        "Global iteration | Linear Solver | Convergence info |\n"
        " 9 +-------------+\n"
        "| Flow Enclosure - Step of 0.005000s - Step 9 |\n"
    )
    rows = []
    for equation in ("U - Mom", "V - Mom", "W - Mom", "P - Mass", "K - TurbKE", "O - Diss.K"):
        turbulence = equation in {"K - TurbKE", "O - Diss.K"}
        iterations, linear = ("---", "------") if startup and turbulence else ("1", "1e-6")
        residual = turbulence_residual if turbulence else "1e-6"
        message = "OK" if float(residual) < 1e-4 else "--"
        rows.append(f"| {equation} | {iterations} | {linear} | 0.9 | {residual} | {message} |")
    return (header + "\n".join(rows)).replace("\n", "\r\r\n")


def test_sst_requires_both_turbulence_equations():
    report = inspect_flow_log(_sst_history())
    assert len(report["residual_history"]) == 6
    assert report["final_equations_complete"]
    assert report["final_residual_criteria_met"] is True
    assert report["numerical_convergence"] == "not_established"
    report = inspect_flow_log(_sst_history("1e-2"))
    assert report["final_equations_complete"]
    assert report["final_residual_criteria_met"] is False
    assert (
        inspect_flow_log(_sst_history().replace("O - Diss.K", "unknown"))[
            "final_residual_criteria_met"
        ]
        is None
    )


def test_sst_startup_placeholders_remain_unsolved():
    report = inspect_flow_log(_sst_history("1e20", startup=True))
    assert len(report["residual_history"]) == 6
    assert report["residual_history"][-1]["linear_iterations"] is None
    assert report["residual_history"][-1]["linear_residual"] is None
    assert not report["final_equations_complete"]
    assert report["final_residual_criteria_met"] is None
    # Even falsely reassuring residual/message values cannot certify unsolved rows.
    assert inspect_flow_log(_sst_history(startup=True))["final_residual_criteria_met"] is None


def test_sst_missing_final_rows_cannot_reuse_previous_iteration():
    text = _sst_history() + "\nGlobal iteration | Linear Solver\n 10 +---\n"
    assert inspect_flow_log(text)["final_residual_criteria_met"] is None


def test_observed_sst_startup_excerpt():
    text = (Path(__file__).parent / "fixtures/sst-startup-excerpt.log").read_text()
    report = inspect_flow_log(text)
    assert report["last_iteration"] == 9
    final = {r["equation"]: r for r in report["residual_history"] if r["iteration"] == 9}
    assert final["K - TurbKE"]["residual"] == pytest.approx(1.011e-2)
    assert final["O - Diss.K"]["residual"] == pytest.approx(1.986e-5)
    assert report["final_residual_criteria_met"] is False
    assert any(r["linear_iterations"] is None for r in report["residual_history"])


def test_residual_pass_retains_unmet_native_imbalance():
    diagnostic = (
        "\n| Maximum observed imbalance value: 1.2567e+02 (turbulence) |\n"
        "| Target imbalance value: 1.0000e-03 |\n"
    )
    report = inspect_flow_log(_sst_history() + diagnostic.replace("\n", "\r\r\n"))
    assert report["final_residual_criteria_met"] is True
    imbalance = report["final_iteration_imbalance"]
    assert imbalance["iteration"] == 9
    assert imbalance["quantity"] == "turbulence"
    assert imbalance["maximum_observed"] == pytest.approx(125.67)
    assert imbalance["target"] == pytest.approx(0.001)
    assert imbalance["above_target"]
    assert report["numerical_convergence"] == "not_established"
    partial = inspect_flow_log(_sst_history() + diagnostic + "Global iteration |\n 10 +---\n")
    assert len(partial["iterative_imbalance_history"]) == 1
    assert partial["final_iteration_imbalance"] is None


def test_incomplete_or_duplicate_imbalance_diagnostic_is_not_inferred():
    maximum = "\n| Maximum observed imbalance value: 125.67 (turbulence) |\n"
    target = "| Target imbalance value: .001 |\n"
    assert inspect_flow_log(_sst_history() + maximum)["final_iteration_imbalance"] is None
    assert (
        inspect_flow_log(_sst_history() + maximum + target * 0)["iterative_imbalance_history"] == []
    )
    assert (
        inspect_flow_log(_sst_history() + (maximum + target) * 2)["final_iteration_imbalance"]
        is None
    )


def test_generic_thermal_banner_does_not_override_explicit_flow_history():
    report = inspect_flow_log("Solving Flow and Thermal\n" + _sst_history())
    assert report["final_equations_complete"]
    assert report["final_residual_criteria_met"] is True
    assert report["numerical_convergence"] == "not_established"


def test_coupled_history_still_requires_energy_even_when_row_is_missing():
    text = "Solving Flow and Thermal\n" + _sst_history().replace(
        "Steady-state convergence history - Flow simulation",
        "Steady-state convergence history - Coupled thermal/flow simulation",
    )
    report = inspect_flow_log(text)
    assert not report["final_equations_complete"]
    assert report["final_residual_criteria_met"] is None


def test_unclassified_thermal_banner_still_requires_energy():
    text = "Solving Flow and Thermal\n" + _sst_history().replace(
        "Steady-state convergence history - Flow simulation", "Unknown history"
    )
    assert not inspect_flow_log(text)["final_equations_complete"]


def test_native_sst_final_tke_balance_is_reported_without_accepting_solve():
    text = (Path(__file__).parent / "fixtures/sst-final-balance-excerpt.log").read_text()
    report = inspect_flow_log(text.replace("\n", "\r\r\n"))
    assert set(report["reported_imbalances"]) == {
        "momentum",
        "mass",
        "energy",
        "turbulent_kinetic_energy",
    }
    tke = report["reported_imbalances"]["turbulent_kinetic_energy"]
    assert tke["value"] == pytest.approx(8.199e-6)
    assert tke["units"] == "%"
    assert report["iterative_imbalance_history"] == []
    assert report["numerical_convergence"] == "not_established"
    assert report["results_validated"] is False
    # Repeated summaries are ambiguous; do not select an arbitrary last value.
    assert inspect_flow_log(text + text)["reported_imbalances"] == {}
    truncated = text[: text.index("8.199E-06") + len("8.199E-")]
    assert "turbulent_kinetic_energy" not in inspect_flow_log(truncated)["reported_imbalances"]
    with pytest.raises(ValueError, match="Nonfinite"):
        inspect_flow_log(text.replace("8.199E-06", "1e999"))
