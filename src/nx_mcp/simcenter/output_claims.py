"""Permanent ownership of isolated solver output directories.

These records deliberately never expire or unlock on a timeout or terminal job.
A new run uses a new directory, preserving previous solver artifacts. This is
output exclusion, not a licence, NX-session, or process-concurrency decision.
"""

import os

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.jobs import _read, _write_once

_RECORD = ".nx-sim-output-owner.json"


def claim_output(store, job_id, output_directory):
    """Claim a workspace directory for one immutable, already reserved job."""
    current = store.inspect(job_id)
    if current["state"] == "unknown":
        raise NXToolError(
            "NX_SIM_OUTPUT_UNCERTAIN",
            "Job records are incomplete; inspect retained records before using solver outputs",
            details={"mutation_outcome": "not_started", "job_id": job_id},
        )
    directory = store.workspace.resolve(output_directory)
    if directory == store.workspace.root:
        raise NXToolError(
            "NX_INVALID_ARGUMENT",
            "Use a dedicated output subdirectory, not the workspace root",
            details={"mutation_outcome": "not_started"},
        )
    owner = {
        "schema": 1,
        "job_id": job_id,
        "job_directory": os.path.normcase(str(store._directory(job_id))),
        "request_sha256": current["request_sha256"],
        "output_directory": os.path.normcase(str(directory)),
    }
    directory.mkdir(parents=True, exist_ok=True)
    record = store.workspace.ensure_inside(directory / _RECORD)
    try:
        _write_once(record, owner)
        replayed = False
    except FileExistsError:
        try:
            actual = _read(record)
        except (OSError, ValueError):
            raise NXToolError(
                "NX_SIM_OUTPUT_UNCERTAIN",
                "Output ownership is incomplete; retain this directory and inspect the owner record",
                details={"mutation_outcome": "not_started", "output_directory": str(directory)},
            ) from None
        if actual != owner:
            raise NXToolError(
                "NX_SIM_OUTPUT_CONFLICT",
                "Another job owns this output directory; use a new isolated analysis/output directory",
                details={"mutation_outcome": "not_started", "output_directory": str(directory)},
            ) from None
        replayed = True
    return {**owner, "replayed": replayed, "retention": "permanent; no automatic release"}
