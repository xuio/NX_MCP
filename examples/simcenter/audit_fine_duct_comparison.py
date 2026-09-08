"""Audit retained K0/K2 log snapshots and matched input evidence, no solver calls."""

import hashlib
import json
import sys
from pathlib import Path

from nx_mcp.simcenter.fan_results import parse_native_fan_summary


def audit(directory, k0_receipt, k2_receipt, input_comparison):
    inputs = json.loads(Path(input_comparison).read_text())
    inputs = inputs.get("input_comparison", inputs)
    assert inputs["mesh_xml_identical"] and inputs["fan_curve_identical"]
    assert inputs["different_property_names"] == ["Head Loss Coefficient"]
    raw0 = json.loads(Path(k0_receipt).read_text())
    r0 = raw0.get("responses", raw0)["audit"]
    r0 = r0.get("structuredContent", r0)
    r2 = json.loads(Path(k2_receipt).read_text())["audit"]
    cases = {}
    for key, receipt in [("K0", r0), ("K2", r2)]:
        raw = (Path(directory) / f"fine-{key.lower()}-native.log").read_bytes()
        assert hashlib.sha256(raw).hexdigest() == receipt["log_sha256"]
        text = raw.decode(errors="strict")
        assert "mN/mm^2" in text
        summary = parse_native_fan_summary(text, native_pressure_unit="mN/mm^2")
        assert len(summary["fans"]) == 1
        fan = summary["fans"][0]
        q, dp = fan["volume_flow_m3_s"], fan["pressure_rise_Pa"]
        # This benchmark's exact synthetic curve is P=1-2500*Q in SI.
        assert 0 <= q <= 0.0004
        expected = 1 - 2500 * q
        error = abs(dp - expected)
        # Q rounding contributes at most 0.000125 Pa and P rounding 0.00005 Pa.
        assert error <= 0.0002
        assert receipt["final_residual_criteria_met"] and receipt["completion_marker_present"]
        mass = receipt["reported_imbalances"]["mass"]["value"]
        assert mass < 0.1  # screening limit; not a mesh-convergence criterion
        flows = {row["name"]: row["volume_flow_m3_s"] for row in receipt["boundary_flows"]}
        assert flows["Duct Inlet"] > 0 and flows["Duct Opening"] < 0
        cases[key] = {
            "job_id": receipt["job_id"],
            "flow_m3_s": q,
            "fan_pressure_rise_Pa": dp,
            "curve_pressure_Pa": expected,
            "curve_absolute_error_Pa": error,
            "native_mass_imbalance_percent": mass,
            "iterations": receipt["last_iteration"],
            "residual_threshold": receipt["residual_threshold"],
            "log_sha256": receipt["log_sha256"],
        }
    reduction = 100 * (1 - cases["K2"]["flow_m3_s"] / cases["K0"]["flow_m3_s"])
    assert reduction > 5  # well above log precision; meaningful restriction response
    return {
        "scope": "matched fine-mesh synthetic fan/duct restriction response",
        "cases": cases,
        "flow_reduction_percent": reduction,
        "checks_passed": [
            "identical exported node and element XML",
            "identical fan curve; head loss is only differing exported property",
            "positive inlet and negative outlet flow",
            "native reported mass imbalance below 0.1 percent",
            "final RMS threshold met",
            "fan curve within 0.0002 Pa log-rounding allowance",
            "flow reduction exceeds 5 percent",
        ],
        "limitations": [
            "constant-density fluid surrogate; no buoyancy or conjugate heat transfer validation",
            "static fan convention relies on the earlier native mode-5 pressure audit",
            "mesh convergence and full benchmark D acceptance remain incomplete",
            "rounded log values; no acoustic or product certification",
        ],
        "input_comparison": inputs,
    }


if __name__ == "__main__":
    directory, k0, k2, inputs, output = sys.argv[1:]
    Path(output).write_text(json.dumps(audit(directory, k0, k2, inputs), indent=2) + "\n")
