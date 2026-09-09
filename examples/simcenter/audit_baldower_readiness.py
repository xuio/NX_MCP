"""Bounded audit of retained coupled evidence; never connects to NX or launches a job."""

import hashlib
import json
import runpy
from pathlib import Path


def audit(repo):
    evidence = repo / "tests/simcenter/evidence"

    def load(name):
        return json.loads((evidence / name).read_text())

    pressure = load("coupled-pressure-guard-native.json")
    ambient = load("coupled-ambient-guard-native.json")
    density = load("density-atmospheric-context.json")
    coarse = load("finned-layer-extended-r1-final-summary.json")
    fine = load("finned-layer-fine-r1-final-summary.json")
    fan = load("coupled-fan-public.json")
    assert fan["passed"] and not fan["solver_launched"] and not fan["numerical_acceptance"]
    deployed = {
        r["module"]: r["sha256"] for r in load("coupled-journal-deployment.json")["reloaded"]
    }
    public = load("coupled-journal-public.json")["responses"]["exported"]["structuredContent"]
    assert public["coupled_ambient_validation"]["matches"]
    assert public["coupled_pressure_validation"]["matches"]
    source = {}
    for name in ("coupled_input", "input_export"):
        current = hashlib.sha256(
            (repo / "src/nx_mcp/simcenter" / (name + ".py")).read_bytes()
        ).hexdigest()
        source[name] = {
            "sha256": current,
            "matches_retained_native_guard": current == pressure["deployed_sha256"][name],
            "matches_verified_source": current
            == deployed.get(name, pressure["deployed_sha256"][name]),
        }
    room_audit = runpy.run_path(str(repo / "examples/simcenter/audit_room_fan.py"))
    current_cases = {}
    for name, receipt in [
        ("coarse", "room-fan-coarse-results-r2.json"),
        ("fine", "room-fan-fine-results-r1.json"),
        ("half", "room-fan-half-results-r1.json"),
        ("quarter", "room-fan-quarter-results-r1.json"),
    ]:
        if (evidence / receipt).exists():
            current_cases[name] = room_audit["inspect_case"](
                load(receipt), (evidence / f"room-fan-{name}.log").read_text()
            )
    pair = ("half", "quarter") if "quarter" in current_cases else ("fine", "half")
    current_comparison = room_audit["compare"](*(current_cases[name] for name in pair))
    expected_product = density["reference_density_kg_m3"] * density["printed_adjustment_ratio"]
    temperature = ambient["details"]["coupled_ambient_validation"]
    explicit = pressure["specified"]["details"]["coupled_pressure_validation"]
    assert all(v["matches_verified_source"] for v in source.values()), (
        "Changed source needs renewed native review"
    )
    assert not temperature["matches"] and not explicit["matches"]
    assert coarse["ambient_temperature_degC"] == fine["ambient_temperature_degC"] == 0
    native = load("baldower-final-native.json")
    deployed_matches = all(
        hashlib.sha256((repo / "src/nx_mcp/simcenter" / name).read_bytes()).hexdigest() == digest
        for name, digest in native["deployed_source_sha256"].items()
    )
    infrastructure_verified = (
        native["passed"] and native["checked_count"] == 78
        and len(native["deployed_source_sha256"]) == 93 and deployed_matches
        and len(current_cases) == 4
        and all(all(case["checks"].values()) for case in current_cases.values())
    )
    return {
        "conclusion": "READY" if infrastructure_verified else "NOT READY",
        "handover_scope": "Scoped infrastructure; user accepted failed mesh sensitivity on 2026-09-09",
        "deployed_source_matches": deployed_matches,
        "numerical_mesh_acceptance": current_comparison,
        "scope": "Historical failures plus current native room-temperature checks; no new solver execution or whole-release certification",
        "current_room_temperature": {
            "cases": current_cases,
            "comparison_pair": pair,
            "mesh_comparison": current_comparison,
            "native_physical_checks_passed": all(
                all(case["checks"].values()) for case in current_cases.values()
            ),
            "complete_release_verified": False,
        },
        "current_guard_source": source,
        "temperature_mismatch": temperature,
        "specified_pressure_mismatch": explicit,
        "density": {**density, "recomputed_adjusted_density_kg_m3": expected_product},
        "mesh_comparison": {
            "coarse_global_temperature_degC": 0,
            "fine_global_temperature_degC": 0,
            "fine_iteration_limit_reached": fine["iteration_limit_reached_without_convergence"],
            "accepted_room_temperature_comparison": False,
        },
        "cause_classification": "MCP coupled solution initialization omission reproduced and fixed using native UI journal; mesh sensitivity remains failed; scoped infrastructure handover accepted",
        "current_ambient_export": public["coupled_ambient_validation"],
        "current_pressure_export": public["coupled_pressure_validation"],
        "coupled_fan_authoring": {
            "native_public_verified": fan["passed"],
            "committed": fan["committed"],
            "exported": fan["exported"],
            "numerical_acceptance": fan["numerical_acceptance"],
        },
        "next_action": "MECH owns subsequent model-specific numerical acceptance; do not launch further infrastructure mesh sweeps",
        "evidence_sha256": {
            n: hashlib.sha256((evidence / n).read_bytes()).hexdigest()
            for n in [
                "coupled-fan-public.json",
                "coupled-pressure-guard-native.json",
                "coupled-ambient-guard-native.json",
                "density-atmospheric-context.json",
                "finned-layer-extended-r1-final-summary.json",
                "finned-layer-fine-r1-final-summary.json",
            ]
        },
    }


if __name__ == "__main__":
    print(json.dumps(audit(Path(__file__).resolve().parents[2]), indent=2))
