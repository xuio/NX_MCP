"""Read actual native property values without assuming requested values persisted."""

import math


def read_properties(table, nxopen, *, _depth=0, _ancestors=(), _budget=None):
    if _budget is None:
        _budget = [512]
    enum = nxopen.BasePropertyTable.BasePropertyType
    rows = []
    for i in range(table.GetPropertyCount()):
        if _budget[0] <= 0:
            rows.append({"name": None, "inspection_status": "property_budget_exceeded"})
            break
        _budget[0] -= 1
        name = table.GetPropertyNameByIndex(i)
        # Licence configuration is outside this adapter's scope.
        if "licen" in name.lower():
            continue
        kind = table.GetBasePropertyType(name)
        row = {"name": name, "native_type": str(kind), "units": None}
        try:
            if kind == enum.String:
                row["value"] = table.GetStringPropertyValue(name)
            elif kind == getattr(enum, "FileReference", None):
                value = table.GetFileReferencePropertyValue(name)
                if not isinstance(value, str) or len(value) > 4096:
                    raise ValueError("Invalid or oversized native file reference")
                row.update(representation="file_reference", value=value)
                if value != "":
                    row["inspection_status"] = "unverified_external_file_contents"
            elif kind == enum.Boolean:
                row["value"] = table.GetBooleanPropertyValue(name)
            elif kind == enum.Integer:
                row["value"] = table.GetIntegerPropertyValue(name)
            elif kind == enum.Double:
                value, unit = table.GetBaseScalarWithDataPropertyValue(name)
                row.update(value=value, units=unit.Name if unit else "dimensionless")
                row["unit_symbol"] = getattr(unit, "Symbol", None) if unit else None
            elif kind in (getattr(enum, "DoubleArray", None), getattr(enum, "IntegerArray", None)):
                from nx_mcp.simcenter.property_values import bounded

                if kind == getattr(enum, "DoubleArray", None):
                    values, unit = table.GetScalarArrayWithUnitsPropertyValue(name)
                    values = bounded(values)
                    if not all(math.isfinite(v) for v in values):
                        raise ValueError("Nonfinite scalar array")
                    row.update(
                        value=values,
                        units=unit.Name if unit else "dimensionless",
                        unit_symbol=getattr(unit, "Symbol", None) if unit else None,
                    )
                else:
                    row["value"] = bounded(table.GetIntegerArrayPropertyValue(name))
                row["value_semantics"] = (
                    "native values; sentinel meaning depends on owning property"
                )
            elif kind == enum.ScalarFieldWrapper:
                wrapper = table.GetScalarFieldWrapperPropertyValue(name)
                expression = wrapper.GetExpression() if wrapper else None
                field = wrapper.GetField() if wrapper else None
                if expression is not None:
                    row.update(
                        expression=expression.GetFormula(),
                        units=expression.Units.Name if expression.Units else "dimensionless",
                        unit_symbol=getattr(expression.Units, "Symbol", None)
                        if expression.Units
                        else None,
                        representation="expression",
                    )
                elif field is None:
                    row["value"] = None
                else:
                    scale = wrapper.GetFieldScaleFactor()
                    if type(scale) not in (int, float) or not math.isfinite(scale):
                        raise ValueError("Nonfinite field scale")
                    row.update(
                        field_scale=scale,
                        field_reference={
                            "journal_id": field.JournalIdentifier,
                            "owner_path": field.OwningPart.FullPath,
                            "tag": int(field.Tag),
                            "lifetime": "current loaded document; not a cross-session reference",
                        },
                    )
                    if hasattr(field, "GetFieldExpressionString"):
                        formula = field.GetFieldExpressionString()
                        units = field.FieldExpressionUnits
                        row.update(
                            expression=formula,
                            units=units.Name if units else "dimensionless",
                            unit_symbol=getattr(units, "Symbol", None) if units else None,
                            representation="field_expression",
                        )
                        try:
                            constant = float(formula)
                            effective = constant * scale
                            if not math.isfinite(constant) or not math.isfinite(effective):
                                raise ValueError("Nonfinite field value")
                        except (TypeError, ValueError):
                            row["inspection_status"] = "unverified_field_definition"
                        else:
                            row.update(
                                field_definition={"kind": "numeric_constant", "value": constant},
                                evaluated_value=effective,
                            )
                    else:
                        from nx_mcp.simcenter.field_definition import read_supported_table

                        definition = read_supported_table(field)
                        row["representation"] = type(field).__name__
                        if definition is None:
                            row["inspection_status"] = "unsupported_field_type"
                        else:
                            row["field_definition"] = definition
            elif kind == getattr(enum, "PhysicalMaterial", None):
                inherited, material = table.GetMaterialPropertyValue(name)
                row.update(
                    inherited=inherited,
                    value=(
                        {"name": material.Name, "owner": material.OwningPart.FullPath}
                        if material is not None
                        else None
                    ),
                    assignment_status="assigned" if material is not None else "unresolved",
                )
            else:
                from nx_mcp.simcenter.property_values import read_cae_value

                decoded = read_cae_value(table, name, nxopen)
                if decoded is not None:
                    row.update(decoded)
                    rows.append(row)
                    continue
                cae = getattr(nxopen, "CAE", None)
                named_kind = getattr(
                    getattr(getattr(cae, "PropertyTable", None), "PropertyType", None),
                    "NamedPropertyTable",
                    None,
                )
                if (
                    named_kind is not None
                    and hasattr(table, "GetPropertyType")
                    and table.GetPropertyType(name) == named_kind
                ):
                    named = table.GetNamedPropertyTablePropertyValue(name)
                    row["representation"] = "named_property_table"
                    row["value"] = None
                    if named is not None:
                        identity = (named.OwningPart.FullPath, named.JournalIdentifier)
                        row["value"] = {
                            "journal_id": identity[1],
                            "owner_path": identity[0],
                            "descriptor": named.PropertyTable.DescriptorNeutralName,
                            "lifetime": "owner document revision; inspect again after regeneration",
                        }
                        if identity in _ancestors or _depth >= 2:
                            row["inspection_status"] = "named_table_cycle_or_depth_limit"
                        else:
                            nested = read_properties(
                                named.PropertyTable,
                                nxopen,
                                _depth=_depth + 1,
                                _ancestors=(*_ancestors, identity),
                                _budget=_budget,
                            )
                            for child in nested:
                                if child.get("representation") == "expression":
                                    try:
                                        expression = (
                                            named.PropertyTable.GetScalarFieldWrapperPropertyValue(
                                                child["name"]
                                            ).GetExpression()
                                        )
                                        value = expression.GetValueUsingUnits(
                                            nxopen.Expression.UnitsOption.Expression
                                        )
                                        if not math.isfinite(value):
                                            raise ValueError("Nonfinite named-table expression")
                                        child["evaluated_value"] = value
                                    except Exception:
                                        child["inspection_status"] = "evaluation_failed"
                            row["properties"] = nested
                            if any(child.get("inspection_status") for child in nested):
                                row["inspection_status"] = "unverified_named_table_values"
                else:
                    row["inspection_status"] = "unsupported_property_type"
        except Exception as exc:
            if getattr(exc, "code", None) == "NX_SIM_INSPECTION_ROLLBACK_FAILED":
                raise
            row.update(inspection_status="read_failed", nx_code=getattr(exc, "ErrorCode", None))
            from nx_mcp.runtime import NXToolError

            if isinstance(exc, NXToolError):
                row["inspection_error"] = {"code": exc.code, "message": str(exc)}
        rows.append(row)
    return rows
