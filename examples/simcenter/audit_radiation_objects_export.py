"""Audit retained enclosure/emissivity native export; no view-factor acceptance implied."""

import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path


def audit(raw):
    root = ET.fromstring(raw)
    if root.get("class") != "Thermal" or root.get("version") != "Simcenter 3D 2606":
        raise ValueError("Unverified solver/version")
    results = []
    selections = []
    for tag, name, expected in [
        (
            "Radiation",
            "MCP_ENCLOSURE",
            {"Calculation Method": 1, "Include Radiative Environment": 1},
        ),
        (
            "OverrideSetEmissivity",
            "MCP_EMISSIVITY",
            {"Emissivity": 0.8, "Apply Override Set to": 0},
        ),
    ]:
        matches = [r for r in root.findall(".//" + tag) if r.get("uname") == name]
        if len(matches) != 1:
            raise ValueError("Missing/ambiguous radiation object")
        row = matches[0]
        actual = {}
        for key, value in expected.items():
            props = [p for p in row.findall("Property") if p.get("name") == key]
            if len(props) != 1:
                raise ValueError("Missing/ambiguous active property")
            actual[key] = float(props[0].findtext("Value"))
            if not math.isclose(actual[key], value, rel_tol=1e-7, abs_tol=1e-12):
                raise ValueError("Active radiation setting mismatch: " + key)
        sets = row.findall("Selection")
        if len(sets) != 1 or sets[0].get("step") != "1":
            raise ValueError("Unexpected exported selection")
        faces = {tuple(map(int, e.text.split())) for e in sets[0].findall("fa")}
        if len(faces) != 84 or any(not 1 <= e <= 100 or not 1 <= f <= 4 for e, f in faces):
            raise ValueError("Expected 84 tetrahedral faces in the 100-element fixture")
        selections.append(faces)
        results.append({"name": name, "active_values": actual, "finite_element_faces": len(faces)})
    if selections[0] != selections[1]:
        raise ValueError("Enclosure and emissivity target different surfaces")
    return {
        "passed": True,
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "objects": results,
        "scope": "NX 2606 Thermal deterministic enclosure with environment, constant both-side emissivity and matching FE regions",
        "inactive_properties": "Monte Carlo, GPU, hemicube and other inactive controls excluded from active-setting comparison",
        "numerical_acceptance": "not_performed; no view-factor, cavity-closure, temperature or heat-balance result",
    }


if __name__ == "__main__":
    path = Path(__file__).parents[2] / "tests/simcenter/evidence/radiation-objects.xml"
    print(json.dumps(audit(path.read_bytes()), indent=2))
