"""Reject wrong units, inactive selectors and missing membership in the export audit."""

import runpy
from pathlib import Path

import pytest

inspect = runpy.run_path(
    str(Path(__file__).parents[2] / "examples/simcenter/audit_active_field_export.py")
)["inspect"]


@pytest.fixture
def data():
    return (Path(__file__).parent / "evidence/active-field-export-excerpt.xml").read_bytes()


def test_native_export_preserves_active_scale(data):
    result = inspect(data)
    assert result["power_W"] == 0.2
    assert result["selected_element_count"] == 764


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (b"2.0000000E+05", b"1.0000000E+05"),
        (b"<System>Millimeters", b"<System>Meters"),
        (
            b'<Property name="Per Element">\n      <Value>0',
            b'<Property name="Per Element">\n      <Value>1',
        ),
        (b'<Selection step="1">', b'<Selection step="2">'),
    ],
)
def test_incompatible_export_never_passes(data, before, after):
    assert before in data
    with pytest.raises(ValueError):
        inspect(data.replace(before, after))
