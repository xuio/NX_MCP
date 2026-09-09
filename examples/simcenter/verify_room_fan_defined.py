def run(executor):
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.results import acquire_result

    s = executor.session
    sim = s.Parts.BaseWork
    assert sim.FullPath.endswith(r"E-room-fan-half-run-20260909-r1\half_r1.sim")
    result, owned = acquire_result(s, sim)
    manager = s.ResultManager
    p = a = None
    try:
        (field,) = [
            f
            for f in result.GetLoadcases()[0].GetIterations()[0].GetResultTypes()
            if f.Name == "Temperature - Nodal"
        ]
        p = manager.CreateResultParameters()
        p.SetLoadcaseIteration(0, 0)
        p.SetGenericResultType(field)
        p.SetResultComponent(cae.Result.Component.Scalar)
        p.SetUnit(sim.UnitCollection.FindObject("Celsius"))
        a = manager.CreateResultAccess(result, p)
        n = result.AskNumNodes()
        indices = list(range(1, 101)) + list(range(n - 99, n + 1))
        flags = list(a.IsResultDefined(indices))
        assert len(flags) == len(indices)
        defined = [i for i, f in zip(indices, flags, strict=True) if f]
        values = list(a.AskNodalResult(defined)) if defined else []
        return {
            "node_count": n,
            "indices": indices,
            "defined": flags,
            "defined_value_count": len(values),
            "values": values,
            "api": "ResultAccess.IsResultDefined(int[])",
            "units": "degC",
        }
    finally:
        if a:
            manager.DeleteResultAccess(a)
        if p:
            manager.DeleteResultParameters(p)
        if owned:
            manager.DeleteResult(result)
