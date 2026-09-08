"""Launch the prepared 200-element contact job once through the persistent job API."""


def run(executor):
    import json, hashlib, runpy
    from pathlib import Path
    import xml.etree.ElementTree as ET

    p = json.loads(
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\contact-job-prepared.json").read_text()
    )
    raw = Path(p["input_path"]).read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest() == p["input_sha256"] and p["mesh_counts"]["elements"] == 200
    )
    audit = runpy.run_path(r"Z:\nx-mcp-integration\simcenter-discovery\audit_contact_export.py")[
        "audit"
    ](ET.fromstring(raw), "resistance", 0.5)
    acceptance = {
        "job_id": p["job_id"],
        "input_sha256_before_launch": p["input_sha256"],
        "expected": {
            "maximum_temperature_k": 294.4,
            "interface_drop_k": 0.5,
            "heat_rejection_w": 1.0,
        },
        "absolute_tolerances": {
            "maximum_temperature_k": 0.03,
            "interface_drop_k": 0.01,
            "heat_rejection_w": 0.001,
        },
        "tolerance_basis": "200 linear tetrahedra on two 10 mm blocks; 0.03 K allows spatial discretization of parabolic heated-block temperature, 0.01 K contact drop and 0.1 percent energy balance",
        "physical_inputs": {
            "power_w": 1.0,
            "contact_resistance_k_w": 0.5,
            "conductivity_w_m_k": 200.0,
            "sink_k": 293.15,
            "block_length_mm": 10.0,
            "area_mm2": 100.0,
        },
        "mesh_refinement_acceptance": "not_claimed",
    }
    file = Path(r"Z:\nx-mcp-integration\simcenter-discovery\contact-acceptance.json")
    if file.exists():
        assert json.loads(file.read_text()) == acceptance
    else:
        file.write_text(json.dumps(acceptance, indent=2))
    launched = executor._sim_launch(p["benchmark_document"], p["job_id"])
    return {"launch": launched, "export_audit": audit, "acceptance": acceptance}
