"""Bind a prepared input to explicit saved dependencies before native launch.

The caller supplies freshly read native document flags on the NX thread. This
does not discover omitted external files or prove that input matches all physics
settings; native setup/readback and complete dependency discovery remain needed.
"""

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.result_identity import fingerprint_file
from nx_mcp.simcenter.revisions import audit_saved_revision
from nx_mcp.simcenter.solver_manifest import input_identity


def _input(workspace, path, maximum_bytes):
    path = workspace.resolve(path)
    before = fingerprint_file(path, maximum_bytes=maximum_bytes)
    with path.open("rb") as stream:
        data = stream.read(maximum_bytes + 1)
    if len(data) > maximum_bytes:
        raise ValueError("Input grew beyond the preparation byte budget")
    identity = input_identity(data)
    if identity["sha256"] != before["sha256"]:
        raise NXToolError(
            "NX_SIM_INPUT_CHANGED", "Input changed during preparation; inspect before retrying"
        )
    return {"path": str(path), **identity}


def capture_prepared_input(workspace, input_path, documents, *, maximum_bytes=1_073_741_824):
    if type(maximum_bytes) is not int or maximum_bytes < 1:
        raise ValueError("maximum_bytes must be a positive integer")
    if not documents:
        raise ValueError("Explicit native document dependencies are required")
    files, consumed, paths = [], 0, set()
    for row in documents:
        path = workspace.resolve(row["path"])
        if path in paths:
            raise ValueError("Duplicate native dependency")
        paths.add(path)
        if row.get("modified") is not False or row.get("fully_loaded") is not True:
            raise NXToolError(
                "NX_SIM_REVISION_UNSAVED",
                "Prepared inputs require fully loaded, saved analysis dependencies",
                details={"path": str(path), "mutation_outcome": "not_started"},
            )
        current = fingerprint_file(path, maximum_bytes=maximum_bytes - consumed)
        files.append(current)
        consumed += current["bytes"]
    input_record = _input(workspace, input_path, min(64 * 1024 * 1024, maximum_bytes - consumed))
    return {
        "schema": 1,
        "dependencies": files,
        "input": input_record,
        "scope": "explicit saved dependencies and input bytes only",
        "dependency_completeness": "not_established",
        "solve_readiness": "not_established",
    }


def validate_prepared_input(workspace, prepared, documents, *, maximum_bytes=1_073_741_824):
    if prepared.get("schema") != 1:
        raise ValueError("Unsupported prepared input schema")
    revision = audit_saved_revision(
        workspace, prepared["dependencies"], documents, maximum_bytes=maximum_bytes
    )
    if not revision["revision_matches"]:
        raise NXToolError(
            "NX_SIM_REVISION_CHANGED",
            "Analysis dependencies differ from the prepared input; prepare a new run",
            details={"mutation_outcome": "not_started", "audit": revision},
        )
    consumed = sum(row["bytes"] for row in revision["files"])
    try:
        current = _input(
            workspace, prepared["input"]["path"], min(64 * 1024 * 1024, maximum_bytes - consumed)
        )
    except (OSError, ValueError) as error:
        raise NXToolError(
            "NX_SIM_INPUT_CHANGED",
            "Prepared input is missing, unreadable or invalid; inspect it and prepare a new run",
            details={"mutation_outcome": "not_started"},
        ) from error
    if current["sha256"] != prepared["input"]["sha256"]:
        raise NXToolError(
            "NX_SIM_INPUT_CHANGED",
            "Exported input bytes changed after preparation; prepare a new run",
            details={"mutation_outcome": "not_started"},
        )
    return {
        "revision": revision,
        "input": current,
        "prepared_inputs_match": True,
        "solve_readiness": "not_established",
    }
