"""Preserve solver-input identity across NX's export performed during Solve."""

import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from nx_mcp.simcenter.solver_log import inspect_input_xml


def input_identity(data):
    validation = inspect_input_xml(data)
    if validation["state"] != "well_formed":
        raise ValueError("Cannot fingerprint invalid solver input XML")
    # Ignore XML comments, including the vendor's export-date comment. Preserve
    # whitespace in values: trimming it could hide a changed string property.
    canonical = ET.canonicalize(
        xml_data=data.decode("utf-8-sig"), with_comments=False, strip_text=False
    )
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "xml_content_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "bytes": len(data),
        "canonicalization": "xml_c14n2_no_comments",
    }


def preserve_input(job_directory, phase, data):
    """Write an immutable input snapshot in an already workspace-validated job dir.

    Repeated identical writes are safe. A conflicting snapshot is rejected.
    This does not prove solver completion, result freshness, or numerical validity.
    """
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", phase):
        raise ValueError("Invalid snapshot phase")
    identity = input_identity(data)
    directory = Path(job_directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (phase + ".xml")
    try:
        with target.open("xb") as stream:
            stream.write(data)
            stream.flush()
            import os

            os.fsync(stream.fileno())
    except FileExistsError:
        if target.read_bytes() != data:
            raise ValueError(
                "Existing input snapshot differs; inspect this job before retrying"
            ) from None
    return {"path": str(target), **identity}


def compare_inputs(before, after):
    previous, current = input_identity(before), input_identity(after)
    return {
        "before": previous,
        "after": current,
        "byte_identical": previous["sha256"] == current["sha256"],
        "xml_content_identical": previous["xml_content_sha256"] == current["xml_content_sha256"],
        "scope": "input XML only; result association and solver outcome require separate verification",
    }
