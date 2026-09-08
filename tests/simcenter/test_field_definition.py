from types import SimpleNamespace as NS

import pytest

from nx_mcp.simcenter.field_definition import read_supported_table
from nx_mcp.simcenter.properties import read_properties


def test_supported_table_uses_native_inspector_and_propagates_mismatch(monkeypatch):
    import sys

    from nx_mcp.simcenter import fan_field

    class Table:
        OwningPart = object()

    monkeypatch.setitem(sys.modules, "NXOpen.Fields", NS(FieldTable=Table))
    monkeypatch.setitem(sys.modules, "NXOpen", NS(Fields=sys.modules["NXOpen.Fields"]))
    inspected = {"manifest": {"interpolation": "linear"}, "readback": {"pressure_Pa": [2, 0]}}
    monkeypatch.setattr(fan_field, "inspect_fan_table", lambda owner, field: inspected)
    assert read_supported_table(Table())["native_samples_si"] == inspected["readback"]
    assert read_supported_table(object()) is None

    def fail(*args):
        raise ValueError("Native curve changed")

    monkeypatch.setattr(fan_field, "inspect_fan_table", fail)
    with pytest.raises(ValueError, match="Native curve changed"):
        read_supported_table(Table())


def test_table_values_and_wrapper_scale_are_both_preserved(monkeypatch):
    from nx_mcp.simcenter import field_definition

    values = [2.0, 0.0]
    monkeypatch.setattr(
        field_definition,
        "read_supported_table",
        lambda field: {
            "kind": "validated_fan_table",
            "native_samples_si": {"pressure_Pa": list(values)},
        },
    )
    field = NS(JournalIdentifier="fan", OwningPart=NS(FullPath="test.sim"), Tag=1)
    scale = [2.0]
    wrapper = NS(
        GetExpression=lambda: None, GetField=lambda: field, GetFieldScaleFactor=lambda: scale[0]
    )
    kinds = NS(String=1, Boolean=2, Integer=3, Double=4, ScalarFieldWrapper=6)
    nx = NS(BasePropertyTable=NS(BasePropertyType=kinds))
    table = NS(
        GetPropertyCount=lambda: 1,
        GetPropertyNameByIndex=lambda i: "Fan",
        GetBasePropertyType=lambda name: 6,
        GetScalarFieldWrapperPropertyValue=lambda name: wrapper,
    )
    first = read_properties(table, nx)[0]
    assert first["field_scale"] == 2 and "inspection_status" not in first
    scale[0] = 3
    second = read_properties(table, nx)[0]
    assert first != second and first["field_definition"] == second["field_definition"]
    values[0] = 4
    third = read_properties(table, nx)[0]
    assert second["field_definition"] != third["field_definition"]


def test_native_definition_error_is_preserved_in_property_readback(monkeypatch):
    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter import field_definition

    def fail(field):
        raise NXToolError("NX_SIM_MANIFEST_INVALID", "Fan metadata is missing or corrupt")

    monkeypatch.setattr(field_definition, "read_supported_table", fail)
    kinds = NS(String=1, Boolean=2, Integer=3, Double=4, ScalarFieldWrapper=6)
    field = NS(JournalIdentifier="fan", OwningPart=NS(FullPath="test.sim"), Tag=1)
    wrapper = NS(
        GetExpression=lambda: None, GetField=lambda: field, GetFieldScaleFactor=lambda: 1.0
    )
    table = NS(
        GetPropertyCount=lambda: 1,
        GetPropertyNameByIndex=lambda i: "Fan Curve",
        GetBasePropertyType=lambda name: 6,
        GetScalarFieldWrapperPropertyValue=lambda name: wrapper,
    )
    row = read_properties(table, NS(BasePropertyTable=NS(BasePropertyType=kinds)))[0]
    assert row["inspection_status"] == "read_failed"
    assert row["inspection_error"]["code"] == "NX_SIM_MANIFEST_INVALID"
