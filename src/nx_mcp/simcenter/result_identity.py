"""Read native result associations without treating file identity as freshness."""

import hashlib
from pathlib import Path


def fingerprint_file(path, *, maximum_bytes):
    """Hash a validated path; reject an observation that overlaps a file change."""
    consumed = 0
    digest = hashlib.sha256()
    path_before = path.stat()
    with path.open("rb") as stream:
        import os

        before = os.fstat(stream.fileno())
        if before.st_size > maximum_bytes:
            raise ValueError("Result identity byte budget exceeded; increase it explicitly")
        while chunk := stream.read(1024 * 1024):
            consumed += len(chunk)
            if consumed > maximum_bytes:
                raise ValueError("Result identity byte budget exceeded while reading")
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    current = path.stat()

    def signature(value):
        return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns

    # Windows Python can report creation time for path.stat().st_ctime but
    # change time for fstat().st_ctime. Compare ctime only within each API.
    if (
        signature(before) != signature(after)
        or signature(path_before) != signature(current)
        or signature(after)[:4] != signature(current)[:4]
    ):
        raise ValueError("Result file changed during inspection; retry inspection after solve")
    return {"path": str(path), "bytes": after.st_size, "sha256": digest.hexdigest()}


def inspect_result_identity(solution, workspace, *, maximum_bytes=1_073_741_824):
    """Hash workspace-scoped result files and report NX's separate verification.

    Call on the NX thread. Never registers results, saves documents or changes
    associations. Native verification is reported, not engineering acceptance.
    The byte budget applies across all associated files; larger studies require
    an explicit increased budget. Unavailable verification remains unknown.
    """
    if type(maximum_bytes) is not int or maximum_bytes < 1:
        raise ValueError("maximum_bytes must be a positive integer")
    import NXOpen.CAE as cae

    if solution.ResultReferenceCount < 1:
        raise ValueError("No associated result files; inspect the solution and solver job")
    rows = []
    consumed = 0
    for index in range(solution.ResultReferenceCount):
        reference = solution.GetResultReferenceByIndex(index)
        directory, name = reference.GetResultFile()
        if not directory or not name:
            raise ValueError("Result association has no local file; inspect its storage mode")
        path = workspace.ensure_inside(Path(directory) / name)
        identity = fingerprint_file(path, maximum_bytes=maximum_bytes - consumed)
        consumed += identity["bytes"]
        rows.append({"index": index, **identity})
    try:
        value = solution.VerifyResults()
        statuses = {
            "VerificationSuccess": "native_verification_success",
            "ChecksumCalFailed": "checksum_failed",
            "ResultsChanged": "results_changed",
            "ResultsOutOfDate": "results_out_of_date",
        }
        status = next(
            (
                label
                for name, label in statuses.items()
                if value == getattr(cae.SimSolution.EnumVerifyResults, name)
            ),
            "unknown",
        )
        verification = {"state": status, "native_value": str(value)}
    except Exception as error:
        verification = {"state": "unavailable", "nx_code": getattr(error, "ErrorCode", None)}
    return {
        "files": rows,
        "native_verification": verification,
        "result_freshness": "not_verified",
        "engineering_accepted": False,
        "scope": "Associated file identity and native verification only; model/job revision binding required",
    }
