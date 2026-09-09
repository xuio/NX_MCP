"""Bounded native controller API probe; sensor support and numerical behavior unverified."""


def run(executor):
    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    session = executor.session
    candidates = []
    for p in session.Parts:
        if isinstance(p, cae.SimPart) and "ui-benchmarks" in p.FullPath:
            sol = p.Simulation.ActiveSolution
            if (
                sol is not None
                and sol.SolverType == "NX MULTIPHYSICS"
                and sol.AnalysisType == "Coupled Thermal-Flow"
            ):
                candidates.append(p)
    if not candidates:
        return {"candidates": [], "mutation": "not_started"}
    sim = candidates[0]
    previous = session.Parts.BaseWork
    prev_id = executor._reference(previous, "part", previous, "part")["id"]
    flags = [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    executor._sim_activate(executor._reference(sim, "part", sim, "SIM")["id"])
    before = {int(t.Tag) for t in sim.ModelingObjectPropertyTables}
    mark = session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "NX MCP controller descriptor probe"
    )
    result = {
        "document": sim.FullPath,
        "hypothesis": "Installed descriptor factory produces native sensor and speed-field slots",
    }
    try:
        model = sim.ModelingObjectPropertyTables.CreateModelingObjectPropertyTable(
            "Fan Speed Controller",
            "NX MULTIPHYSICS - Coupled Thermal-Flow",
            "NX MULTIPHYSICS",
            "MCP_CONTROLLER_PROBE",
            0,
        )
        table = model.PropertyTable
        result["sensor_property_type"] = str(table.GetPropertyType("Temperature Sensor Entity"))
        result["reference_enum_available"] = hasattr(cae.PropertyTable.PropertyType, "Reference")
        result["reference_enum_value"] = str(cae.PropertyTable.PropertyType.Reference)
        try:
            result["sensor_before"] = (
                table.GetReferencePropertyValue("Temperature Sensor Entity") is None
            )
        except Exception as e:
            result["unset_sensor_read_error"] = {
                "message": str(e),
                "nx_code": getattr(e, "ErrorCode", None),
            }
        from nx_mcp.simcenter.selections import face_inventory

        sensor = face_inventory(session, sim)["rows"][0]["face"]
        table.SetReferencePropertyValue("Temperature Sensor Entity", sensor)
        actual = table.GetReferencePropertyValue("Temperature Sensor Entity")
        result["sensor_binding"] = {
            "same_object": actual == sensor,
            "type": type(actual).__name__,
            "journal_id": actual.JournalIdentifier,
            "owner": actual.OwningPart.FullPath,
        }
        import NXOpen.Fields as fields

        field = sim.FieldManager.CreateFieldTableFromData(
            "MCP_SPEED_PROBE",
            sim.UnitCollection.FindObject("Celsius"),
            sim.UnitCollection.FindObject("DegreesPerSecond"),
            fields.FieldVariable.ValueType.Real,
            [20.0, 6000.0, 60.0, 12000.0],
        )
        wrapper = sim.FieldManager.CreateScalarFieldWrapperWithField(field, 1.0)
        table.SetScalarFieldWrapperPropertyValue("Speed versus Temperature Table", wrapper)
        linked = table.GetScalarFieldWrapperPropertyValue("Speed versus Temperature Table")
        result["speed_binding"] = {
            "same_field": linked.GetField() == field,
            "scale": linked.GetFieldScaleFactor(),
            "independent": [
                (v.Units.Name, list(field.GetData(v))) for v in field.GetIndependentVariables()
            ],
            "dependent": [
                (v.Units.Name, list(field.GetData(v))) for v in field.GetDependentVariables()
            ],
        }
        inlet = next(b for b in sim.Simulation.SimulationObjects if b.DescriptorName == "Inlet")
        props = inlet.PropertyTable
        props.SetNamedPropertyTablePropertyValue("Fan Speed Controller", model)
        props.SetIntegerPropertyValue("Controller Type", 2)
        props.SetBaseScalarWithDataPropertyValue(
            "Nominal Fan Speed", 12000.0, sim.UnitCollection.FindObject("DegreesPerSecond")
        )
        nominal, unit = props.GetBaseScalarWithDataPropertyValue("Nominal Fan Speed")
        result["fan_binding"] = {
            "same_controller": props.GetNamedPropertyTablePropertyValue("Fan Speed Controller")
            == model,
            "controller_type": props.GetIntegerPropertyValue("Controller Type"),
            "nominal": nominal,
            "units": unit.Name,
            "mode": props.GetIntegerPropertyValue("Mode Option"),
        }
        result["controller_properties"] = read_properties(table, nx)
        result["reference_methods"] = [m for m in dir(table) if "Reference" in m or "Tagged" in m]
        result["fan_boundaries"] = [
            {
                "name": b.Name,
                "descriptor": b.DescriptorName,
                "properties": read_properties(b.PropertyTable, nx),
            }
            for b in sim.Simulation.SimulationObjects
            if b.DescriptorName in ["Inlet", "Internal Fan"]
        ][:2]
    except Exception as exc:
        result["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "nx_code": getattr(exc, "ErrorCode", None),
        }
    finally:
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
        executor._sim_activate(prev_id)
    result["table_inventory_restored"] = before == {
        int(t.Tag) for t in sim.ModelingObjectPropertyTables
    }
    result["flags_restored"] = flags == [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    return result
