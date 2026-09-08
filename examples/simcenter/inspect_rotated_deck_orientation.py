"""Inspect all exported orientation records and mesh-group attributes."""


def run(executor):
    import xml.etree.ElementTree as ET

    path = executor.workspace.resolve(
        "ui-benchmarks/orthotropic-rotated-export-20260908-r1/rotated_ortho_export_r1-Conduction.xml"
    )
    root = ET.parse(path).getroot()
    selected = []
    for element in root.iter():
        text = element.tag + " " + " ".join(element.attrib.values())
        if any(k in text.lower() for k in ("orientation", "coordinate", "csys", "transform")):
            serialized = ET.tostring(element, encoding="unicode")
            selected.append(
                {
                    "tag": element.tag,
                    "attributes": element.attrib,
                    "xml": serialized[:8000],
                    "truncated": len(serialized) > 8000,
                }
            )
    return {
        "sections": [c.tag for c in root],
        "orientation_records": selected,
        "alignment_sections": {key: ET.tostring(root.find(key), encoding="unicode")[:16000] for key in ("Alignments", "ElementAssociatedDataList") if root.find(key) is not None},
        "element_group_attributes": [g.attrib for g in root.findall("./ElementList/Set")],
        "file_modified": False,
        "solver_launched": False,
    }
