"""Parse observed 2606 steady-flow log tables, without accepting a solve."""

import math
import re

from nx_mcp.simcenter.fan_summary import inspect_fan_operating_points
from nx_mcp.simcenter.solver_log import inspect_solver_log

_N = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_EQUATIONS = {"U - Mom", "V - Mom", "W - Mom", "P - Mass"}


def _number(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Nonfinite numeric value in flow log")
    return number


def inspect_flow_log(text, boundary_types=None):
    if not isinstance(text, str) or len(text) > 8 * 1024 * 1024:
        raise ValueError("Flow log must be text no larger than 8 MiB")
    # Native Windows logs contain CRCRLF; normalize without adding phantom rows.
    text = text.replace("\r", "")
    coupled = text.count("Steady-state convergence history - Coupled thermal/flow simulation") == 1
    energy_expected = coupled or "Solving Flow and Thermal" in text or "| H - Energy" in text
    equations = _EQUATIONS | {"H - Energy"} if energy_expected else _EQUATIONS
    thresholds = re.findall(r"Flow converged when RMS residual less than:\s*(" + _N + r")", text)
    threshold = _number(thresholds[0]) if len(thresholds) == 1 else None
    history = []
    iterations = []
    iteration = None
    region = None
    expecting_iteration = False
    pattern = re.compile(
        r"\|\s*(U - Mom|V - Mom|W - Mom|P - Mass|H - Energy)\s*\|\s*(\d+)\s*\|\s*("
        + _N
        + r")\s*\|\s*("
        + _N
        + r"|\+{4}"
        + r")\s*\|\s*("
        + _N
        + r")\s*\|\s*(OK|--)\s*\|"
    )
    for line in text.splitlines():
        if "Global iteration |" in line:
            expecting_iteration = True
            iteration = None
            region = None
            continue
        if expecting_iteration:
            match = re.match(r"\s*(\d+)\s*\+", line)
            if match:
                iteration = int(match[1])
                iterations.append(iteration)
                expecting_iteration = False
        match = re.match(r"\s*\|\s*(.*?)\s+- Step of (" + _N + r")s - Step (\d+)\s*\|", line)
        if match:
            region = match[1]
        match = pattern.fullmatch(line.strip())
        if match and iteration is not None and region is not None:
            history.append(
                {
                    "iteration": iteration,
                    "region": region,
                    "equation": match[1],
                    "linear_iterations": int(match[2]),
                    "linear_residual": _number(match[3]),
                    "rate": _number(match[4]) if match[4] != "++++" else None,
                    "rate_overflow": match[4] == "++++",
                    "residual": _number(match[5]),
                    "native_message": match[6],
                }
            )
    last = max(iterations, default=None)
    final = [r for r in history if r["iteration"] == last]
    regions = {r["region"] for r in final}
    complete = bool(final) and all(
        len([r for r in final if r["region"] == region]) == len(equations)
        and {r["equation"] for r in final if r["region"] == region} == equations
        for region in regions
    )
    # Recognize only the observed single steady history. Multiple/restarted
    # histories need their own explicit solution/step identity.
    steady = text.count("Steady-state convergence history - Flow simulation") == 1
    residuals_met = None
    if complete and steady and threshold is not None and math.isfinite(threshold) and threshold > 0:
        residuals_met = all(
            math.isfinite(r["residual"])
            and 0 <= r["residual"] < threshold
            and r["native_message"] == "OK"
            for r in final
        )
    balances = {}
    for key in ("Momentum", "Mass", "Energy"):
        matches = re.findall(
            r"Flow solver - " + key + r" imbalance\s+(" + _N + r")\s+Percent", text
        )
        if len(matches) == 1:
            balances[key.lower()] = {
                "value": _number(matches[0]),
                "units": "%",
                "definition": "native reported imbalance; denominator not independently established",
            }
    boundaries = []
    boundary_pattern = re.compile(
        r"^\s*(.*?)\s+(" + _N + r")\s+(mm\^3/s|m\^3/s)\s+(" + _N + r")\s+kg/s\s*$", re.M
    )
    sections = text.split("Volume/Mass Flow Summary")
    if len(sections) == 2 and "(Values > 0 are inflows)" in sections[1]:
        section = sections[1].split("Solver Convergence")[0]
        for match in boundary_pattern.finditer(section):
            name = match[1]
            candidates = [
                kind
                for full, kind in (boundary_types or {}).items()
                if full == name or (len(name) == 26 and full.startswith(name))
            ]
            kind = candidates[0] if len(candidates) == 1 else None
            scope = (
                "internal"
                if kind == "Internal Fan"
                else "external"
                if kind in {"Inlet", "Opening", "Outlet"}
                else "unknown"
            )
            boundaries.append(
                {
                    "name": name,
                    "native_boundary_type": kind,
                    "flow_scope": scope,
                    "volume_flow_m3_s": _number(match[2]) * (1e-9 if match[3] == "mm^3/s" else 1),
                    "mass_flow_kg_s": _number(match[4]),
                    "positive_direction": "into_domain"
                    if scope == "external"
                    else "native_internal_flow_sign"
                    if scope == "internal"
                    else "unclassified_native_summary_sign",
                }
            )
    failure = inspect_solver_log(text)
    from nx_mcp.simcenter.coupled_log import inspect_coupled_summary

    return {
        "format": "observed_simcenter_2606_steady_coupled"
        if coupled
        else "observed_simcenter_2606_steady_flow",
        "completion_marker_present": "Solve completed at:" in text,
        "failure_evidence": failure,
        "residual_threshold": threshold,
        "last_iteration": last,
        "final_equations_complete": complete,
        "final_residual_criteria_met": residuals_met,
        "residual_history": history,
        "reported_imbalances": balances,
        "boundary_flows": boundaries,
        "fan_operating_points": inspect_fan_operating_points(text),
        "coupled_summary": inspect_coupled_summary(text) if coupled else None,
        "rounded_boundary_mass_sum_kg_s": sum(
            r["mass_flow_kg_s"] for r in boundaries if r["flow_scope"] == "external"
        )
        if boundaries
        and all(r["flow_scope"] != "unknown" for r in boundaries)
        and any(r["flow_scope"] == "external" for r in boundaries)
        else None,
        "rounding_warning": "Boundary values are rounded in the log; a zero sum does not establish zero imbalance",
        "numerical_convergence": "not_established",
        "results_validated": False,
        "scope": "Log observations only; input/job association, all configured criteria and mesh sensitivity require separate audits",
    }


def audit_job_flow_log(
    workspace, job_id, log_name, job_folder="simcenter-jobs", offset=0, limit=50
):
    import hashlib

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.jobs import JobStore
    from nx_mcp.simcenter.log_reader import owned_output, valid_log_name

    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise NXToolError("NX_INVALID_ARGUMENT", "offset >= 0 and limit 1..100")
    valid_log_name(log_name)
    job, directory = owned_output(JobStore(workspace, job_folder), job_id)
    path = workspace.resolve(directory / log_name)
    if path.parent != directory:
        raise NXToolError("NX_INVALID_ARGUMENT", "Select a directly owned job log")
    with path.open("rb") as stream:
        data = stream.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise NXToolError("NX_SIM_LOG_TOO_LARGE", "Flow audit log exceeds 8 MiB")
    # Native summaries include internal fan flows and truncate names to 26 chars.
    # Resolve roles from this job's owned input; unknown/ambiguous roles suppress
    # the external mass sum rather than counting internal transport as an inlet.
    boundary_types = None
    try:
        import xml.etree.ElementTree as ET

        input_path = workspace.resolve(job["manifest"]["prepared_input"]["input"]["path"])
        if input_path.parent == directory and input_path.stat().st_size <= 64 * 1024 * 1024:
            raw = input_path.read_bytes()
            if b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper():
                root = ET.fromstring(raw)
                if root.tag == "SolutionFile":
                    rows = root.findall(".//FlowBc")
                    names = [row.attrib.get("uname") for row in rows]
                    if all(names) and len(set(names)) == len(names):
                        boundary_types = {
                            row.attrib["uname"]: row.attrib.get("type") for row in rows
                        }
    except (KeyError, OSError, ValueError, ET.ParseError):
        pass
    report = inspect_flow_log(data.decode("utf-8", errors="replace"), boundary_types=boundary_types)
    history = report.pop("residual_history")
    return {
        "job_id": job_id,
        "request_sha256": job["request_sha256"],
        "persisted_job_state": job["state"],
        "log_name": log_name,
        "log_sha256": hashlib.sha256(data).hexdigest(),
        "observed_bytes": len(data),
        "snapshot_semantics": "bytes read; file may still be growing",
        **report,
        "residual_history": history[offset : offset + limit],
        "history_total": len(history),
        "next_offset": offset + limit if offset + limit < len(history) else None,
        "job_state_changed": False,
    }
