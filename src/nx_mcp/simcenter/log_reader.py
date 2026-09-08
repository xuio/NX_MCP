"""Bounded, line-aligned solver log excerpts; not a convergence judgement."""

import re

from nx_mcp.runtime import NXToolError

_SENSITIVE = re.compile(
    r"licen[cs]e|password|passwd|secret|token|credential|hostid|\bsign2?\s*=|\b\d+@[^\s]+",
    re.IGNORECASE,
)


def read_log(workspace, path, *, offset=0, maximum_bytes=8192, file_identity=None):
    """Read complete lines without crossing a workspace boundary.

    Cursor offsets are raw byte positions. A caller must retain file_identity on
    subsequent reads to detect replacement. In-place rewrites are not fully
    detectable; excerpts do not establish immutable result identity.
    """
    if (
        type(offset) is not int
        or offset < 0
        or type(maximum_bytes) is not int
        or not 256 <= maximum_bytes <= 65536
    ):
        raise NXToolError("NX_INVALID_ARGUMENT", "offset >= 0; maximum_bytes 256..65536")
    target = workspace.resolve(path)
    if target.suffix.lower() != ".log":
        raise NXToolError("NX_INVALID_ARGUMENT", "Select a .log file")
    with target.open("rb") as stream:
        import os

        stat = os.fstat(stream.fileno())
        identity = f"{stat.st_dev}:{stat.st_ino}"
        if file_identity is not None and file_identity != identity:
            raise NXToolError("NX_SIM_LOG_CHANGED", "Log file was replaced; restart inspection")
        if offset > stat.st_size:
            raise NXToolError("NX_SIM_LOG_CHANGED", "Log shrank below the requested offset")
        if offset:
            stream.seek(offset - 1)
            if stream.read(1) != b"\n":
                raise NXToolError("NX_INVALID_ARGUMENT", "Offset must follow a newline")
        stream.seek(offset)
        raw = stream.read(maximum_bytes)
    # Hold a trailing incomplete line until the writer appends a newline.
    end = raw.rfind(b"\n") + 1
    if not end and len(raw) == maximum_bytes:
        raise NXToolError(
            "NX_SIM_LOG_LINE_TOO_LONG", "A complete log line exceeds this read budget"
        )
    selected = raw[:end]
    lines = selected.decode("utf-8", errors="replace").splitlines(keepends=True)
    redactions = sum(bool(_SENSITIVE.search(line)) for line in lines)
    text = "".join(
        "[sensitive diagnostic line omitted]\n" if _SENSITIVE.search(line) else line
        for line in lines
    )
    return {
        "path": str(target),
        "file_identity": identity,
        "offset": offset,
        "next_offset": offset + end,
        "observed_size_bytes": stat.st_size,
        "text": text,
        "redacted_line_count": redactions,
        "trailing_partial_line_held": end < len(raw),
        "more_bytes_at_snapshot": offset + end < stat.st_size,
        "encoding": "UTF-8 with replacement",
        "numerical_convergence": "not_established",
        "redaction_scope": "credential/licensing keyword lines; not a complete secret scanner",
    }


def owned_output(store, job_id):
    """Verify immutable job/output ownership without creating files."""
    import os

    from nx_mcp.simcenter.jobs import _read

    job = store.inspect(job_id)
    if job["state"] == "unknown":
        raise NXToolError(
            "NX_SIM_JOB_UNKNOWN", "Job history is unavailable; inspect retained records"
        )
    output = job["manifest"].get("isolated_output_directory")
    if not isinstance(output, str) or not output:
        raise NXToolError("NX_SIM_OUTPUT_UNBOUND", "Job has no isolated output directory")
    directory = store.workspace.resolve(output)
    if directory == store.workspace.root:
        raise NXToolError(
            "NX_SIM_OUTPUT_UNBOUND", "Job must own an isolated workspace subdirectory"
        )
    expected = {
        "schema": 1,
        "job_id": job_id,
        "job_directory": os.path.normcase(str(store._directory(job_id))),
        "request_sha256": job["request_sha256"],
        "output_directory": os.path.normcase(str(directory)),
    }
    try:
        owner = _read(store.workspace.ensure_inside(directory / ".nx-sim-output-owner.json"))
    except (OSError, ValueError):
        raise NXToolError(
            "NX_SIM_OUTPUT_UNBOUND", "Output ownership could not be verified"
        ) from None
    if owner != expected:
        raise NXToolError(
            "NX_SIM_OUTPUT_CONFLICT", "Output directory belongs to another job identity"
        )
    return job, directory


def valid_log_name(name):
    if not isinstance(name, str) or not re.fullmatch(
        r"[\w][\w. -]{0,199}\.log", name, re.ASCII | re.IGNORECASE
    ):
        return False
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(10)),
        *(f"LPT{i}" for i in range(10)),
    }
    return name.split(".")[0].upper() not in reserved


def read_job_log(store, job_id, log_name, *, offset=0, maximum_bytes=8192, file_identity=None):
    """Read a named log only after verifying permanent output ownership."""
    if not valid_log_name(log_name):
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Supply a non-device ASCII .log basename, not a path"
        )
    job, directory = owned_output(store, job_id)
    target = store.workspace.ensure_inside(directory / log_name)
    if target.parent != directory:
        raise NXToolError(
            "NX_SIM_OUTPUT_CONFLICT", "Log resolves outside the owned output directory"
        )
    try:
        result = read_log(
            store.workspace,
            str(target),
            offset=offset,
            maximum_bytes=maximum_bytes,
            file_identity=file_identity,
        )
    except OSError:
        raise NXToolError(
            "NX_SIM_LOG_UNAVAILABLE", "Log is missing or cannot be read; inspect job status"
        ) from None
    return {
        **result,
        "job_id": job_id,
        "request_sha256": job["request_sha256"],
        "persisted_job_state": job["state"],
        "job_state_changed": False,
    }


def list_job_logs(store, job_id, *, offset=0, limit=20):
    """Bounded live listing of direct log files in the verified owned directory."""
    import os

    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise NXToolError("NX_INVALID_ARGUMENT", "offset >= 0; limit 1..100")
    job, directory = owned_output(store, job_id)
    candidates = []
    with os.scandir(directory) as entries:
        for count, entry in enumerate(entries):
            if count >= 4096:
                raise NXToolError(
                    "NX_SIM_LOG_DIRECTORY_LIMIT", "Output directory exceeds 4096 entries"
                )
            if valid_log_name(entry.name) and entry.is_file(follow_symlinks=False):
                candidates.append(entry.name)
    candidates.sort(key=lambda name: (name.casefold(), name))
    rows = []
    for name in candidates[offset : offset + limit]:
        target = store.workspace.ensure_inside(directory / name)
        if target.parent != directory:
            raise NXToolError("NX_SIM_OUTPUT_CONFLICT", "Log resolves outside its owned directory")
        try:
            stat = target.stat()
        except OSError:
            raise NXToolError(
                "NX_SIM_LOG_CHANGED", "Log listing changed; refresh inventory"
            ) from None
        rows.append(
            {
                "log_name": name,
                "bytes": stat.st_size,
                "modified_ns": stat.st_mtime_ns,
                "file_identity": f"{stat.st_dev}:{stat.st_ino}",
            }
        )
    return {
        "job_id": job_id,
        "request_sha256": job["request_sha256"],
        "logs": rows,
        "total": len(candidates),
        "next_offset": offset + limit if offset + limit < len(candidates) else None,
        "scope": "Direct ASCII log files, excluding symlinks and device names",
        "consistency": "Live directory rescan; refresh if files change between pages",
        "job_state_changed": False,
    }
