"""Read existing reference and refined decks; never export or solve."""


def run(executor):
    import hashlib
    import xml.etree.ElementTree as ET

    root = executor.workspace.resolve("ui-benchmarks")
    paths = {
        "reference": root
        / "D-independent-clone-export-20260908-r1/independent_export-Flow_benchmark.xml",
        "refined": root
        / "D-independent-refined-solve-20260908-r1/refined_flow_r1-Flow_benchmark.xml",
    }
    reports = {}
    for name, path in paths.items():
        if path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("Deck exceeds comparison size limit")
        raw = path.read_bytes()
        tree = ET.fromstring(raw)
        props = {}
        for prop in tree.iter("Property"):
            props.setdefault(prop.get("name"), []).append(ET.tostring(prop, encoding="unicode"))
        reports[name] = {
            "path": str(path),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "counts": {
                "elements": len(tree.findall("./ElementList/Set/E")),
                "nodes": len(tree.findall("./NodeList/N")),
            },
            "sections": {
                child.tag: hashlib.sha256(ET.tostring(child)).hexdigest() for child in tree
            },
            "properties": props,
        }
    a, b = reports["reference"], reports["refined"]
    differing_properties = sorted(
        k
        for k in set(a["properties"]) | set(b["properties"])
        if a["properties"].get(k) != b["properties"].get(k)
    )
    differing_sections = sorted(
        k
        for k in set(a["sections"]) | set(b["sections"])
        if a["sections"].get(k) != b["sections"].get(k)
    )
    return {
        "inputs": {
            key: {k: v for k, v in row.items() if k not in ("properties", "sections")}
            for key, row in reports.items()
        },
        "different_property_names": differing_properties,
        "different_sections": differing_sections,
        "fan_curve_identical": bool(a["properties"].get("Fan Curve"))
        and a["properties"].get("Fan Curve") == b["properties"].get("Fan Curve"),
        "solver_launched": False,
        "files_modified": False,
        "scope": "Exported property and section comparison; changing mesh sets require geometry-aware selection checks",
    }
