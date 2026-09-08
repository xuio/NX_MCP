"""Compare two completed synthetic duct runs without claiming mesh convergence."""

import argparse
import json
from pathlib import Path


def compare(reference, refined):
    rows = []
    for report in (reference, refined):
        if not report["completion_marker_present"] or not report["final_residual_criteria_met"]:
            raise ValueError("Completed residual audit required for both runs")
        if report["fan_operating_points"]["state"] != "reported":
            raise ValueError("Native fan summary required")
        fans = report["fan_operating_points"]["fans"]
        if len(fans) != 1 or fans[0]["name"] != "Duct Inlet":
            raise ValueError("Expected the single synthetic duct fan")
        fan = fans[0]
        mass = report["reported_imbalances"]["mass"]
        if mass["units"] != "%" or abs(mass["value"]) > 0.1:
            raise ValueError("Native mass imbalance exceeds the 0.1 percent benchmark screen")
        q, pressure = fan["volume_flow_m3_s"], fan["pressure_rise_Pa"]
        if q <= 0 or not 0 <= q <= 0.0004:
            raise ValueError("Flow is outside the synthetic curve range")
        curve_error = abs(pressure - (1 - 2500 * q))
        if curve_error > 0.0002:
            raise ValueError("Fan operating point exceeds the native log rounding allowance")
        rows.append(
            {
                "job_id": report["job_id"],
                "flow_m3_s": q,
                "fan_pressure_rise_Pa": pressure,
                "native_mass_imbalance_percent": mass["value"],
                "curve_error_Pa": curve_error,
                "iterations": report["last_iteration"],
                "log_sha256": report["log_sha256"],
            }
        )
    return {
        "scope": "Two-level core-mesh sensitivity for the synthetic K=0 duct",
        "reference": rows[0],
        "refined": rows[1],
        "flow_change_percent": 100 * (rows[1]["flow_m3_s"] / rows[0]["flow_m3_s"] - 1),
        "pressure_change_percent": 100
        * (rows[1]["fan_pressure_rise_Pa"] / rows[0]["fan_pressure_rise_Pa"] - 1),
        "mesh_convergence_established": False,
        "limitations": [
            "Only core sizing refined; boundary-layer spacing unchanged",
            "Two levels do not establish observed convergence order or an extrapolated error bound",
            "Model and boundary equivalence require the separate deck audit",
            "Constant-density surrogate, not coupled or natural-convection validation",
            "Rounded native log values; no acoustic or product certification",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("reference")
    parser.add_argument("refined")
    parser.add_argument("output")
    args = parser.parse_args()
    reference = json.loads(Path(args.reference).read_text())["fine-k0-flow-01"]
    refined = json.loads(Path(args.refined).read_text())["responses"]["audit"]["structuredContent"]
    Path(args.output).write_text(json.dumps(compare(reference, refined), indent=2) + "\n")
