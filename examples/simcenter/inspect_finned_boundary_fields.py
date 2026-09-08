def triangulate_boundary(selected, points):
    """Triangulate an X-normal planar convex boundary face for recovered-field integration."""
    import math

    if len(selected) not in (3, 4) or len(set(selected)) != len(selected):
        raise ValueError("Expected three or four distinct vertices")
    if max(points[i][0] for i in selected) - min(points[i][0] for i in selected) > 1e-6:
        raise ValueError("Expected an X-normal planar face")
    selected = list(selected)
    result = []
    if len(selected) == 4:
        cy = sum(points[i][1] for i in selected) / 4
        cz = sum(points[i][2] for i in selected) / 4
        selected.sort(key=lambda i: math.atan2(points[i][2] - cz, points[i][1] - cy))
    triangles = (
        [selected]
        if len(selected) == 3
        else [selected[:3], [selected[0], selected[2], selected[3]]]
    )
    for nodes in triangles:
        a, b, c = [points[i] for i in nodes]
        u = [b[j] - a[j] for j in range(3)]
        v = [c[j] - a[j] for j in range(3)]
        cross = [
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        ]
        area = 0.5 * math.sqrt(sum(t * t for t in cross))
        if area <= 0:
            raise ValueError("Degenerate boundary triangle")
        result.append((nodes, area))
    return result


def run(executor):
    import xml.etree.ElementTree as ET
    from pathlib import Path

    import NXOpen.CAE as cae

    from nx_mcp.simcenter.results import acquire_result

    s = executor.session
    sim = s.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or not any(
        x in sim.FullPath
        for x in (
            "E-finned-tight-",
            "E-finned-refined-run-",
            "E-finned-fine-run-",
            "E-finned-layer_fine-run-",
            "E-finned-layer-extended-",
        )
    ):
        raise ValueError("Isolated cavity SIM required")
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    decks = list(Path(sim.FullPath).parent.glob("*.xml"))
    if len(decks) != 1:
        raise ValueError("Expected one result input deck")
    raw = decks[0].read_bytes()
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
        for name, x in [("Coupled Inlet", 0.0), ("Coupled Opening", 20.0)]:
            bc = next(e for e in xml.iter("FlowBc") if e.get("uname") == name)
            facets = []
            seen = set()
            for face in bc.iter("fa"):
                label = int(face.text.split()[0])
                ei = result.AskElementIndex(label)
                nodes = list(result.AskElementNodes(ei))
                selected = [i for i in nodes if abs(points[i][0] - x) < 1e-6]
                if len(selected) not in (3, 4):
                    raise ValueError(
                        "Boundary element does not have a triangular or quadrilateral face on the expected plane"
                    )
                key = tuple(sorted(selected))
                if key in seen:
                    raise ValueError("Duplicate boundary facet")
                seen.add(key)
                facets.extend(
                    (ei, nodes, area) for nodes, area in triangulate_boundary(selected, points)
                )
            area = sum(t[2] for t in facets)
            if abs(area - 72.0) > 1e-3:
                raise ValueError("Boundary area mismatch")
            surfaces.append({"name": name, "area_mm2": area, "facets": facets, "values": {}})
        types = result.GetLoadcases()[0].GetIterations()[0].GetResultTypes()
        for name, unit, comp in [
            ("Pressure - Element-Nodal", "PressurePascals", cae.Result.Component.Scalar),
            ("Total Pressure - Element-Nodal", "PressurePascals", cae.Result.Component.Scalar),
            ("Velocity - Element-Nodal", "MeterPerSecond", cae.Result.Component.X),
            ("Temperature - Element-Nodal", "Celsius", cae.Result.Component.Scalar),
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
            "document": sim.FullPath,
            "input_sha256": __import__("hashlib").sha256(raw).hexdigest(),
            "static_pressure_drop_Pa": surfaces[0]["values"]["Pressure - Element-Nodal"][
                "area_mean"
            ]
            - surfaces[1]["values"]["Pressure - Element-Nodal"]["area_mean"],
            "boundaries": surfaces,
            "method": "piecewise linear triangular integration of recovered element-nodal values; planar quads split geometrically",
            "conservation": "not_established_by_recovered_field_integrals",
            "freshness": "not_verified",
        }
    finally:
        if owned:
            manager.DeleteResult(result)
