"""Live constant-property solid thermal state, independent of native dirty flags."""

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.collector_state import inspect_collector, state_hash


def capture_analysis_thermal_state(sim):
    import NXOpen

    if sim.Simulation.ActiveSolution.AnalysisType != "Thermal":
        return None
    from nx_mcp.simcenter.boundary_state import capture_boundary_state

    material = capture_thermal_state(sim.FemPart, NXOpen)
    boundary = capture_boundary_state(sim, NXOpen)
    return {
        "adapter": 3,
        "boundary_scope": boundary["scope"],
        "scope": "solid_material_frame_properties_and_observed_thermal_boundaries",
        "owner_path": sim.FullPath,
        "material_state": material,
        "boundary_state": boundary,
        "errors": material["errors"] + boundary["errors"],
        "sha256": state_hash({"material": material["sha256"], "boundary": boundary["sha256"]})
        if material["sha256"] and boundary["sha256"]
        else None,
        "full_model_freshness": "not_verified",
    }


def compare_thermal_state(expected, actual):
    if not expected or not expected.get("sha256") or not actual or not actual.get("sha256"):
        return {"state": "not_verified", "reason": "live_thermal_state_evidence_missing"}
    if any(
        expected.get(key) != actual.get(key)
        for key in ("adapter", "scope", "owner_path", "boundary_scope")
    ):
        return {"state": "not_verified", "reason": "live_thermal_state_scope_mismatch"}
    if expected["sha256"] != actual["sha256"]:
        return {
            "state": "changed",
            "reason": "live_thermal_state_changed"
            if expected.get("adapter") in (2, 3)
            else "live_thermal_material_or_frame_changed",
        }
    return {"state": "matches", "scope": expected["scope"], "full_model_freshness": "not_verified"}


def require_thermal_state(expected, actual):
    comparison = compare_thermal_state(expected, actual)
    if comparison["state"] != "matches":
        raise NXToolError(
            "NX_SIM_LIVE_STATE_CHANGED",
            "Thermal state differs or cannot be verified; prepare a new job",
            details={"comparison": comparison, "mutation_outcome": "not_started"},
        )
    return comparison


def capture_thermal_state(fem, nx):
    """Scoped fingerprint, not full model freshness: no mesh, loads, contacts or flow."""

    def reference(value, kind, owner, fallback):
        return {
            "kind": kind,
            "journal_id": str(value.JournalIdentifier),
            "owner_path": owner.FullPath,
        }

    units = "mm" if fem.PartUnits == nx.BasePart.Units.Millimeters else "inch"
    rows, errors = [], []
    for collector in fem.BaseFEModel.MeshManager.GetMeshCollectors():
        if collector.CollectorNeutralType != "Solid":
            continue
        row = inspect_collector(fem, collector, reference, units)
        if not row.get("state_sha256"):
            errors.append({"collector": row["collector"], "reason": "assignment_read_failed"})
            continue
        row.pop("state_sha256")
        row.pop("state_scope")
        stored = row["orientation"]["stored_frame"]
        if stored:
            stored.pop("native_tag")
        try:
            table = collector.ElementPropertyTable.GetNamedPropertyTablePropertyValue(
                "Solid Property"
            ).PropertyTable
            options = table.GetPhysicalMaterialPropertyValue("material")
            try:
                material = options.Material
                properties = material.GetPropTable()
            finally:
                options.Dispose()
            names = {
                properties.GetPropertyNameByIndex(i) for i in range(properties.GetPropertyCount())
            }
            keys = ["ThermalConductivity", "SpecificHeat"]
            keys.append("MassDensity" if "MassDensity" in names else "MassDensityConstant")
            if "ThermalConductivity2" in names:
                keys += ["ThermalConductivity2", "ThermalConductivity3"]
            actual = {}
            for key in keys:
                wrapper = properties.GetScalarFieldWrapperPropertyValue(key)
                expression = wrapper.GetExpression()
                if expression is None or expression.Units is None:
                    raise ValueError("Requires constant scalar expressions with units")
                actual[key] = {
                    "value": expression.GetValueUsingUnits(nx.Expression.UnitsOption.Expression),
                    "units": expression.Units.Name,
                }
            row["thermal_properties"] = actual
            rows.append(row)
        except Exception as error:
            errors.append(
                {
                    "collector": row["collector"],
                    "reason": "constant_properties_unavailable",
                    "nx_code": getattr(error, "ErrorCode", None),
                }
            )
    rows.sort(key=lambda row: row["collector"]["journal_id"])
    result = {
        "adapter": 1,
        "scope": "solid_material_assignment_frame_constant_thermal_properties",
        "owner_path": fem.FullPath,
        "collectors": rows,
        "errors": errors,
        "full_model_freshness": "not_verified",
    }
    result["sha256"] = state_hash(rows) if rows and not errors else None
    return result
