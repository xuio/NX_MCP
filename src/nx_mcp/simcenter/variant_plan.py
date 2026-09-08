"""Bounded saved-analysis clone preflight; never creates, loads or saves files."""

import hashlib
import json
import re
from pathlib import Path

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.result_identity import fingerprint_file


def plan_variant(
    workspace,
    dependencies,
    *,
    folder,
    name,
    loaded_paths=(),
    saved_snapshot=False,
    maximum_bytes=1_073_741_824,
):
    def reject(code, message, **details):
        raise NXToolError(code, message, details={"mutation_outcome": "not_started", **details})

    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,47}", name):
        reject(
            "NX_INVALID_ARGUMENT",
            "Variant name must be 1..48 ASCII letters, digits or underscores, beginning with a letter",
        )
    if type(saved_snapshot) is not bool or type(maximum_bytes) is not int or maximum_bytes < 1:
        reject(
            "NX_INVALID_ARGUMENT",
            "saved_snapshot must be boolean and maximum_bytes a positive integer",
        )
    target = workspace.resolve(folder)
    if target == workspace.root or target.exists():
        reject(
            "NX_SIM_OUTPUT_CONFLICT",
            "Choose a new workspace folder; existing artifacts are never overwritten",
            folder=str(target),
        )
    rows = dependencies.get("rows", [])
    if dependencies.get("unresolved") or not 2 <= len(rows) <= 16:
        reject(
            "NX_SIM_DEPENDENCIES_INCOMPLETE",
            "Resolve all direct SIM/FEM/CAD dependencies before cloning",
            unresolved=dependencies.get("unresolved", []),
        )
    sim_rows = [row for row in rows if "simulation" in row["roles"]]
    fem_rows = [row for row in rows if "mesh" in row["roles"]]
    if len(sim_rows) != 1 or len(fem_rows) != 1:
        reject(
            "NX_SIM_UNSUPPORTED_DOCUMENT_TYPE",
            "Require one standalone SIM and FEM with explicit CAD associations",
        )
    unsaved = [row["path"] for row in rows if row["modified"]]
    if unsaved and not saved_snapshot:
        reject(
            "NX_SIM_UNSAVED_DOCUMENT",
            "Save approved edits explicitly or select saved_snapshot to copy only disk revisions",
            unsaved_sources=unsaved,
        )
    ordered = (
        sim_rows
        + fem_rows
        + sorted(
            [row for row in rows if row not in sim_rows + fem_rows],
            key=lambda row: row["path"].casefold(),
        )
    )
    loaded_stems = {Path(path).stem.casefold() for path in loaded_paths if path}
    mappings, seen, consumed = [], set(), 0
    for index, row in enumerate(ordered):
        path = workspace.resolve(row["path"])
        suffix = ".sim" if index == 0 else ".fem" if index == 1 else ".prt"
        if (
            str(path).casefold() in seen
            or path.suffix.casefold() != suffix
            or row["file_state"] != "exists"
            or not path.is_file()
            or not row["fully_loaded"]
        ):
            reject(
                "NX_SIM_DEPENDENCIES_INCOMPLETE",
                "Require distinct, fully loaded existing native dependencies with matching roles",
                path=str(path),
            )
        seen.add(str(path).casefold())
        stem = (
            f"{name}_analysis"
            if index == 0
            else f"{name}_mesh"
            if index == 1
            else f"{name}_cad_{index - 1:02d}"
        )
        if stem.casefold() in loaded_stems:
            reject(
                "NX_SIM_NAME_CONFLICT",
                "Generated basename is already loaded; choose a distinct variant name",
                basename=stem,
            )
        destination = workspace.resolve(target / (stem + suffix))
        try:
            identity = fingerprint_file(path, maximum_bytes=maximum_bytes - consumed)
        except (OSError, ValueError) as error:
            reject(
                "NX_SIM_SOURCE_SNAPSHOT_FAILED",
                "Could not establish a stable bounded source-file snapshot; inspect files or increase the byte limit",
                path=str(path),
                error_type=type(error).__name__,
            )
        consumed += identity["bytes"]
        mappings.append(
            {
                "source": identity,
                "destination": str(destination),
                "roles": row["roles"],
                "units": row["units"],
                "source_modified": row["modified"],
            }
        )
    result = {
        "schema": 1,
        "folder": str(target),
        "name": name,
        "saved_snapshot": saved_snapshot,
        "unsaved_sources_excluded": unsaved,
        "source_bytes": consumed,
        "mapping": mappings,
        "scope": "direct standalone SIM/FEM/CAD native files",
        "complete_analysis_package": False,
        "result_freshness": "not_verified",
    }
    result["plan_sha256"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return result
