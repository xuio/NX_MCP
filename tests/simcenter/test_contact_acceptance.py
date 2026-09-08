import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
AUDIT = runpy.run_path(str(ROOT / "examples/simcenter/audit_contact_acceptance.py"))["audit"]
EVIDENCE = ROOT / "tests/simcenter/evidence"


def inputs():
    return (
        json.loads((EVIDENCE / "contact-nodal-results.json").read_text())["nodes"],
        (EVIDENCE / "contact-numerical.log").read_text(),
        (EVIDENCE / "contact-numerical.xml").read_bytes(),
        {"maximum_temperature_k": 294.4, "interface_drop_k": 0.5, "heat_rejection_w": 1.0},
    )


def test_retained_native_contact_values_and_criterion():
    result = AUDIT(*inputs())
    assert not result["native_convergence"]["passed"]
    assert result["native_convergence"]["native_mode"] == "automatic"
    assert result["native_convergence"]["criterion_k"] is None
    assert result["temperature_absolute_error_k"] < 0.03
    assert result["interface_absolute_error_k"] < 0.01


def test_missing_convergence_cannot_be_accepted():
    nodes, log, deck, expected = inputs()
    with pytest.raises(ValueError, match="convergence record"):
        AUDIT(nodes, log.replace("TDmax", "missing"), deck, expected)


def test_wrong_interface_assignment_is_numerically_detected():
    nodes, log, deck, expected = inputs()
    for node in nodes:
        if node.get("interface_region") == "heated":
            node["temperature_deg_c"] -= 0.5
    assert AUDIT(nodes, log, deck, expected)["interface_absolute_error_k"] > 0.49
