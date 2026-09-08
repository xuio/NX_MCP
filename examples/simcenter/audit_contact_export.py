"""Read-only contact setting audit of NX 2606 solver XML; not a solve acceptance."""

import hashlib
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def audit(root, mode, expected):
    rows = root.findall(".//ThermalCoupling")
    if len(rows) != 1:
        raise ValueError("Expected one explicit contact coupling")
    row = rows[0]

    def value(name):
        found = [p for p in row.findall("Property") if p.get("name") == name]
        if len(found) != 1:
            raise ValueError("Missing or ambiguous contact property " + name)
        return float(found[0].findtext("Value"))

    if value("Override Secondary Region") != 0 or value("Specify Region Side to Apply to") != 0:
        raise ValueError("Unexpected contact region mode")
    if (
        mode not in ("resistance", "conductance")
        or value("Type") != {"resistance": 1, "conductance": 0}[mode]
    ):
        raise ValueError("Inactive contact mode")
    if mode == "conductance" and value("Per Element") != 0:
        raise ValueError("Conductance must be total")
    units = root.find("Units")
    force = float(units.findtext("ForceConversionFactor"))
    length = float(units.findtext("LengthConversionFactor"))
    temperature = float(units.findtext("TemperatureConversionFactor"))
    # This observed NX deck uses seconds unchanged; do not generalize to other systems.
    if units.findtext("System") != "Millimeters" or (force, length, temperature) != (
        1000.0,
        1000.0,
        1.0,
    ):
        raise ValueError("Unverified solver unit system")
    raw = value("Total Resistance" if mode == "resistance" else "Total Conductance")
    actual = (
        raw * force * length / temperature
        if mode == "resistance"
        else raw * temperature / (force * length)
    )
    if not math.isfinite(actual) or not math.isclose(actual, expected, rel_tol=1e-7, abs_tol=1e-12):
        raise ValueError("Exported SI contact value mismatch")
    selections = row.findall("Selection")
    if [s.get("step") for s in selections] != ["1", "2"] or any(
        not s.findall("fa") for s in selections
    ):
        raise ValueError("Missing contact region selections")
    return {
        "mode": mode,
        "native_value": raw,
        "si_value": actual,
        "si_units": "K/W" if mode == "resistance" else "W/K",
        "force_factor": force,
        "length_factor": length,
        "temperature_factor": temperature,
        "region_face_counts": [len(s.findall("fa")) for s in selections],
        "selection_semantics": "Contact Selection step=1/2 labels the primary/secondary sets; not solution-step membership",
        "export_settings_verified": True,
        "numerical_acceptance": "not_established",
    }


if __name__ == "__main__":
    p = Path(sys.argv[1])
    raw = p.read_bytes()
    r = audit(ET.fromstring(raw), sys.argv[2], float(sys.argv[3]))
    r.update(path=str(p), sha256=hashlib.sha256(raw).hexdigest())
    print(json.dumps(r, indent=2))
