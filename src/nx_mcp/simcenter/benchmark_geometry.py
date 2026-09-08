"""Pure preflight for isolated multi-block benchmark geometry."""

import math

from nx_mcp.runtime import NXToolError


def validate_block_origins(value, dimensions):
    def reject(message):
        raise NXToolError(
            "NX_INVALID_ARGUMENT", message, details={"mutation_outcome": "not_started"}
        )

    if value is None:
        return [(0.0, 0.0, 0.0)]
    if not isinstance(value, list) or not 1 <= len(value) <= 16:
        reject("block_origins_mm must contain 1..16 XYZ origins")
    origins = []
    for origin in value:
        if (
            not isinstance(origin, (tuple, list))
            or len(origin) != 3
            or any(
                type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 10000
                for v in origin
            )
        ):
            reject(
                "Each block origin must contain three finite millimeter coordinates within +/-10000"
            )
        xyz = tuple(float(v) for v in origin)
        if any(
            all(abs(a - b) < length for a, b, length in zip(xyz, other, dimensions, strict=True))
            for other in origins
        ):
            reject("Benchmark blocks may touch but must not overlap")
        origins.append(xyz)
    return origins
