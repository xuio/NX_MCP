import pytest

from nx_mcp.simcenter.thermal_balance import inspect_thermal_balances


def test_partial_and_repeated_summaries_are_not_combined():
    text = "Summary for thermal elements\nHeat flow into sinks = 1D6\nSummary for thermal elements\nHeat load into elements = 2e6\n"
    result = inspect_thermal_balances(text, power_unit="mN-mm/s")
    assert len(result["summaries"]) == 2
    assert result["summaries"][0]["values"] == {"heat_flow_into_sinks": 1e6}
    assert result["summaries"][1]["values"] == {"heat_load_into_elements": 2e6}
    assert all(r["state"] == "incomplete" for r in result["summaries"])
    assert not result["conservation_accepted"]


def test_duplicate_and_overflow_values_fail_closed():
    result = inspect_thermal_balances(
        "Summary for thermal elements\nHeat flow into sinks = 1\nHeat flow into sinks = 2\nHeat load into elements = 1e999\n",
        power_unit="W",
    )
    row = result["summaries"][0]
    assert row["state"] == "incomplete"
    assert {i["reason"] for i in row["issues"]} == {"duplicate_field", "nonfinite_value"}


def test_units_are_not_guessed():
    with pytest.raises(ValueError):
        inspect_thermal_balances("", power_unit="unknown")
