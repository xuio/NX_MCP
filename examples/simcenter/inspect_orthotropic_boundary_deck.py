"""Read exact exported orthotropic benchmark settings without mutation."""


def run(executor):
    import xml.etree.ElementTree as ET

    path = executor.workspace.resolve(
        "ui-benchmarks/orthotropic-export-20260908-r1/orthotropic_export_r1-Conduction.xml"
    )
    root = ET.parse(path).getroot()
    nodes = [list(map(float, n.text.split()[1:])) for n in root.findall("./NodeList/N")]
    return {
        "path": str(path),
        "root_attributes": root.attrib,
        "bounds": {
            "minimum": [min(n[i] for n in nodes) for i in range(3)],
            "maximum": [max(n[i] for n in nodes) for i in range(3)],
        },
        "sections": {
            c.tag: ET.tostring(c, encoding="unicode")
            for c in root
            if c.tag not in ("NodeList", "ElementList", "MaterialList", "PhysicalPropertyTableList")
        },
        "file_modified": False,
        "solver_launched": False,
    }
