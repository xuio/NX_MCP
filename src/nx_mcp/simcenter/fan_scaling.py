"""Bounded same-geometry fan-law estimates; no acoustic or motor-power model."""

import hashlib
import json
import math

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.fan_field import validate_manifest


def scale_curve(curve, name, rpm, density_kg_m3=None):
    source = validate_manifest(curve)
    limits = source.get("scaling_rpm_range")
    if (
        type(rpm) not in (int, float)
        or not math.isfinite(rpm)
        or limits is None
        or not limits[0] <= rpm <= limits[1]
    ):
        raise NXToolError("NX_INVALID_ARGUMENT", "RPM must lie within the explicit fan-law range")
    density = source["reference_density_kg_m3"] if density_kg_m3 is None else density_kg_m3
    if type(density) not in (int, float) or not math.isfinite(density) or density <= 0:
        raise NXToolError("NX_INVALID_ARGUMENT", "Density must be finite and positive")
    checksum = hashlib.sha256(
        json.dumps(source, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    ratio = rpm / source["rpm"]
    result = {
        **source,
        "name": name,
        "rpm": rpm,
        "reference_density_kg_m3": density,
        "points": [
            {
                "flow_m3_s": p["flow_m3_s"] * ratio,
                "pressure_Pa": p["pressure_Pa"]
                * ratio**2
                * density
                / source["reference_density_kg_m3"],
            }
            for p in source["points"]
        ],
        "provenance": {
            "kind": "assumed",
            "source": f"Fan-law estimate Q~RPM, pressure~density*RPM^2; same fan geometry. "
            f"Source SHA256={checksum}; RPM={source['rpm']}; density={source['reference_density_kg_m3']} kg/m3. "
            f"Original {source['provenance']['kind']}: {source['provenance']['source']}",
        },
    }
    return validate_manifest(result)
