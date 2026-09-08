"""Private, fixed NX .NET evaluator adapter. Opaque pointers never enter Python."""

import hashlib
import json
import math
import re
from pathlib import Path

from nx_mcp.runtime import NXToolError


def decode_result(values, count):
    values = list(values)
    if (
        len(values) == 4
        and values[0] == -1
        and all(type(v) in (int, float) and math.isfinite(v) and int(v) == v for v in values)
        and values[3] in (0, 1)
    ):
        raise NXToolError(
            "NX_EVALUATOR_CLEANUP_FAILED" if values[3] else "NX_EVALUATOR_OPERATION_FAILED",
            "Native evaluator operation failed; no geometry result accepted",
            nx_code=int(values[1]) or None,
            details={"cleanup_nx_code": int(values[2]) or None, "cleanup_failed": bool(values[3])},
        )
    if (
        len(values) != 15 + 3 * count
        or not all(type(v) in (int, float) and math.isfinite(v) for v in values)
        or values[0] != 1
        or values[1] not in (0, 1, 2)
        or values[2] != count
        or (values[1] == 2 and values[5] <= 0)
    ):
        raise NXToolError("NX_EVALUATOR_PROTOCOL", "Invalid private evaluator result")
    return {
        "kind": {0: "other", 1: "line", 2: "arc"}[values[1]],
        "limits": values[3:5],
        "radius": values[5],
        "center": values[6:9],
        "x_axis": values[9:12],
        "y_axis": values[12:15],
        "points": [values[i : i + 3] for i in range(15, len(values), 3)],
    }


class EvaluatorBridge:
    def __init__(self, session):
        self.session = session
        directory = Path(__file__).with_name("native")
        try:
            manifest = json.loads((directory / "evaluator-helper.json").read_text())
            name = manifest["file"]
            if not re.fullmatch(r"EvaluatorHelper-[0-9a-f]{16}\.dll", name):
                raise ValueError("Invalid private helper filename")
            path = directory / name
            if (
                manifest["protocol"] != 1
                or hashlib.sha256(path.read_bytes()).hexdigest() != manifest["binary_sha256"]
                or hashlib.sha256((directory / "EvaluatorHelper.cs").read_bytes()).hexdigest()
                != manifest["source_sha256"]
            ):
                raise ValueError("Helper source/binary manifest mismatch")
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise NXToolError(
                "NX_API_UNAVAILABLE",
                "The private NX evaluator helper is not installed or does not match its build manifest",
                details={"mutation_outcome": "not_started"},
            ) from error
        self.path = str(path)

    def inspect(self, source, count):
        if type(count) is not int or not 2 <= count <= 200:
            raise NXToolError("NX_INVALID_ARGUMENT", "Evaluator samples must be 2..200")
        try:
            result = self.session.Execute(
                self.path, "EvaluatorHelper", "InspectChecked", [source, count, False]
            )
        except Exception as error:
            raise NXToolError(
                "NX_EVALUATOR_LOAD_FAILED",
                "Private managed evaluator invocation failed; inspect NX loader/signing prerequisites",
                nx_code=getattr(error, "ErrorCode", None),
            ) from error
        return decode_result(result, count)
