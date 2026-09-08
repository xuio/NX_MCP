"""Compare captured native benchmark results; never synthesize solver output."""

import argparse
import hashlib
import json
from pathlib import Path

from nx_mcp.simcenter.thermal_balance import inspect_thermal_balances


def compare(root):
    rows = []
    for kind, expected_rise, job in (
        ("flux", 5.0, "surface-flux-numerical-r1"),
        ("volume", 2.5, "volume-generation-numerical-r1"),
    ):
        receipt_path = root / f"native-{kind}-finish.json"
        receipt = json.loads(receipt_path.read_text())["responses"]
        native = receipt["temperature"]["structuredContent"]
        assert not receipt["temperature"]["isError"] and native["units"] == "degC"
        assert receipt["release"]["structuredContent"]["released"]
        assert receipt["status_observations"][-1]["structuredContent"]["state"] == "solver_exited"
        log_path = root / f"{kind}-native-solver.log"
        raw = log_path.read_bytes()
        balances = inspect_thermal_balances(raw.decode(errors="replace"), power_unit="mN-mm/s")
        rise = native["maximum"] - native["minimum"]
        relative = abs(rise - expected_rise) / expected_rise
        rows.append(
            {
                "kind": kind,
                "job_id": job,
                "minimum_degC": native["minimum"],
                "maximum_degC": native["maximum"],
                "expected_rise_K": expected_rise,
                "actual_rise_K": rise,
                "relative_rise_error": relative,
                "rise_tolerance": 0.01,
                "fixed_boundary_tolerance_K": 0.001,
                "temperature_check_passed": relative <= 0.01
                and abs(native["minimum"] - 20) <= 0.001,
                "tolerance_basis": "1% comparison on linear TET benchmark; separate from mesh refinement convergence",
                "log_sha256": hashlib.sha256(raw).hexdigest(),
                "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
                "exported_units": {
                    "system": "Millimeters",
                    "length_conversion_factor": 1000,
                    "force_conversion_factor": 1000,
                },
                "power_conversion": "1 W = 1000000 mN-mm/s, from exported length/force factors",
                "expected_applied_power_W": 1.0,
                "thermal_summaries": balances,
                "heat_balance_interpretation": "Rounded summary values; reported deviation is retained, not treated as exact global conservation",
                "mesh_convergence": "not_established",
                "complete_result_freshness": "not_established",
            }
        )
    return {
        "scope": "NX 2606 constant-property isolated 100x10x10 mm bars, k=200 W/(m K), one end fixed at 20 C; no product validation",
        "cases": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = compare(args.evidence_directory)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    assert all(row["temperature_check_passed"] for row in result["cases"])
    print(json.dumps(result, indent=2))
