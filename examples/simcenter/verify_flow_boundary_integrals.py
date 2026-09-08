def run(executor):
    import math
    import xml.etree.ElementTree as ET
    from pathlib import Path

    import NXOpen.CAE as cae

    from nx_mcp.simcenter.results import acquire_result

    s = executor.session
    sim = s.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Isolated cavity SIM required")
    raw = (
        Path(sim.FullPath).parent / "benchmark_4ba7072a1d7a_analysis-Flow_benchmark.xml"
    ).read_bytes()
    xml = ET.fromstring(raw)
    result, owned = acquire_result(s, sim)
    manager = s.ResultManager
    try:
        ids = list(range(1, result.AskNumNodes() + 1))
        coords = result.AskNodeCoordinates(ids)
        points = {i: (p.X, p.Y, p.Z) for i, p in zip(ids, coords, strict=True)}
        if result.AskNumNodes() != len(xml.findall("./NodeList/N")):
            raise ValueError("Result/deck node count differs")
        surfaces = []
        for name, x in [("Duct Inlet", 1.0), ("Duct Opening", 161.0)]:
            bc = next(e for e in xml.iter("FlowBc") if e.get("uname") == name)
            facets = []
            seen = set()
            for face in bc.iter("fa"):
                label = int(face.text.split()[0])
                ei = result.AskElementIndex(label)
                nodes = list(result.AskElementNodes(ei))
                selected = [i for i in nodes if abs(points[i][0] - x) < 1e-6]
                if len(selected) != 3:
                    raise ValueError(
                        "Boundary element does not have three vertices on expected plane"
                    )
                key = tuple(sorted(selected))
                if key in seen:
                    raise ValueError("Duplicate boundary facet")
                seen.add(key)
                a, b, c = [points[i] for i in selected]
                u = [b[j] - a[j] for j in range(3)]
                v = [c[j] - a[j] for j in range(3)]
                cross = [
                    u[1] * v[2] - u[2] * v[1],
                    u[2] * v[0] - u[0] * v[2],
                    u[0] * v[1] - u[1] * v[0],
                ]
                area = 0.5 * math.sqrt(sum(t * t for t in cross))
                facets.append((ei, selected, area))
            area = sum(t[2] for t in facets)
            if abs(area - 400.0) > 1e-3:
                raise ValueError("Boundary area mismatch")
            surfaces.append({"name": name, "area_mm2": area, "facets": facets, "values": {}})
        types = result.GetLoadcases()[0].GetIterations()[0].GetResultTypes()
        for name, unit, comp in [
            ("Pressure - Element-Nodal", "PressurePascals", cae.Result.Component.Scalar),
            ("Total Pressure - Element-Nodal", "PressurePascals", cae.Result.Component.Scalar),
            ("Velocity - Element-Nodal", "MeterPerSecond", cae.Result.Component.X),
        ]:
            params = manager.CreateResultParameters()
            access = None
            try:
                params.SetLoadcaseIteration(0, 0)
                params.SetGenericResultType(next(t for t in types if t.Name == name))
                params.SetResultComponent(comp)
                params.SetUnit(sim.UnitCollection.FindObject(unit))
                access = manager.CreateResultAccess(result, params)
                for surface in surfaces:
                    integral = sum(
                        area * sum(access.AskElementNodalResult(ei, ni) for ni in nodes) / 3.0
                        for ei, nodes, area in surface["facets"]
                    )
                    surface["values"][name] = {
                        "area_mean": integral / surface["area_mm2"],
                        "unit": unit,
                    }
                    if name.startswith("Velocity"):
                        surface["recovered_volume_flow_m3_s_positive_x"] = integral * 1e-6
            finally:
                if access:
                    manager.DeleteResultAccess(access)
                manager.DeleteResultParameters(params)
        for surface in surfaces:
            surface["facet_count"] = len(surface.pop("facets"))
        return {
            "boundaries": surfaces,
            "method": "linear triangular integration of recovered element-nodal values",
            "conservation": "not_established_by_recovered_field_integrals",
            "freshness": "not_verified",
        }
    finally:
        if owned:
            manager.DeleteResult(result)
