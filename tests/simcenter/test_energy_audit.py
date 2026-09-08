"""Check conservation-audit math; native receipts establish actual solver values."""

import runpy
from pathlib import Path

import pytest

AUDIT = runpy.run_path(str(Path(__file__).parents[2] / "examples/simcenter/audit_transient.py"))[
    "audit_energy"
]


def fixture(tmp_path, energy):
    (tmp_path / "fixture-Conduction.xml").write_text(
        "<SolutionFile><Units><LengthConversionFactor>1000</LengthConversionFactor><ForceConversionFactor>1000</ForceConversionFactor></Units></SolutionFile>"
    )
    (tmp_path / "fixture-Conduction_report.log").write_text(
        "Time= 2025\nGroup: BENCHMARK_C_POWER\n 25.00 1 25.00 2 25.00 1.00E+05 2.43E+06 2.70E-03\n"
    )
    (tmp_path / "fixture-Conduction.log").write_text(
        "Fluid ambient group 2.000E+01 9.9E+04 " + energy + "\n"
    )


def test_accounts_for_stored_heat_and_print_rounding(tmp_path):
    fixture(tmp_path, "1.9035E+08")
    result = AUDIT(tmp_path)
    assert result["energy_balance_passed"]
    assert result["applied_energy_J"] == 202.5
    assert result["stored_energy_bound_J"][0] < 12.15 < result["stored_energy_bound_J"][1]
    assert result["rejected_energy_rounding_J"] == pytest.approx(0.005)
    assert not result["benchmark_accepted"]


def test_large_energy_deficit_cannot_pass(tmp_path):
    fixture(tmp_path, "1.0000E+08")
    result = AUDIT(tmp_path)
    assert not result["energy_balance_passed"]
    assert result["worst_normalized_residual"] > 0.4
