"""Standard-library-only native fan log inspection for the NX Python runtime."""

import math
import re


def parse_native_fan_summary(text: str, *, native_pressure_unit: str) -> dict:
    """Parse the observed 2606 steady log layout, retaining precision limitations.

    Pressure units must be verified by the caller against this run's native output.
    Multiple summaries/enclosures are rejected instead of silently selecting one.
    Display names in logs are not stable object references.
    """
    import re

    if native_pressure_unit not in ("Pa", "mN/mm^2"):
        raise ValueError("Specify verified native pressure units: Pa or mN/mm^2")
    if len(text) > 16 * 1024 * 1024:
        raise ValueError("Log exceeds bounded summary parser limit")
    marker = "Fan Curve Operating Point Summary"
    flow_marker = "Volume/Mass Flow Summary"
    if text.count(marker) != 1 or text.count(flow_marker) != 1:
        raise ValueError("Require one fan operating-point and one boundary flow summary")
    section = text.split(marker, 1)[1].split("Total parallel flow solver time", 1)[0]
    number = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?"
    fan_pattern = re.compile(
        rf"^\s*\|\s*([^|]+?)\s*\|\s*({number})\s*\|\s*({number})\s*\|\s*({number})\s*\|\s*$",
        re.MULTILINE,
    )
    fans = []
    names = set()
    scale = 1.0 if native_pressure_unit == "Pa" else 1000.0
    for match in fan_pattern.finditer(section):
        name, loss, pressure, mass = match.groups()
        name = name.strip()
        if name in names:
            raise ValueError("Duplicate fan display name is ambiguous")
        names.add(name)
        fans.append(
            {
                "name": name,
                "loss_coefficient": float(loss),
                "pressure_rise_Pa": float(pressure) * scale,
                "mass_flow_kg_s": float(mass),
                "pressure_convention": "unverified",
            }
        )
    flow_section = text.split(flow_marker, 1)[1].split("Solver Convergence", 1)[0]
    flow_pattern = re.compile(
        rf"^\s*(\S[^\r\n]*?)\s+({number})\s+mm\^3/s\s+({number})\s+kg/s\s*$", re.MULTILINE
    )
    boundaries = {}
    for match in flow_pattern.finditer(flow_section):
        name, volume, mass = match.groups()
        name = name.strip()
        if name in boundaries:
            raise ValueError("Duplicate boundary display name is ambiguous")
        boundaries[name] = {
            "name": name,
            "volume_flow_m3_s": float(volume) * 1e-9,
            "mass_flow_kg_s": float(mass),
            "positive_direction": "into_domain",
        }
    if not fans or not boundaries:
        raise ValueError("Native fan/flow summary layout is unsupported or incomplete")
    for fan in fans:
        if fan["name"] not in boundaries:
            raise ValueError("Fan row has no uniquely matching boundary flow row")
        fan["volume_flow_m3_s"] = boundaries[fan["name"]]["volume_flow_m3_s"]
    if any(
        not math.isfinite(v)
        for row in [*fans, *boundaries.values()]
        for v in row.values()
        if isinstance(v, float)
    ):
        raise ValueError("Non-finite native summary value")
    return {
        "fans": fans,
        "boundaries": list(boundaries.values()),
        "native_pressure_unit": native_pressure_unit,
        "precision": "rounded_native_log",
        "identity": "display_names_only",
        "engineering_accepted": False,
    }


def inspect_fan_operating_points(text):
    """Report only points with an unambiguous native pressure-unit header."""
    if "Fan Curve Operating Point Summary" not in text:
        return {"state": "not_present", "fans": []}
    number = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?"
    units = re.findall(
        r"^\s*Fluid Pressure\s+" + number + r"\s+" + number + r"\s+" + number + r"\s+(\S+)\s*$",
        text,
        re.MULTILINE,
    )
    if units != ["mN/mm^2"]:
        return {
            "state": "units_not_verified",
            "fans": [],
            "reason": "Require one observed NX2606 Fluid Pressure summary in mN/mm^2; other layouts remain unsupported",
        }
    try:
        summary = parse_native_fan_summary(text, native_pressure_unit="mN/mm^2")
    except ValueError as error:
        return {"state": "summary_not_verified", "fans": [], "reason": str(error)}
    return {
        "state": "reported",
        "fans": summary["fans"],
        "native_pressure_unit": "mN/mm^2",
        "unit_basis": "observed NX2606 fluid pressure summary header",
        "precision": summary["precision"],
        "identity": summary["identity"],
        "engineering_accepted": False,
        "scope": "Native rounded operating-point rows; static/total convention and exact model/job binding require separate audits",
    }
