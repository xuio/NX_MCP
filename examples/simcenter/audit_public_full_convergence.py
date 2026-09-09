"""Audit the retained continuous fixture's final native convergence table.

This checks reported criteria, not discretization error or general CFD accuracy.
"""

import json
import re
from pathlib import Path

from nx_mcp.simcenter.flow_audit import inspect_flow_log

root = Path(__file__).resolve().parents[2] / "tests/simcenter/evidence"
text = (root / "public-full-complete-r1.log").read_text()
report = inspect_flow_log(text)
final = [row for row in report["residual_history"] if row["iteration"] == report["last_iteration"]]
tail = text[text.rfind("Global iteration") :]
checks = {
    "one_coupled_history": text.count(
        "Steady-state convergence history - Coupled thermal/flow simulation"
    )
    == 1,
    "all_five_equations": {r["equation"] for r in final}
    == {"U - Mom", "V - Mom", "W - Mom", "P - Mass", "H - Energy"}
    and len(final) == 5,
    "declared_rms_threshold": report["residual_threshold"] == 1e-6,
    "final_rms_and_native_ok": bool(final)
    and all(0 <= r["residual"] < 1e-6 and r["native_message"] == "OK" for r in final),
    "native_solid_temperature_ok": bool(re.search(r"\| T-Solid[^\n]*\bOK\s*\|", tail)),
    "native_coupled_heat_ok": bool(re.search(r"\| Heat Imbalance[^\n]*\bOK\s*\|", tail)),
    "native_coupled_temperature_ok": bool(re.search(r"\| Max delta T[^\n]*\bOK\s*\|", tail)),
    "completion_marker": report["completion_marker_present"],
}
result = {
    "checks": checks,
    "reported_final_convergence_passed": all(checks.values()),
    "final_iteration": report["last_iteration"],
    "final_equations": final,
    "limitations": [
        "Native y+ row reports LO; no mesh-independence claim",
        "Public aggregate convergence remains conservative; this audits the retained single fixture table",
    ],
}
print(json.dumps(result, indent=2))
assert result["reported_final_convergence_passed"]
