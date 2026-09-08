"""Read-only audit of the retained NX 2606 manual-K export; no solver execution.

Usage: python examples/simcenter/audit_head_loss_export.py export.xml
"""

import hashlib
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def audit(root, opening_name="Duct Opening", coefficient=2.0):
    def one(items, description):
        if len(items) != 1:
            raise ValueError(f"Expected exactly one {description}; got {len(items)}")
        return items[0]

    def value(element, name):
        prop = one([p for p in element.findall("Property") if p.get("name") == name], name)
        return one(prop.findall("Value"), name + " value").text.strip()

    opening = one(
        [
            b
            for b in root.findall(".//FlowBc")
            if b.get("uname") == opening_name and b.get("type") == "Opening"
        ],
        "opening",
    )
    uid = value(opening, "Head Loss")
    table = one(
        [t for t in root.findall("./HeadLossList/HeadLoss") if t.get("uid") == uid],
        "referenced head-loss table",
    )
    selectors = {key: int(value(table, key)) for key in ("Type", "Proportional to")}
    if selectors != {"Type": 0, "Proportional to": 0}:
        raise ValueError("Export does not activate manual dynamic-pressure K")
    actual = float(value(table, "Head Loss Coefficient"))
    if not math.isfinite(actual) or not math.isclose(
        actual, coefficient, rel_tol=1e-7, abs_tol=1e-12
    ):
        raise ValueError("Exported coefficient differs from requested K")
    selections = opening.findall("Selection")
    steps = {s.get("stepid") for s in root.findall("./SolutionStepList/SolutionStep")}
    if not selections or any(s.get("step") not in steps or not s.findall("fa") for s in selections):
        raise ValueError("Opening lacks face selections in a declared solution step")
    return {
        "scope": "NX 2606 exported manual dynamic-pressure opening coefficient",
        "solution": root.attrib,
        "opening": opening_name,
        "table_uid": uid,
        "table_name": table.get("uname"),
        "selectors": selectors,
        "coefficient": actual,
        "units": "dimensionless",
        "selections": [
            {"step": s.get("step"), "face_count": len(s.findall("fa"))} for s in selections
        ],
        "export_settings_verified": True,
        "numerical_acceptance": "not_tested_by_this_audit",
    }


if __name__ == "__main__":
    path = Path(sys.argv[1])
    data = path.read_bytes()
    result = audit(ET.fromstring(data))
    result.update(
        source_path=str(path),
        source_sha256=hashlib.sha256(data).hexdigest(),
        source_bytes=len(data),
    )
    print(json.dumps(result, indent=2))
