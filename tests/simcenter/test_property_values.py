from types import SimpleNamespace as NS

import pytest

from nx_mcp.simcenter.property_values import bounded, read_cae_value


def fixture(kind):
    types = NS(Text=-1, NamedPropertyTableArray=-8, Vector=-4, Axis=-11, VectorFieldWrapper=-3)
    return NS(GetPropertyType=lambda _: kind), NS(
        CAE=NS(PropertyTable=NS(PropertyType=types)),
        Expression=NS(UnitsOption=NS(Expression=1)),
        Session=NS(
            GetSession=lambda: NS(
                Parts=[],
                SetUndoMark=lambda *a: 1,
                UndoToMark=lambda *a: None,
                DeleteUndoMark=lambda *a: None,
            ),
            MarkVisibility=NS(Invisible=0),
        ),
    )


def test_text_and_arrays_are_bounded_without_silent_truncation():
    table, nx = fixture(-1)
    table.GetTextPropertyValue = lambda _: ["a", "b"]
    assert read_cae_value(table, "description", nx)["value"] == ["a", "b"]
    table.GetTextPropertyValue = lambda _: ["x" * 65537]
    with pytest.raises(ValueError):
        read_cae_value(table, "description", nx)
    with pytest.raises(ValueError):
        bounded(range(1001))


def test_nonempty_linked_table_array_cannot_claim_value_inspection():
    table, nx = fixture(-8)
    table.GetNamedPropertyTableArrayPropertyValue = lambda _: []
    assert read_cae_value(table, "tables", nx)["value"] == []
    table.GetNamedPropertyTableArrayPropertyValue = lambda _: [
        NS(JournalIdentifier="T[1]", OwningPart=NS(FullPath="a.sim"))
    ]
    assert (
        read_cae_value(table, "tables", nx)["inspection_status"]
        == "unverified_named_table_array_values"
    )


def test_vector_expressions_read_values_and_reject_missing_or_nonfinite_components():
    table, nx = fixture(-3)
    values = [1.0, 2.0, 3.0]
    wrapper = NS(
        GetField=lambda: None,
        GetExpressionByIndex=lambda i: NS(
            GetValueUsingUnits=lambda _: values[i],
            GetFormula=lambda: str(values[i]),
            Units=NS(Name="mm_per_sec", Symbol="mm/s"),
        ),
    )
    table.GetVectorFieldWrapperPropertyValue = lambda _: wrapper
    assert [r["evaluated_value"] for r in read_cae_value(table, "v", nx)["components"]] == values
    values[1] = float("nan")
    with pytest.raises(ValueError):
        read_cae_value(table, "v", nx)
    wrapper.GetField = lambda: NS(JournalIdentifier="F[1]", OwningPart=NS(FullPath="a.sim"))
    assert read_cae_value(table, "v", nx)["inspection_status"] == "unverified_vector_field_scales"


def test_null_direction_is_distinct_from_unsupported_vector_field():
    table, nx = fixture(-4)
    table.GetVectorPropertyValue = lambda _: None
    assert read_cae_value(table, "direction", nx) == {"representation": "vector", "value": None}


def test_failed_getter_rollback_is_explicit_partial_state():
    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.property_values import preserved_getter_state

    _, nx = fixture(-3)
    part = NS(Tag=1, IsModified=False)
    session = NS(
        Parts=[part],
        SetUndoMark=lambda *a: 1,
        UndoToMark=lambda *a: None,
        DeleteUndoMark=lambda *a: None,
    )
    nx.Session.GetSession = lambda: session
    with pytest.raises(NXToolError) as error, preserved_getter_state(nx):
        part.IsModified = True
    assert error.value.code == "NX_SIM_INSPECTION_ROLLBACK_FAILED"
    assert error.value.details["mutation_outcome"] == "partial"
