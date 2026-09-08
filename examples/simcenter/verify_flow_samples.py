def run(executor):
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.results import acquire_result

    s = executor.session
    sim = s.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Isolated cavity SIM required")
    manager = s.ResultManager
    result, owned = acquire_result(s, sim)
    try:
        ids = list(range(1, result.AskNumNodes() + 1))
        coords = result.AskNodeCoordinates(ids)
        if len(coords) != len(ids):
            raise ValueError("Coordinate cardinality differs")
        points = [(p.X, p.Y, p.Z) for p in coords]
        lo = [min(p[j] for p in points) for j in range(3)]
        hi = [max(p[j] for p in points) for j in range(3)]
        if any(abs(a - b) > 1e-6 for a, b in zip(lo + hi, [1, 1, 1, 161, 21, 21], strict=True)):
            raise ValueError("Result coordinate frame/units not confirmed: " + str((lo, hi)))
        targets = [
            ("inlet_center", (1, 11, 11)),
            ("outlet_center", (161, 11, 11)),
            ("mid_center", (81, 11, 11)),
            ("mid_wall", (81, 1, 11)),
            ("mid_near_wall", (81, 2, 11)),
        ]
        rows = []
        for name, target in targets:
            ni = min(ids, key=lambda i: sum((points[i - 1][j] - target[j]) ** 2 for j in range(3)))
            incident = list(result.AskNodeElements(ni))
            if not incident:
                raise ValueError("Sample node has no element")
            rows.append(
                {
                    "name": name,
                    "requested_mm": target,
                    "actual_mm": points[ni - 1],
                    "node_index": ni,
                    "element_index": incident[0],
                    "incident_element_count": len(incident),
                    "values": {},
                }
            )
        types = result.GetLoadcases()[0].GetIterations()[0].GetResultTypes()
        for name, unit, comp in [
            ("Pressure - Element-Nodal", "PressurePascals", cae.Result.Component.Scalar),
            ("Total Pressure - Element-Nodal", "PressurePascals", cae.Result.Component.Scalar),
            ("Velocity - Element-Nodal", "MeterPerSecond", cae.Result.Component.Magnitude),
        ]:
            matches = [t for t in types if t.Name == name]
            if len(matches) != 1:
                raise ValueError("Field unavailable")
            params = manager.CreateResultParameters()
            access = None
            try:
                params.SetLoadcaseIteration(0, 0)
                params.SetGenericResultType(matches[0])
                params.SetResultComponent(comp)
                params.SetUnit(sim.UnitCollection.FindObject(unit))
                access = manager.CreateResultAccess(result, params)
                for row in rows:
                    row["values"][name] = {
                        "value": access.AskElementNodalResult(
                            row["element_index"], row["node_index"]
                        ),
                        "unit": unit,
                    }
            finally:
                if access:
                    manager.DeleteResultAccess(access)
                manager.DeleteResultParameters(params)
        return {
            "samples": rows,
            "bounds_mm": {"min": lo, "max": hi},
            "sampling": "nearest mesh node, first incident element; no averaging",
            "freshness": "not_verified",
        }
    finally:
        if owned:
            manager.DeleteResult(result)
