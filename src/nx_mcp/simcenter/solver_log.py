"""Conservative interpretation of observed Simcenter 2606 translator logs.

An NX launch return, process exit or 'Solve completed' footer does not establish
numerical convergence. Unrecognized log formats remain unknown.
"""

from __future__ import annotations

import re

_FATAL = re.compile(r"\bNX2TMG\s*-\s*FATAL ERROR\s+(\d+)\b", re.IGNORECASE)
_ERROR = re.compile(r"\bNX2TMG\s*-\s*(?:FATAL\s+)?ERROR\s+(\d+)\b", re.IGNORECASE)
_ABORT = re.compile(r"Run aborted due to (?:fatal )?errors", re.IGNORECASE)
_FATAL_ABORT = re.compile(r"Run aborted due to fatal errors", re.IGNORECASE)


def inspect_solver_log(text: str) -> dict:
    """Return only failure evidence supported by the native translator log.

    This intentionally neither echoes arbitrary log lines (which can contain
    environment details) nor infers success from absence of recognized errors.
    The caller must associate the log with a durable job and exact model revision.
    """
    codes = list(dict.fromkeys(int(match) for match in _FATAL.findall(text)))
    errors = list(dict.fromkeys(int(match) for match in _ERROR.findall(text)))
    aborted = bool(_ABORT.search(text))
    return {
        "state": "failed" if errors or aborted else "unknown",
        "stage": "translation" if errors else "unknown",
        "translator_fatal_codes": codes,
        "translator_error_codes": errors,
        "abort_reported": aborted,
        "fatal_abort_reported": bool(_FATAL_ABORT.search(text)),
        "numerical_convergence": "not_established",
        "results_validated": False,
        "next_action": (
            "Inspect native setup and translator diagnostics; do not automatically rerun."
            if errors or aborted
            else "Inspect job process status, residuals and result validation before classifying."
        ),
    }


def inspect_input_xml(data: bytes) -> dict:
    """Reject malformed native exports before launch; XML validity is not solve readiness."""
    import xml.etree.ElementTree as ET

    if len(data) > 64 * 1024 * 1024:
        return {"state": "invalid", "reason": "input_exceeds_validation_limit"}
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        return {"state": "invalid", "reason": "xml_declarations_not_supported"}
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        return {"state": "invalid", "reason": "malformed_xml", "position": list(exc.position)}
    if root.tag != "SolutionFile":
        return {"state": "invalid", "reason": "unexpected_root"}
    return {
        "state": "well_formed",
        "step_definitions": len(root.findall("./SolutionStepList/SolutionStep")),
        "mesh_counts": {
            "elements": len(root.findall("./ElementList/Set/E")),
            "nodes": len(root.findall("./NodeList/N")),
            "element_sets": len(root.findall("./ElementList/Set")),
            "scope": "observed_multiphysics_xml_layout",
        }
        if root.find("ElementList") is not None and root.find("NodeList") is not None
        else None,
        "solve_readiness": "not_established",
    }
