"""Native mesh diagnostics with committed quality-criteria readback."""


def read_quality_settings(fem):
    from NXOpen.CAE import ModelCheck as mc

    solver, analysis = fem.GetSolverAndAnalysisType()
    setting = fem.ElementQualitySettings.GetElementQualitySetting(solver)
    enum = mc.TestValueTypes.TestType
    names = {
        str(getattr(enum, n)): n
        for n in dir(enum)
        if not n.startswith("_") and not callable(getattr(enum, n))
    }

    def read(v):
        result = {
            "test_type": names.get(str(v.GetTestType()), str(v.GetTestType())),
            "enabled": v.DoTest,
            "validator": str(v.GetValidator()),
            "has_criteria": v.HasCriteriaValue(),
        }
        if result["has_criteria"]:
            result["criteria"] = {}
            for n in ["Warning", "Error"]:
                raw = v.GetCriteriaValue(getattr(mc.TestValueTypes.CriteriaType, n))
                result["criteria"][n] = (
                    [{"unit": x.Name} if hasattr(x, "Name") else x for x in raw]
                    if isinstance(raw, tuple)
                    else raw
                )
        return result

    out = {
        "solver": solver,
        "analysis": analysis,
        "limit_option": str(setting.LimitValueOption),
        "element_specific": setting.UseElementSpecificValue,
        "tests": [],
    }
    for i in range(setting.TestValueCount):
        v = setting.GetTestValueByIndex(i)
        row = read(v)
        row["specific_count"] = v.ElementSpecificTestCount
        out["tests"].append(row)
    return out


def check_mesh_quality(fem, meshes, report_path=None):
    """Inspect current criteria and run native checks; never repair elements."""
    from nx_mcp.runtime import NXToolError

    if not meshes or any(mesh.OwningPart != fem for mesh in meshes):
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Select meshes owned by this FEM")
    if report_path is not None and (
        report_path.suffix.lower() != ".txt" or not report_path.parent.is_dir() or report_path.exists()
    ):
        raise NXToolError("NX_INVALID_ARGUMENT", "Report requires a new .txt path in an existing directory")
    settings = read_quality_settings(fem)
    builder = fem.ModelCheckMgr.CreateElementQualityCheckBuilder()
    result = None
    try:
        builder.SelectionList.Add(meshes)
        result = builder.ExecuteCheck()
        from NXOpen.CAE import ModelCheck as mc

        report = None
        if report_path is not None:
            import hashlib

            builder.ElementReportFormat = mc.ElementQualityCheckBuilder.ReportFormat.FailedAndWarning
            builder.WriteResultsToFile(str(report_path), result)
            data = report_path.read_bytes()
            if not data:
                raise NXToolError("NX_SIM_EMPTY_REPORT", "Native quality report is empty")
            report = {"path": str(report_path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                      "format": "native failed and warning elements", "parsed": False}
        enum = mc.TestValueTypes.TestType
        names = {
            str(getattr(enum, n)): n
            for n in dir(enum)
            if not n.startswith("_") and not callable(getattr(enum, n))
        }
        return {
            "settings": settings,
            "report": report,
            "element_count": result.ElementTestCount,
            "tests": [
                {
                    "type": names.get(str(t.TestType), str(t.TestType)),
                    "count": t.TestCount,
                    "errors": t.ErrorCount,
                    "warnings": t.WarnedCount,
                    "worst_value": t.WorstTestValue if t.HasTestValue else None,
                }
                for t in result.GetTestSummary()
            ],
            "repair_attempted": False,
            "scope": str(builder.CheckScopeOption),
            "limitations": [
                "Native check may highlight failed elements",
                "Does not establish CFD convergence",
                "Element-specific overrides are not enumerated; inspect element_specific flag",
            ],
        }
    finally:
        try:
            if result is not None:
                result.Dispose()
        finally:
            builder.Destroy()


def inspect_elements(fem, labels):
    import math

    from nx_mcp.runtime import NXToolError

    if (not isinstance(labels, list) or not 1 <= len(labels) <= 1000
            or any(type(n) is not int or n <= 0 for n in labels)
            or len(labels) != len(set(labels))):
        raise NXToolError("NX_INVALID_ARGUMENT", "Use 1..1000 distinct positive element labels")
    label_map = fem.BaseFEModel.FeelementLabelMap
    rows = []
    try:
        for label in labels:
            element = label_map.GetElement(label)
            if element is None or int(element.Label) != label:
                raise NXToolError("NX_SIM_ELEMENT_MISSING", "Requested element label is absent")
            nodes = []
            for node in element.GetNodes():
                p = node.Coordinates
                xyz = [float(p.X), float(p.Y), float(p.Z)]
                if not all(math.isfinite(v) for v in xyz):
                    raise NXToolError("NX_SIM_READBACK_MISMATCH", "Nonfinite node coordinate")
                nodes.append({"label": int(node.Label), "coordinates_mm": xyz})
            if not 1 <= len(nodes) <= 32:
                raise NXToolError("NX_SIM_UNSUPPORTED", "Element requires 1..32 readable nodes")
            mesh = element.Mesh
            xyz = [n["coordinates_mm"] for n in nodes]
            rows.append({"label": label, "shape": str(element.Shape), "mesh": mesh.JournalIdentifier,
                         "collector": mesh.MeshCollector.JournalIdentifier, "nodes": nodes,
                         "minimum_mm": [min(p[i] for p in xyz) for i in range(3)],
                         "maximum_mm": [max(p[i] for p in xyz) for i in range(3)],
                         "vertex_average_mm": [sum(p[i] for p in xyz)/len(xyz) for i in range(3)]})
        return {"elements": rows, "count": len(rows), "units": "mm", "coordinate_frame": "fem_part_absolute",
                "fem_path": fem.FullPath, "mesh_modified": False}
    finally:
        label_map.Dispose()
