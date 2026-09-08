"""Read observed TMG thermal summaries without inferring conservation acceptance."""

import math
import re

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?"
_LABELS = {
    "Heat flow into sinks": "heat_flow_into_sinks",
    "Heat flow from non-fluid sinks": "heat_flow_from_nonfluid_sinks",
    "Heat load into elements": "heat_load_into_elements",
    "Heat load into sinks": "heat_load_into_sinks",
    "Heat flow from fluid sinks": "heat_flow_from_fluid_sinks",
    "Deviation from heat balance": "reported_deviation",
}


def inspect_thermal_balances(text, *, power_unit):
    """Return every complete/partial summary with caller-supplied native units.

    No inferred time association, SI conversion, global/local deviation meaning,
    or convergence pass. Keep repeated transient summaries separate.
    """
    if power_unit not in ("W", "mN-mm/s"):
        raise ValueError("Supply an explicitly verified native power unit: W or mN-mm/s")
    if len(text.encode("utf-8")) > 8 * 1024 * 1024:
        raise ValueError("Thermal log exceeds the 8 MiB inspection budget")
    records = []
    current = None
    for line in text.splitlines():
        if "Summary for thermal elements" in line:
            current = {"ordinal": len(records), "values": {}, "issues": []}
            records.append(current)
            continue
        if current is None:
            continue
        for label, key in _LABELS.items():
            if not line.strip().startswith(label):
                continue
            match = re.fullmatch(r"\s*" + re.escape(label) + r"\s*=\s*(" + _NUMBER + r")\s*", line)
            if not match:
                current["issues"].append({"field": key, "reason": "unrecognized_numeric_value"})
                continue
            number = float(match[1].replace("D", "E").replace("d", "e"))
            if not math.isfinite(number):
                current["issues"].append({"field": key, "reason": "nonfinite_value"})
            elif key in current["values"]:
                current["issues"].append({"field": key, "reason": "duplicate_field"})
            else:
                current["values"][key] = number
    for row in records:
        row["missing_fields"] = sorted(set(_LABELS.values()) - row["values"].keys())
        row["state"] = (
            "complete" if not row["issues"] and not row["missing_fields"] else "incomplete"
        )
    return {
        "summaries": records,
        "power_unit": power_unit,
        "unit_source": "caller_verified",
        "time_association": "not_established",
        "conservation_accepted": False,
        "deviation_semantics": "native reported value; global versus local meaning not established",
        "scope": "Observed TMG aggregate summaries; named sink and field integrals require separate inspection",
    }
