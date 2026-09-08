"""Verify every selected duct face using native nodes and geometric patch checks."""


def run(executor):
    import hashlib
    import runpy
    import xml.etree.ElementTree as ET
    from pathlib import Path

    check = runpy.run_path(str(Path(__file__).with_name("boundary_geometry.py")))[
        "inspect_rectangular_patch"
    ]
    root = executor.workspace.resolve("ui-benchmarks")
    cases = [
        (
            "reference",
            "D-independent-clone-export-20260908-r1/independent_export-Flow_benchmark.xml",
            "D-cavity-documents-20260908-r2/benchmark_4ba7072a1d7a_mesh.fem",
        ),
        (
            "refined",
            "D-independent-refined-solve-20260908-r1/refined_flow_r1-Flow_benchmark.xml",
            "D-independent-clone-native-20260908-r1/independent_mesh.fem",
        ),
    ]
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    results = []
    for case, deck_name, fem_name in cases:
        path, fem_path = root / deck_name, root / fem_name
        fems = [
            p
            for p in executor.session.Parts
            if p.FullPath and executor.workspace.resolve(p.FullPath) == fem_path
        ]
        if len(fems) != 1 or str(fems[0].PartUnits) != "1":
            raise ValueError("Require the exact loaded millimeter benchmark FEM")
        fem = fems[0]
        digest = hashlib.sha256(fem_path.read_bytes()).hexdigest()
        raw = path.read_bytes()
        tree = ET.fromstring(raw)
        element_rows = {
            int(e.text.split()[0]): (group.get("elementType"), [int(v) for v in e.text.split()[1:]])
            for group in tree.find("ElementList")
            for e in group
        }
        xml_nodes = {}
        for row in tree.find("NodeList"):
            fields = row.text.split()
            xml_nodes[int(fields[0])] = [float(v) for v in fields[1:]]
        labels = fem.BaseFEModel.FeelementLabelMap
        try:
            if labels.NumElements != len(element_rows):
                raise ValueError("Native FEM and exported element counts differ")
            bcs = tree.findall("./SimulationObjects/FlowBcList/FlowBc")
            if sorted(b.get("uname") for b in bcs) != ["Duct Inlet", "Duct Opening"]:
                raise ValueError("Unexpected benchmark boundary inventory")
            patches = []
            for bc in bcs:
                name = bc.get("uname")
                faces = bc.findall("./Selection/fa")
                if not 1 <= len(faces) <= 10000:
                    raise ValueError("Unexpected boundary face count")
                polygons = []
                for face in faces:
                    label, exported_index = map(int, face.text.split())
                    kind, expected_nodes = element_rows[label]
                    max_faces = {"TET4 Fluid": 4, "WEDGE6 Fluid": 5}.get(kind)
                    if max_faces is None or not 1 <= exported_index <= max_faces:
                        raise ValueError("Untested element type or exported face index")
                    element = labels.GetElement(label)
                    if {n.Label for n in element.GetNodes()} != set(expected_nodes):
                        raise ValueError("Native/exported element connectivity differs")
                    nodes = element.GetCornerNodesOnFace(exported_index - 1)
                    polygon = []
                    for node in nodes:
                        xyz = [node.Coordinates.X, node.Coordinates.Y, node.Coordinates.Z]
                        if any(
                            abs(a - b) > 1e-7
                            for a, b in zip(xyz, xml_nodes[node.Label], strict=True)
                        ):
                            raise ValueError("Native/exported selected node coordinates differ")
                        polygon.append({"label": node.Label, "xyz": xyz})
                    polygons.append(polygon)
                patches.append(
                    {
                        "boundary": name,
                        **check(
                            polygons,
                            plane_x_mm=1 if name == "Duct Inlet" else 161,
                            minimum_yz_mm=[1, 1],
                            maximum_yz_mm=[21, 21],
                        ),
                    }
                )
        finally:
            labels.Dispose()
        assert hashlib.sha256(fem_path.read_bytes()).hexdigest() == digest
        results.append(
            {
                "case": case,
                "input_sha256": hashlib.sha256(raw).hexdigest(),
                "fem_path": str(fem_path),
                "fem_file_preserved": True,
                "patches": patches,
            }
        )
    assert flags == {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    return {
        "cases": results,
        "all_selected_face_connectivity_and_coordinates_matched": True,
        "existing_flags_preserved": True,
        "solver_launched": False,
        "frame": "standalone FEM part-absolute",
        "units": "mm",
        "index_mapping": "Observed NX2606 TET4/WEDGE6 export face index minus one for native GetCornerNodesOnFace",
    }
