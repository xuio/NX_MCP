from pathlib import Path

import pytest

from nx_mcp.simcenter.coupled_input import inspect_ambient_temperature


@pytest.fixture
def deck():
    return (Path(__file__).parent / "evidence/coupled-cae-scalar-deck.xml").read_bytes()


def test_actual_native_export_mismatch(deck):
    report = inspect_ambient_temperature(deck, 20.0, "Celsius")
    assert not report["matches"]
    assert report["exported_value"] == 0.0


def test_matching_value_does_not_establish_readiness(deck):
    report = inspect_ambient_temperature(deck, 0.0, "Celsius")
    assert report["matches"]
    assert "not complete solve readiness" in report["scope"]


@pytest.mark.parametrize("value,unit", [(20, "Kelvin"), (float("nan"), "Celsius")])
def test_unverified_native_representation_rejected(deck, value, unit):
    with pytest.raises(ValueError):
        inspect_ambient_temperature(deck, value, unit)


def test_unverified_export_units_rejected(deck):
    with pytest.raises(ValueError, match="convention"):
        inspect_ambient_temperature(
            deck.replace(b"-2.7315000E+02", b"0.0000000E+00"), 20, "Celsius"
        )


@pytest.fixture
def pressure_deck():
    return (Path(__file__).parent / "evidence/finned-pressure-r1.xml").read_bytes()


def test_actual_active_pressure_mismatch(pressure_deck):
    from nx_mcp.simcenter.coupled_input import inspect_ambient_pressure

    report = inspect_ambient_pressure(pressure_deck, 0, 101325.0)
    assert report["stored_absolute_pressure_active"]
    assert report["exported_value"] == 0
    assert not report["matches"]


def test_inactive_absolute_pressure_is_not_a_mismatch(deck):
    from nx_mcp.simcenter.coupled_input import inspect_ambient_pressure

    report = inspect_ambient_pressure(deck, 1)
    assert report["matches"]
    assert not report["stored_absolute_pressure_active"]
    assert "density not verified" in report["scope"]


def test_specified_pressure_units_and_success(pressure_deck):
    import xml.etree.ElementTree as ET

    from nx_mcp.simcenter.coupled_input import inspect_ambient_pressure

    root = ET.fromstring(pressure_deck)
    root.find(
        "./SolutionParameters/AmbientConditions/Property[@name='Absolute Pressure']/Value"
    ).text = "101.325"
    assert inspect_ambient_pressure(ET.tostring(root), 0, 101325)["matches"]
    root.find("./Units/ForceConversionFactor").text = "1"
    with pytest.raises(ValueError, match="convention"):
        inspect_ambient_pressure(ET.tostring(root), 0, 101325)


def test_pressure_selector_disagreement_rejected(pressure_deck):
    from nx_mcp.simcenter.coupled_input import inspect_ambient_pressure

    with pytest.raises(ValueError, match="selector"):
        inspect_ambient_pressure(pressure_deck, 1)
