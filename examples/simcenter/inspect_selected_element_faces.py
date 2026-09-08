"""Inspect installed native face-node binding against selected exported faces."""


def run(executor):
    import xml.etree.ElementTree as ET

    root = executor.workspace.resolve("ui-benchmarks")
    path = root / "D-independent-refined-solve-20260908-r1/refined_flow_r1-Flow_benchmark.xml"
    tree = ET.fromstring(path.read_bytes())
    sim = executor.session.Parts.BaseWork
    assert (
        executor.workspace.resolve(sim.FemPart.FullPath)
        == root / "D-independent-clone-native-20260908-r1/independent_mesh.fem"
    )
    fem = sim.FemPart
    kinds = {
        int(e.text.split()[0]): group.attrib for group in tree.find("ElementList") for e in group
    }
    label_map = fem.BaseFEModel.FeelementLabelMap
    rows = []
    seen = set()
    try:
        for bc in tree.findall("./SimulationObjects/FlowBcList/FlowBc"):
            for face in bc.findall("./Selection/fa"):
                label, index = map(int, face.text.split())
                key = (bc.get("uname"), str(kinds[label]), index)
                if key in seen:
                    continue
                seen.add(key)
                element = label_map.GetElement(label)
                row = {
                    "boundary": bc.get("uname"),
                    "element": label,
                    "export_face_index": index,
                    "native_face_index": index - 1,
                    "element_set": kinds[label],
                }
                try:
                    nodes = element.GetCornerNodesOnFace(index - 1)
                    row["nodes"] = [
                        {
                            "type": type(n).__name__,
                            "label": n.Label,
                            "xyz": [n.Coordinates.X, n.Coordinates.Y, n.Coordinates.Z],
                        }
                        for n in nodes
                    ]
                except Exception as error:
                    row["error"] = {
                        "type": type(error).__name__,
                        "message": str(error),
                        "nx_code": getattr(error, "ErrorCode", None),
                    }
                rows.append(row)
                if len(rows) > 16:
                    raise ValueError("Unexpected face-family count")
    finally:
        label_map.Dispose()
    return {"rows": rows, "files_modified": False}
