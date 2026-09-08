"""Disposable native curve-table check; undo leaves no fan attached to the SIM."""


def run(executor):
    import importlib

    from nx_mcp.simcenter import fan_field

    importlib.reload(fan_field)
    session = executor.session
    sim = session.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Activate isolated cavity benchmark SIM")
    manifest = {
        "name": "Synthetic fan table native verification",
        "pressure_convention": "static",
        "rpm": 1000,
        "reference_density_kg_m3": 1.2,
        "points": [
            {"flow_m3_s": 0, "pressure_Pa": 1},
            {"flow_m3_s": 0.0002, "pressure_Pa": 0.5},
            {"flow_m3_s": 0.0004, "pressure_Pa": 0},
        ],
        "stall_region": "Not modeled; synthetic benchmark only",
        "provenance": {"kind": "assumed", "source": "Synthetic unit-conversion benchmark"},
    }
    mark = session.SetUndoMark(executor.nxopen.Session.MarkVisibility.Visible, "Verify fan table")
    try:
        result = fan_field.create_fan_table(session, sim, manifest)
        table = result.pop("table")
        inlet = next(b for b in sim.Simulation.SimulationObjects if b.Name == "Duct Inlet")
        properties = inlet.PropertyTable
        original_mode = properties.GetIntegerPropertyValue("Mode Option")
        wrapper = sim.FieldManager.CreateScalarFieldWrapperWithField(table, 1.0)
        properties.SetScalarFieldWrapperPropertyValue("Fan Curve", wrapper)
        actual = properties.GetScalarFieldWrapperPropertyValue("Fan Curve")
        if actual.GetField() != table or actual.GetFieldScaleFactor() != 1.0:
            raise RuntimeError("Fan field attachment readback differs")
        result["attachment_readback"] = {
            "boundary": inlet.Name,
            "same_field": True,
            "scale_factor": actual.GetFieldScaleFactor(),
            "mode_unchanged": original_mode,
        }
        result["native_type"] = type(table).__name__
        result["property_descriptors"] = {}
        for key in ("Mode Option", "Fan Curve", "Pressure Rise"):
            result["property_descriptors"][key] = properties.GetPropertyDescriptorName(key)
        try:
            result["mode_choices"] = list(
                properties.GetStringArrayPropertyValueChoices("Mode Option")
            )
        except Exception as exc:
            result["mode_choices_error"] = {
                "message": str(exc),
                "nx_code": getattr(exc, "ErrorCode", None),
            }
        result["disposable_probe"] = True
        return result
    finally:
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
