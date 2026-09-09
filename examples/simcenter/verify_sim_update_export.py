def run(executor):
    import hashlib
    import json
    import xml.etree.ElementTree as ET
    from pathlib import Path
    from types import SimpleNamespace

    from nx_mcp.simcenter.mesh_plan import mesh_counts

    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    receipt = json.loads((shared / "sim-update-export-public.json").read_text())
    assert receipt["completed"] and not receipt["export"]["solver_launched"]
    path = executor.workspace.resolve(receipt["export"]["input_path"])
    assert path.stat().st_size < 2 * 1024 * 1024
    raw = path.read_bytes()
    root = ET.fromstring(raw)
    sim = executor.session.Parts.BaseWork
    assert type(sim).__name__ == "SimPart" and "U-sim-update-export-20260909-r1" in sim.FullPath
    counts = {
        "elements": len(root.findall("./ElementList/Set/E")),
        "nodes": len(root.find("NodeList")),
    }
    fem = mesh_counts(sim.FemPart)
    occurrence = mesh_counts(SimpleNamespace(BaseFEModel=sim.Simulation.Femodel))
    assert counts == fem == occurrence == {"elements": 182, "nodes": 73}
    from nx_mcp.simcenter.boundary_geometry import inspect_rectangular_patch

    material = root.find("./MaterialList/Material")

    def value(node, name):
        rows = [p for p in node.findall("Property") if p.get("name") == name]
        assert len(rows) == 1
        return float(rows[0].findtext("Value"))

    assert root.findtext("./Units/System") == "Millimeters"
    assert value(material, "Thermal Conductivity") == 200000
    assert value(material, "Specific Heat") == 900000000
    assert value(material, "Mass Density Constant") == 0.0000027
    heat = root.find("./Loads/ThermalLoadList/ThermalLoad")
    temperature = root.find("./Constraints/TemperatureList/Temperature")
    assert (
        value(heat, "Heat Load") == 1000000
        and value(heat, "Per Element") == 0
        and value(heat, "Per Node") == 0
    )
    assert value(temperature, "Temperature") == 20
    elements = {
        int(e.text.split()[0]): list(map(int, e.text.split()[1:]))
        for e in root.findall("./ElementList/Set/E")
    }
    assigned = [int(e.text) for e in heat.findall("./Selection/el")]
    assert len(assigned) == len(set(assigned)) == 182 and set(assigned) == set(elements)
    xmlnodes = {
        int(n.text.split()[0]): list(map(float, n.text.split()[1:])) for n in root.find("NodeList")
    }
    labels = sim.FemPart.BaseFEModel.FeelementLabelMap
    polygons = []
    try:
        for face in temperature.findall("./Selection/fa"):
            label, index = map(int, face.text.split())
            element = labels.GetElement(label)
            assert len(elements[label]) == 4 and 1 <= index <= 4
            assert set(elements[label]) == {n.Label for n in element.GetNodes()}
            polygon = []
            for node in element.GetCornerNodesOnFace(index - 1):
                xyz = [node.Coordinates.X, node.Coordinates.Y, node.Coordinates.Z]
                assert all(abs(a - b) < 1e-7 for a, b in zip(xyz, xmlnodes[node.Label], strict=True))
                polygon.append({"label": node.Label, "xyz": xyz})
            polygons.append(polygon)
    finally:
        labels.Dispose()
    patch = inspect_rectangular_patch(
        polygons, plane_x_mm=10, minimum_yz_mm=[0, 0], maximum_yz_mm=[10, 10]
    )
    (shared / "sim-update-export.xml").write_bytes(raw)
    return {
        "passed": True,
        "export_counts": counts,
        "fem_counts": fem,
        "sim_counts": occurrence,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "input_path": str(path),
        "source_sim": sim.FullPath,
        "thermal_values_verified": {
            "conductivity_w_m_k": 200,
            "density_kg_m3": 2700,
            "heat_capacity_j_kg_k": 900,
            "total_heat_w": 1,
            "temperature_k": 293.15,
        },
        "heat_selected_elements": len(assigned),
        "temperature_patch": patch,
        "solver_launched": False,
        "numeric_acceptance": "not_established",
    }
