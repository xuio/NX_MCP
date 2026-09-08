"""Supported native field definitions for boundary inspection, without solver inference."""


def read_supported_table(field):
    import NXOpen.Fields as fields

    from nx_mcp.simcenter.fan_field import inspect_fan_table

    if not isinstance(field, fields.FieldTable):
        return None
    # This validates the native samples, units and interpolation against the
    # bounded retained manifest. Unregistered or changed tables fail explicitly.
    inspected = inspect_fan_table(field.OwningPart, field)
    return {
        "kind": "validated_fan_table",
        "manifest": inspected["manifest"],
        "native_samples_si": inspected["readback"],
        "scale_application": "scalar wrapper scales dependent pressure values only",
        "definition_scope": "table values and interpolation; not solver or boundary semantics",
    }
