"""Read requested regional density; do not infer it from a reference-density log row."""


def run(executor):
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.results import acquire_result
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    s = executor.session
    sim = s.Parts.BaseWork
    if not any(
        name in sim.FullPath
        for name in (
            "E-finned-layer-extended-20260908-r1",
            "E-finned-density-path-20260908-r1",
            "E-finned-stock-copy-run-20260908-r1",
        )
    ):
        raise ValueError("Activate the isolated density-output benchmark")
    manager = s.ResultManager
    result, owned = acquire_result(s, sim)
    params = access = None
    try:
        types = result.GetLoadcases()[0].GetIterations()[0].GetResultTypes()
        names = [t.Name for t in types]
        density = [t for t in types if "density" in t.Name.casefold()]
        if len(density) != 1:
            return {
                "field_names": names,
                "density_verified": False,
                "reason": "Expected one requested density field",
            }
        params = manager.CreateResultParameters()
        params.SetLoadcaseIteration(0, 0)
        params.SetGenericResultType(density[0])
        params.SetResultComponent(cae.Result.Component.Scalar)
        params.SetUnit(sim.UnitCollection.FindObject("KilogramPerCubicMeter"))
        access = manager.CreateResultAccess(result, params)
        location, low, high, low_id, high_id, low_sub, high_sub = access.AskMinMaxLocation()
        return {
            "field_names": names,
            "density_field": density[0].Name,
            "units": "kg/m3",
            "minimum": low,
            "maximum": high,
            "minimum_native_id": low_id,
            "maximum_native_id": high_id,
            "minimum_native_sub_id": low_sub,
            "maximum_native_sub_id": high_sub,
            "location": str(location),
            "expected_constant_density": 1.2,
            "constant_density_matches": abs(low - 1.2) < 1e-5 and abs(high - 1.2) < 1e-5,
            "reference_lifetime": "indices apply only to this result revision",
            "result_freshness": "not_verified",
        }
    finally:
        try:
            if access is not None:
                manager.DeleteResultAccess(access)
        finally:
            try:
                if params is not None:
                    manager.DeleteResultParameters(params)
            finally:
                if owned:
                    manager.DeleteResult(result)
