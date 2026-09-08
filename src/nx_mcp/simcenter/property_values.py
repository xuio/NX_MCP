"""Bounded readback for documented CAE text, directions and vector wrappers."""

import math
from contextlib import contextmanager

from nx_mcp.runtime import NXToolError


def bounded(values, maximum=1000):
    values = list(values)
    if len(values) > maximum:
        raise ValueError("Property array exceeds inspection bound")
    return values


def xyz(value):
    result = [value.X, value.Y, value.Z]
    if not all(math.isfinite(v) for v in result):
        raise ValueError("Nonfinite coordinate")
    return result


def read_cae_value(table, name, nx):
    types = getattr(getattr(getattr(nx, "CAE", None), "PropertyTable", None), "PropertyType", None)
    if types is None or not hasattr(table, "GetPropertyType"):
        return None
    kind = table.GetPropertyType(name)
    if kind == getattr(types, "Text", None):
        lines = bounded(table.GetTextPropertyValue(name))
        if not all(isinstance(v, str) for v in lines) or sum(map(len, lines)) > 65536:
            raise ValueError("Invalid or oversized text property")
        return {"representation": "text_lines", "value": lines}
    if kind == getattr(types, "NamedPropertyTableArray", None):
        tables = bounded(table.GetNamedPropertyTableArrayPropertyValue(name))
        if not tables:
            return {"representation": "named_table_array", "value": []}
        # Preserve associations; value recursion for nonempty arrays is not yet verified.
        return {
            "representation": "named_table_array",
            "value": [
                None
                if t is None
                else {"journal_id": t.JournalIdentifier, "owner_path": t.OwningPart.FullPath}
                for t in tables
            ],
            "inspection_status": "unverified_named_table_array_values",
        }
    for kind_name, getter, direction_property in (
        ("Vector", "GetVectorPropertyValue", "Vector"),
        ("Axis", "GetAxisPropertyValue", "DirectionVector"),
    ):
        if kind != getattr(types, kind_name, None):
            continue
        obj = getattr(table, getter)(name)
        if obj is None:
            return {"representation": kind_name.lower(), "value": None}
        owner = obj.OwningPart
        return {
            "representation": kind_name.lower(),
            "value": {
                "journal_id": obj.JournalIdentifier,
                "owner_path": owner.FullPath,
                "origin": xyz(obj.Origin),
                "direction": xyz(getattr(obj, direction_property)),
                "coordinate_frame": "owner_part_absolute",
                "origin_units": "mm"
                if owner.PartUnits == nx.BasePart.Units.Millimeters
                else "inch",
                "native_sense_or_type": str(obj.Sense if kind_name == "Vector" else obj.Type),
            },
        }
    if kind == getattr(types, "VectorFieldWrapper", None):
        with preserved_getter_state(nx):
            return read_vector_wrapper(table, name, nx)
    return None


@contextmanager
def preserved_getter_state(nx):
    """NX 2606 vector getters can create expressions; undo their local side effects."""
    session = nx.Session.GetSession()
    before = {int(p.Tag): bool(p.IsModified) for p in session.Parts}
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Invisible, "MCP vector inspection")
    try:
        yield
    finally:
        try:
            session.UndoToMark(mark, None)
            session.DeleteUndoMark(mark, None)
            if before != {int(p.Tag): bool(p.IsModified) for p in session.Parts}:
                raise ValueError("Document flags differ after getter rollback")
        except Exception as error:
            raise NXToolError(
                "NX_SIM_INSPECTION_ROLLBACK_FAILED",
                "Native getter recovery failed; inspect the session before further work",
                details={"mutation_outcome": "partial"},
            ) from error


def read_vector_wrapper(table, name, nx):
    wrapper = table.GetVectorFieldWrapperPropertyValue(name)
    if wrapper is None:
        return {"representation": "vector_wrapper", "value": None}
    field = wrapper.GetField()
    if field is not None:
        return {
            "representation": "vector_field",
            "inspection_status": "unverified_vector_field_scales",
            "field_reference": {
                "journal_id": field.JournalIdentifier,
                "owner_path": field.OwningPart.FullPath,
            },
        }
    expressions = [wrapper.GetExpressionByIndex(i) for i in range(3)]
    if all(e is None for e in expressions):
        return {"representation": "vector_expressions", "value": None}
    if any(e is None for e in expressions):
        raise ValueError("Incomplete vector expression components")
    values = []
    for expression in expressions:
        value = expression.GetValueUsingUnits(nx.Expression.UnitsOption.Expression)
        if not math.isfinite(value):
            raise ValueError("Nonfinite vector component")
        unit = expression.Units
        values.append(
            {
                "expression": expression.GetFormula(),
                "evaluated_value": value,
                "units": unit.Name if unit else "dimensionless",
                "unit_symbol": getattr(unit, "Symbol", None) if unit else None,
            }
        )
    return {
        "representation": "vector_expressions",
        "components": values,
        "coordinate_frame": "owning_property_convention; not inferred",
    }
