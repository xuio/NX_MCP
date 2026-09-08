"""Native mesh diagnostics with committed quality-criteria readback."""


def read_quality_settings(fem):
    import NXOpen.CAE.ModelCheck as mc

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


def check_mesh_quality(fem, meshes):
    """Inspect current criteria and run native checks; never repair elements."""
    from nx_mcp.runtime import NXToolError

    if not meshes or any(mesh.OwningPart != fem for mesh in meshes):
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Select meshes owned by this FEM")
    settings = read_quality_settings(fem)
    builder = fem.ModelCheckMgr.CreateElementQualityCheckBuilder()
    result = None
    try:
        builder.SelectionList.Add(meshes)
        result = builder.ExecuteCheck()
        import NXOpen.CAE.ModelCheck as mc

        enum = mc.TestValueTypes.TestType
        names = {
            str(getattr(enum, n)): n
            for n in dir(enum)
            if not n.startswith("_") and not callable(getattr(enum, n))
        }
        return {
            "settings": settings,
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
