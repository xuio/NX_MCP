"""Audit native C-benchmark temperature samples against the lumped reference.

Usage: python audit_transient.py native-temperatures.json --expected-samples 21
This checks temperature history only, not complete benchmark acceptance.
"""

import argparse
import json
import math
from pathlib import Path


def audit(receipt, expected_samples):
    if receipt.get("status") != "success":
        raise ValueError("Native result extraction did not succeed")
    if (
        isinstance(expected_samples, bool)
        or not isinstance(expected_samples, int)
        or expected_samples < 2
    ):
        raise ValueError("expected_samples must be an integer >= 2")
    samples = receipt.get("temperatures", [])
    if len(samples) != expected_samples:
        raise ValueError("Missing or extra native temperature samples")
    reference = next(
        row
        for row in json.loads(Path(__file__).with_name("benchmarks.json").read_text())["benchmarks"]
        if row["id"] == "C_transient"
    )
    ambient = reference["initial_and_ambient_K"] - 273.15
    rise = reference["expected_lumped_steady_delta_T_K"]
    tau = reference["expected_lumped_time_constant_s"]
    tolerance = reference["temperature_relative_tolerance"]
    rows = []
    for index, sample in enumerate(samples):
        times = [v for v in sample["values"] if v["kind"] == "time"]
        if len(times) != 1 or times[0]["native_unit"] != "Second":
            raise ValueError("Expected one native time in seconds")
        time = times[0]["value"]
        expected_time = index * 5 * tau / (expected_samples - 1)
        if not math.isfinite(time) or not math.isclose(time, expected_time, abs_tol=1e-8):
            raise ValueError("Time history does not cover every requested benchmark time")
        temperature = sample["temperature"]
        if temperature["units"] != "degC":
            raise ValueError("Temperature units must be explicit Celsius")
        minimum, maximum = temperature["minimum"], temperature["maximum"]
        if not all(math.isfinite(v) for v in (minimum, maximum)) or minimum > maximum:
            raise ValueError("Invalid temperature extrema")
        expected = ambient + rise * (1 - math.exp(-time / tau))
        error = max(abs(minimum - expected), abs(maximum - expected)) / rise
        rows.append(
            {
                "time_s": time,
                "minimum_C": minimum,
                "maximum_C": maximum,
                "analytical_C": expected,
                "normalized_error": error,
            }
        )
    worst = max(rows, key=lambda row: row["normalized_error"])
    return {
        "benchmark": "C_transient",
        "temperature_history_passed": worst["normalized_error"] <= tolerance,
        "benchmark_accepted": False,
        "acceptance_scope": "temperature history only; independent mesh/time refinement and energy audit required",
        "reference": reference,
        "normalization": "absolute error divided by analytical steady temperature rise",
        "maximum_normalized_error": worst["normalized_error"],
        "worst_time_s": worst["time_s"],
        "samples": rows,
    }


def audit_energy(run_directory):
    """Bound C-benchmark energy residual using native cell extrema and sink energy.

    The volume average lies between cell extrema. Printed-value rounding is
    propagated explicitly; no unweighted nodal mean is used as stored energy.
    """
    import re
    import xml.etree.ElementTree as ET
    from decimal import Decimal

    root = Path(run_directory)

    def one(pattern):
        matches = list(root.glob(pattern))
        if len(matches) != 1:
            raise ValueError(f"Expected one native artifact: {pattern}")
        return matches[0]

    xml = ET.fromstring(one("*Conduction.xml").read_bytes())
    scale = float(xml.find("Units/LengthConversionFactor").text) * float(
        xml.find("Units/ForceConversionFactor").text
    )
    if scale != 1e6:
        raise ValueError("This benchmark adapter requires the verified millimeter solver units")
    report = one("*Conduction_report.log").read_text()
    log = one("*Conduction.log").read_text()
    times = re.findall(r"\bTime=\s*([0-9.E+\-]+)", report)
    end = float(times[-1])
    if not math.isclose(end, 2025.0):
        raise ValueError("Report does not reach the benchmark end time")
    groups = re.findall(r"Group: BENCHMARK_C_POWER\s*\n\s*([^\n]+)", report)
    fields = groups[-1].split()
    if len(fields) != 8:
        raise ValueError("Unrecognized native body summary")
    maximum, minimum = float(fields[0]), float(fields[2])
    power, capacity, mass = float(fields[5]) / scale, float(fields[6]) / scale, float(fields[7])
    if not all(
        math.isclose(a, b, rel_tol=1e-6)
        for a, b in [(power, 0.1), (capacity, 2.43), (mass, 0.0027)]
    ):
        raise ValueError("Native body summary does not match the reference power/capacity/mass")
    sinks = re.findall(r"Fluid ambient group\s+([0-9.E+\-]+)\s+([0-9.E+\-]+)\s+([0-9.E+\-]+)", log)
    ambient, _, energy_text = sinks[-1]
    if float(ambient) != 20:
        raise ValueError("Unexpected native ambient temperature")

    def rounding(value):
        return 0.5 * 10 ** Decimal(value).as_tuple().exponent

    rejected = float(energy_text) / scale
    rejected_rounding = rounding(energy_text) / scale
    stored = [
        capacity * (minimum - rounding(fields[2]) - 20),
        capacity * (maximum + rounding(fields[0]) - 20),
    ]
    applied = power * end
    residual = [
        applied - rejected - rejected_rounding - stored[1],
        applied - rejected + rejected_rounding - stored[0],
    ]
    worst = max(abs(value) for value in residual) / applied
    return {
        "benchmark": "C_transient",
        "energy_balance_passed": worst <= 0.005,
        "benchmark_accepted": False,
        "tolerance": 0.005,
        "tolerance_basis": "0.5% bounds printed sink-energy and cell-temperature rounding; independent temperature/refinement checks remain required",
        "applied_energy_J": applied,
        "printed_rejected_energy_J": rejected,
        "rejected_energy_rounding_J": rejected_rounding,
        "stored_energy_bound_J": stored,
        "balance_residual_bound_J": residual,
        "worst_normalized_residual": worst,
        "basis": "native body cell extrema and uniform benchmark thermal capacity; no nodal-average approximation",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--expected-samples", type=int, required=True)
    parser.add_argument("--native-run-dir", type=Path)
    args = parser.parse_args()
    result = audit(json.loads(args.receipt.read_text()), args.expected_samples)
    if args.native_run_dir:
        result["energy_audit"] = audit_energy(args.native_run_dir)
    print(json.dumps(result, indent=2))
