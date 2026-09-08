from types import SimpleNamespace

from nx_mcp.simcenter.properties import read_properties


def test_dimensionless_field_readback_is_not_reported_as_failed():
    kinds = SimpleNamespace(String=1, Boolean=2, Integer=3, Double=4, ScalarFieldWrapper=6)
    field = SimpleNamespace(
        FieldExpressionUnits=None,
        GetFieldExpressionString=lambda: "0.3",
        JournalIdentifier="Field[1]",
        OwningPart=SimpleNamespace(FullPath="a.sim"),
        Tag=5,
    )
    table = SimpleNamespace(
        GetPropertyCount=lambda: 1,
        GetPropertyNameByIndex=lambda _: "dimensionless coefficient",
        GetBasePropertyType=lambda _: kinds.ScalarFieldWrapper,
        GetScalarFieldWrapperPropertyValue=lambda _: SimpleNamespace(
            GetExpression=lambda: None, GetField=lambda: field, GetFieldScaleFactor=lambda: 1.0
        ),
    )
    nx = SimpleNamespace(BasePropertyTable=SimpleNamespace(BasePropertyType=kinds))
    assert read_properties(table, nx) == [
        {
            "name": "dimensionless coefficient",
            "native_type": "6",
            "units": "dimensionless",
            "unit_symbol": None,
            "expression": "0.3",
            "representation": "field_expression",
            "field_scale": 1.0,
            "field_reference": {
                "journal_id": "Field[1]",
                "owner_path": "a.sim",
                "tag": 5,
                "lifetime": "current loaded document; not a cross-session reference",
            },
            "field_definition": {"kind": "numeric_constant", "value": 0.3},
            "evaluated_value": 0.3,
        }
    ]


def test_expression_wrapper_is_inspected_without_field_conversion():
    kinds = SimpleNamespace(String=1, Boolean=2, Integer=3, Double=4, ScalarFieldWrapper=6)
    expression = SimpleNamespace(GetFormula=lambda: "200", Units=SimpleNamespace(Name="W_per_m_K"))
    table = SimpleNamespace(
        GetPropertyCount=lambda: 1,
        GetPropertyNameByIndex=lambda _: "ThermalConductivity",
        GetBasePropertyType=lambda _: kinds.ScalarFieldWrapper,
        GetScalarFieldWrapperPropertyValue=lambda _: SimpleNamespace(
            GetExpression=lambda: expression, GetField=lambda: None
        ),
    )
    nx = SimpleNamespace(BasePropertyTable=SimpleNamespace(BasePropertyType=kinds))
    row = read_properties(table, nx)[0]
    assert row["expression"] == "200"
    assert row["units"] == "W_per_m_K"
    assert row["representation"] == "expression"
    assert "inspection_status" not in row


def test_unresolved_inherited_material_is_explicit():
    kinds = SimpleNamespace(
        String=1, Boolean=2, Integer=3, Double=4, ScalarFieldWrapper=6, PhysicalMaterial=10
    )
    table = SimpleNamespace(
        GetPropertyCount=lambda: 1,
        GetPropertyNameByIndex=lambda _: "material",
        GetBasePropertyType=lambda _: 10,
        GetMaterialPropertyValue=lambda _: (True, None),
    )
    nx = SimpleNamespace(BasePropertyTable=SimpleNamespace(BasePropertyType=kinds))
    row = read_properties(table, nx)[0]
    assert row["inherited"] is True
    assert row["value"] is None
    assert row["assignment_status"] == "unresolved"


def linked_fixture():
    state = {"temperature": 20.0, "journal": "Conditions[1]"}
    kinds = SimpleNamespace(String=1, Boolean=2, Integer=3, Double=4, ScalarFieldWrapper=6)
    child = SimpleNamespace(
        DescriptorNeutralName="External Conditions",
        GetPropertyCount=lambda: 1,
        GetPropertyNameByIndex=lambda _: "Temperature Value",
        GetBasePropertyType=lambda _: 4,
        GetBaseScalarWithDataPropertyValue=lambda _: (
            state["temperature"],
            SimpleNamespace(Name="Celsius", Symbol="°C"),
        ),
    )
    named = SimpleNamespace(
        OwningPart=SimpleNamespace(FullPath="fixture.sim"),
        JournalIdentifier="Conditions[1]",
        PropertyTable=child,
    )
    parent = SimpleNamespace(
        GetPropertyCount=lambda: 1,
        GetPropertyNameByIndex=lambda _: "Inlet Conditions",
        GetBasePropertyType=lambda _: 0,
        GetPropertyType=lambda _: -10,
        GetNamedPropertyTablePropertyValue=lambda _: named,
    )
    nx = SimpleNamespace(
        BasePropertyTable=SimpleNamespace(BasePropertyType=kinds),
        CAE=SimpleNamespace(
            PropertyTable=SimpleNamespace(PropertyType=SimpleNamespace(NamedPropertyTable=-10))
        ),
    )
    return state, parent, child, named, nx


def test_linked_conditions_expose_identity_and_changed_values():
    state, parent, _, named, nx = linked_fixture()
    first = read_properties(parent, nx)
    state["temperature"] = 25.0
    second = read_properties(parent, nx)
    assert first != second
    assert second[0]["properties"][0]["value"] == 25.0
    named.JournalIdentifier = "Conditions[replacement]"
    assert read_properties(parent, nx)[0]["value"] != first[0]["value"]


def test_linked_conditions_failure_is_not_a_verified_reference_only():
    _, parent, child, _, nx = linked_fixture()
    child.GetBasePropertyType = lambda _: 999
    row = read_properties(parent, nx)[0]
    assert row["inspection_status"] == "unverified_named_table_values"
    assert row["properties"][0]["inspection_status"] == "unsupported_property_type"


def test_named_table_cycle_and_budget_are_explicit():
    _, parent, child, named, nx = linked_fixture()
    child.GetBasePropertyType = lambda _: 0
    child.GetPropertyType = lambda _: -10
    child.GetNamedPropertyTablePropertyValue = lambda _: named
    row = read_properties(parent, nx)[0]
    assert row["inspection_status"] == "unverified_named_table_values"
    assert row["properties"][0]["inspection_status"] == "named_table_cycle_or_depth_limit"
    parent.GetPropertyCount = lambda: 600
    rows = read_properties(parent, nx)
    assert rows[-1]["inspection_status"] == "property_budget_exceeded"
    assert len(rows) <= 513


def test_empty_file_reference_is_distinct_from_untracked_external_content():
    kinds = SimpleNamespace(
        String=1, Boolean=2, Integer=3, Double=4, ScalarFieldWrapper=6, FileReference=16
    )
    state = {"path": ""}
    table = SimpleNamespace(
        GetPropertyCount=lambda: 1,
        GetPropertyNameByIndex=lambda i: "Temperature File",
        GetBasePropertyType=lambda name: 16,
        GetFileReferencePropertyValue=lambda name: state["path"],
    )
    nx = SimpleNamespace(BasePropertyTable=SimpleNamespace(BasePropertyType=kinds))
    empty = read_properties(table, nx)[0]
    assert empty["value"] == "" and "inspection_status" not in empty
    for value in ["temperature.csv", " "]:
        state["path"] = value
        row = read_properties(table, nx)[0]
        assert (
            row["value"] == value
            and row["inspection_status"] == "unverified_external_file_contents"
        )
