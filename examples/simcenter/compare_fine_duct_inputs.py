"""Audit the two saved benchmark decks; does not invoke NX or any solver."""

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(r"D:\CAD\SIMCENTER_MCP_WORKSPACE\ui-benchmarks")
PATHS = {
    "K0": ROOT / "D-fine-k0-solve-20260908-r1/fine_k0_solve_r1-Flow_benchmark.xml",
    "K2": ROOT / "F-auto-observer-20260908-r1/auto_flow_r1-Flow_benchmark.xml",
}


def inspect(path):
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Input exceeds benchmark audit size limit")
    raw = path.read_bytes()
    root = ET.fromstring(raw)
    hashes = {}
    for tag in ("NodeList", "ElementList"):
        items = root.findall(tag)
        assert len(items) == 1, tag
        hashes[tag] = hashlib.sha256(ET.tostring(items[0])).hexdigest()
    properties = {}
    for prop in root.iter("Property"):
        name = prop.get("name")
        properties.setdefault(name, []).append(ET.tostring(prop, encoding="unicode"))
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "mesh_hashes": hashes,
        "properties": properties,
    }


if __name__ == "__main__":
    rows = {key: inspect(path) for key, path in PATHS.items()}
    a, b = rows["K0"], rows["K2"]
    keys = sorted(set(a["properties"]) | set(b["properties"]))
    differences = {
        key: {"K0": a["properties"].get(key), "K2": b["properties"].get(key)}
        for key in keys
        if a["properties"].get(key) != b["properties"].get(key)
    }
    result = {
        "inputs": {
            key: {k: v for k, v in row.items() if k != "properties"} for key, row in rows.items()
        },
        "mesh_xml_identical": a["mesh_hashes"] == b["mesh_hashes"],
        "different_property_names": list(differences),
        "property_differences": differences,
        "fan_curve_identical": a["properties"].get("Fan Curve") == b["properties"].get("Fan Curve")
        and bool(a["properties"].get("Fan Curve")),
        "scope": "Mesh XML, fan curve and property comparison; not numerical acceptance",
    }
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\fine-duct-input-comparison.json").write_text(
        json.dumps(result, indent=2)
    )
    print(
        json.dumps({k: v for k, v in result.items() if k not in ("inputs", "property_differences")})
    )
