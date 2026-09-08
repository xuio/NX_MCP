"""Reproduce the bounded contact benchmark's numerical checks from retained evidence."""

import hashlib
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

from nx_mcp.simcenter.thermal_balance import inspect_thermal_balances


def audit(nodes, log, deck, expected):
    root = ET.fromstring(deck)
    settings = root.find(".//ThermalParameters")

    def value(name):
        rows = [p for p in settings.findall("Property") if p.get("name") == name]
        if len(rows) != 1:
            raise ValueError("Missing/ambiguous thermal control")
        return float(rows[0].findtext("Value"))

    selector = value("Steady State - Convergence Criteria")
    if selector not in (0, 1):
        raise ValueError("Unverified convergence selector")
    tolerance = value("Steady State - Maximum Temperature Change")
    matches = re.findall(r"No\. of iterations\s*=\s*(\d+)\s+TDmax\s*=\s*([\d.E+-]+)", log)
    if len(matches) != 1:
        raise ValueError("Expected one steady thermal convergence record")
    iterations, change = int(matches[0][0]), float(matches[0][1])
    bounds = [[min(n["xyz"][i] for n in nodes), max(n["xyz"][i] for n in nodes)] for i in range(3)]
    if bounds != [[0.0, 20.0], [0.0, 10.0], [0.0, 10.0]]:
        raise ValueError("Result bounds differ from isolated mm fixture")
    groups = {
        side: [n["temperature_deg_c"] for n in nodes if n.get("interface_region") == side]
        for side in ("heated", "sink")
    }
    if any(len(v) != 12 for v in groups.values()):
        raise ValueError("Expected 12 interface nodes per block")
    means = {k: sum(v) / len(v) for k, v in groups.items()}
    interface_drop = means["heated"] - means["sink"]
    maximum = max(n["temperature_deg_c"] for n in nodes) + 273.15
    if "mN-mm/s" not in log:
        raise ValueError("Missing explicit native power units")
    balances = inspect_thermal_balances(log, power_unit="mN-mm/s")
    return {
        "maximum_temperature_k": maximum,
        "interface_drop_k": interface_drop,
        "interface_temperature_means_deg_c": means,
        "interface_mean_semantics": "arithmetic mean of native interface nodes; not area weighted",
        "native_convergence": {
            "iterations": iterations,
            "tdmax_k": change,
            "criterion_k": tolerance if selector == 1 else None,
            "inactive_or_active_exported_temperature_change_k": tolerance,
            "native_mode": "automatic" if selector == 0 else "specified",
            "effective_criterion_verified": selector == 1,
            "passed": selector == 1
            and change < tolerance
            and iterations < value("Thermal Steady State - Iteration Limit"),
        },
        "thermal_balances": balances,
        "expected": expected,
        "result_bounds_mm": bounds,
        "temperature_absolute_error_k": abs(maximum - expected["maximum_temperature_k"]),
        "interface_absolute_error_k": abs(interface_drop - expected["interface_drop_k"]),
    }


if __name__ == "__main__":
    evidence = Path(__file__).parents[2] / "tests/simcenter/evidence"
    nodes = json.loads((evidence / "contact-nodal-results.json").read_text())["nodes"]
    log = (evidence / "contact-numerical.log").read_text()
    deck = (evidence / "contact-numerical.xml").read_bytes()
    criteria = json.loads((evidence / "contact-acceptance-criteria.json").read_text())
    result = audit(nodes, log, deck, criteria["expected"])
    summary = result["thermal_balances"]["summaries"]
    if len(summary) != 1 or summary[0]["state"] != "complete":
        raise ValueError("Expected one complete steady thermal balance")
    power = summary[0]["values"]
    rejected_w = power["heat_flow_into_sinks"] / 1e6
    generated_w = power["heat_load_into_elements"] / 1e6
    result["derived_balance"] = {
        "heat_rejection_w": rejected_w,
        "heat_generation_w": generated_w,
        "rounded_power_difference_w": generated_w - rejected_w,
        "semantics": "Converted native rounded aggregate values; not exact field integration or an interpretation of the reported local/global deviation",
    }
    tol = criteria["absolute_tolerances"]
    checks = {
        "maximum_temperature": result["temperature_absolute_error_k"]
        <= tol["maximum_temperature_k"],
        "interface_drop": result["interface_absolute_error_k"] <= tol["interface_drop_k"],
        "heat_rejection": abs(rejected_w - criteria["expected"]["heat_rejection_w"])
        <= tol["heat_rejection_w"],
        "heat_generation": abs(generated_w - criteria["physical_inputs"]["power_w"])
        <= tol["heat_rejection_w"],
        "convergence": result["native_convergence"]["passed"],
    }
    public = json.loads((evidence / "contact-solve-finish.json").read_text())["responses"]
    observed = public["status_observations"][-1]["structuredContent"]["evidence"]
    identity = public["identity"]["structuredContent"]["job_binding"]
    checks["solved_input_identity"] = (
        hashlib.sha256(deck).hexdigest() == observed["input_comparison"]["after"]["sha256"]
        and observed["input_comparison"]["xml_content_identical"]
    )
    checks["observed_result_association"] = identity["associated_result_matches_observed_artifact"]
    checks["saved_dependency_hashes"] = all(row["matches"] for row in identity["revision"]["files"])
    result.update(
        checks=checks,
        scoped_artifact_benchmark_passed=all(checks.values()),
        physical_artifact_checks_passed=all(v for k, v in checks.items() if k != "convergence"),
        current_session_freshness=identity["state"],
        freshness_reasons=identity["reasons"],
        acceptance_scope="One 200-element steady two-block result artifact; no mesh convergence study or whole-model freshness claim",
        tolerances=tol,
        job_id=criteria["job_id"],
    )
    result["source_hashes"] = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [
            evidence / "contact-nodal-results.json",
            evidence / "contact-numerical.log",
            evidence / "contact-numerical.xml",
            evidence / "contact-acceptance-criteria.json",
            evidence / "contact-solve-finish.json",
        ]
    }
    print(json.dumps(result, indent=2))
