"""Saved-revision audit for an explicitly enumerated analysis dependency set.

No manifest created after a solve can retroactively prove its input identity.
Callers retain pre-solve snapshots, enumerate dependencies and bind solver jobs.
"""

import re

from nx_mcp.simcenter.result_identity import fingerprint_file


def audit_saved_revision(workspace, expected_files, documents, *, maximum_bytes=1_073_741_824):
    """Compare pre-solve hashes with disk and live modification flags.

    `documents` contains native readbacks: path, modified, and fully_loaded.
    Refuses ambiguous/duplicate paths and incomplete snapshots. This is a narrow
    audit of the supplied set, not a claim that dependency enumeration is complete.
    It never saves edits or automatically accepts native results.
    """
    if type(maximum_bytes) is not int or maximum_bytes < 1:
        raise ValueError("maximum_bytes must be a positive integer")
    if not expected_files or not documents:
        raise ValueError("A nonempty pre-solve snapshot and native document inventory are required")
    expected = {}
    for row in expected_files:
        path = workspace.resolve(row["path"])
        if path in expected:
            raise ValueError("Duplicate snapshot dependency")
        if not isinstance(row.get("sha256"), str) or not re.fullmatch(
            "[0-9a-f]{64}", row["sha256"]
        ):
            raise ValueError("Snapshot needs a SHA256 for every dependency")
        expected[path] = row["sha256"]
    live = {}
    for row in documents:
        path = workspace.resolve(row["path"])
        if path in live:
            raise ValueError("Duplicate native document dependency")
        if type(row.get("modified")) is not bool or type(row.get("fully_loaded")) is not bool:
            raise ValueError("Native modification and load flags must be explicit booleans")
        live[path] = row
    if expected.keys() != live.keys():
        return {
            "state": "dependency_set_changed",
            "revision_matches": False,
            "added": sorted(str(p) for p in live.keys() - expected.keys()),
            "missing": sorted(str(p) for p in expected.keys() - live.keys()),
            "scope": "supplied dependency set only",
        }
    files, issues, consumed = [], [], 0
    for path, digest in expected.items():
        if live[path]["modified"]:
            issues.append({"path": str(path), "reason": "unsaved_edits"})
        if not live[path]["fully_loaded"]:
            issues.append({"path": str(path), "reason": "not_fully_loaded"})
        try:
            current = fingerprint_file(path, maximum_bytes=maximum_bytes - consumed)
        except FileNotFoundError:
            issues.append({"path": str(path), "reason": "missing_file"})
            continue
        consumed += current["bytes"]
        matches = current["sha256"] == digest
        files.append({**current, "expected_sha256": digest, "matches": matches})
        if not matches:
            issues.append({"path": str(path), "reason": "saved_file_changed"})
    return {
        "state": "revision_mismatch" if issues else "supplied_revision_matches",
        "revision_matches": not issues,
        "files": files,
        "issues": issues,
        "scope": "supplied dependency set only",
        "engineering_accepted": False,
    }
