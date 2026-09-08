from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.contact import validate_contact


@pytest.mark.parametrize("mode,value", [("resistance", 0.5), ("conductance", 2.0)])
def test_explicit_positive_total_modes(mode, value):
    validate_contact([NS(Tag=1)], [NS(Tag=2)], mode, value, "contact", "assumed")


@pytest.mark.parametrize(
    "mode,value",
    [
        ("porous", 1),
        ("resistance", 0),
        ("conductance", -1),
        ("resistance", True),
        ("resistance", float("nan")),
        ("conductance", float("inf")),
    ],
)
def test_invalid_inputs_rejected(mode, value):
    with pytest.raises(NXToolError):
        validate_contact([NS(Tag=1)], [NS(Tag=2)], mode, value, "contact", "assumed")


@pytest.mark.parametrize("primary,secondary", [([], [2]), ([1, 1], [2]), ([1], [1]), ([1], [])])
def test_missing_duplicate_and_overlapping_faces_rejected(primary, secondary):
    with pytest.raises(NXToolError):
        validate_contact(
            [NS(Tag=t) for t in primary],
            [NS(Tag=t) for t in secondary],
            "resistance",
            0.5,
            "contact",
            "assumed",
        )


def test_direct_expression_readback_is_verified_without_field_value_key():
    from nx_mcp.simcenter.contact import verify_contact_value

    row = {
        "representation": "expression",
        "expression": "0.5",
        "units": "ThermalResistance_Metric4",
    }
    verify_contact_value(row, 0.5, "ThermalResistance_Metric4")
    for change in (
        {"units": "dimensionless"},
        {"expression": "0"},
        {"expression": "nan"},
        {"representation": "field_expression"},
    ):
        with pytest.raises(NXToolError):
            verify_contact_value({**row, **change}, 0.5, "ThermalResistance_Metric4")
