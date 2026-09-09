"""Bounded audit of retained coupled evidence; never connects to NX or launches a job."""

import hashlib
import json
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
    expected_product = density["reference_density_kg_m3"] * density["printed_adjustment_ratio"]
    temperature = ambient["details"]["coupled_ambient_validation"]
    explicit = pressure["specified"]["details"]["coupled_pressure_validation"]
    assert all(v["matches_verified_source"] for v in source.values()), (
        "Changed source needs renewed native review"
    )
    assert not temperature["matches"] and not explicit["matches"]
    assert coarse["ambient_temperature_degC"] == fine["ambient_temperature_degC"] == 0
    return {
        "conclusion": "NOT READY",
        "scope": "Retained coupled room-temperature gate; no new solver execution",
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
        "cause_classification": "MCP coupled solution initialization omission reproduced and fixed using native UI journal; numerical readiness pending",
        "current_ambient_export": public["coupled_ambient_validation"],
        "current_pressure_export": public["coupled_pressure_validation"],
        "coupled_fan_authoring": {
            "native_public_verified": fan["passed"],
            "committed": fan["committed"],
            "exported": fan["exported"],
            "numerical_acceptance": fan["numerical_acceptance"],
        },
        "next_action": "Verify effective fluid model and coupled heated fan benchmark with one mesh comparison; preserve guards and retained artifacts",
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
