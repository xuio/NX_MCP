"""Audit one generic benchmark material after native XML-to-solver translation."""

import math
import re


def inspect_material(properties, controls, *, expected_values=None):
    """Observed 2606 text format only; reject other units or nonconstant data."""
    for key, expected in {
        "LENGTH_CONVERSION_FACTOR": 1000.0,
        "FORCE_CONVERSION_FACTOR": 1000.0,
        "TIME_CONVERSION_FACTOR": 1.0,
        "TEMPERATURE_CONVERSION_FACTOR": 1.0,
    }.items():
        found = re.findall(r"^" + key + r"\s*=\s*([+\-\d.eE]+)\s*$", controls, re.M)
        if len(found) != 1 or float(found[0]) != expected:
            raise ValueError("Unverified solver units: " + key)
    materials = re.findall(r"^(.+?)\s+(liquid|gas)\s*$", properties, re.M)
    if len(materials) != 1 or materials[0][1] != "liquid":
        raise ValueError("Expected one constant-liquid benchmark material")
    expected = {
        "DENSITY": (1.2, 1e9, "kg/m3"),
        "SPECIFIC_HEAT_P": (1005.0, 1e-6, "J/(kg K)"),
        "DYNAMIC_VISCOSITY": (1.81e-5, 1e3, "Pa s"),
        "CONDUCTIVITY": (0.0257, 1e-3, "W/(m K)"),
    }
    if expected_values is not None:
        if set(expected_values) != set(expected) or any(
            type(v) not in (int, float) or not math.isfinite(v) or v <= 0
            for v in expected_values.values()
        ):
            raise ValueError("Supply all four positive finite expected SI material properties")
        expected = {
            key: (expected_values[key], scale, units) for key, (_, scale, units) in expected.items()
        }
    rows = {}
    for key, (intended, scale, units) in expected.items():
        matches = re.findall(r"^" + key + r"\s+(\d+)\s*\r?\n\s*([+\-\d.eE]+)", properties, re.M)
        if len(matches) != 1 or matches[0][0] != "0":
            raise ValueError("Missing, duplicate or nonconstant property: " + key)
        actual = float(matches[0][1]) * scale
        if not math.isfinite(actual) or actual <= 0:
            raise ValueError("Invalid positive fluid property: " + key)
        rows[key] = {
            "intended": intended,
            "translated": actual,
            "units": units,
            "relative_error": abs(actual - intended) / intended,
            "matches_relative_1e_6": math.isclose(actual, intended, rel_tol=1e-6, abs_tol=0),
        }
    return {
        "material": materials[0][0].strip(),
        "properties": rows,
        "all_properties_match": all(row["matches_relative_1e_6"] for row in rows.values()),
        "scope": "one constant liquid in the generic finned benchmark; not solve or physical acceptance",
    }


def inspect_density_card(cards, *, material_name="Generic air"):
    """Read the documented TMG MAT/RHO card in the observed benchmark units."""
    unit_rows = re.findall(r"^PARAM UNITS (.+)$", cards, re.M)
    if len(unit_rows) != 1:
        raise ValueError("Expected one TMG unit definition")
    if [float(v) for v in unit_rows[0].split()] != [5, 1000, 1000, 1, -273.15, 1]:
        raise ValueError("Unverified TMG units")
    names = re.findall(r'^MAT (\d+) NAME "' + re.escape(material_name) + r'"\s*$', cards, re.M)
    if len(names) != 1:
        raise ValueError("Expected one named material")
    label = names[0]
    phase = re.findall(r"^MAT " + label + r" PHASE (\S+)\s*$", cards, re.M)
    density = re.findall(r"^MAT " + label + r" RHO\s+(\S+)\s*$", cards, re.M)
    if phase != ["LIQUID"] or len(density) != 1:
        raise ValueError("Expected one liquid density card")
    try:
        rho = float(density[0]) * 1e9
    except ValueError as error:
        raise ValueError("Unsupported field/table density card") from error
    if not math.isfinite(rho) or rho <= 0:
        raise ValueError("Invalid material density")
    return {
        "material": material_name,
        "label": int(label),
        "density": rho,
        "units": "kg/m3",
        "phase": "LIQUID",
        "scope": "TMG input card only; not solver acceptance",
    }


if __name__ == "__main__":
    import hashlib
    import json
    import sys
    import zipfile
    from pathlib import Path

    path = Path(sys.argv[1])
    with zipfile.ZipFile(path) as archive:
        for name in ("flow.prp", "flow.prm", "INPF"):
            if archive.getinfo(name).file_size > 1024 * 1024:
                raise ValueError("Material/control text exceeds bounded read limit")
        report = inspect_material(
            archive.read("flow.prp").decode(), archive.read("flow.prm").decode()
        )
        report["tmg_density_card"] = inspect_density_card(archive.read("INPF").decode())
    report["package_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["all_properties_match"] else 1)
