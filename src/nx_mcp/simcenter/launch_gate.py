"""Durable workspace exclusion during the native solver dispatch gap.

Known-process snapshots cannot exclude a second job before the first solver
appears. This claim has no timeout or automatic release; explicit, verified
terminal-job recovery is required before another job can acquire the workspace.
"""

import os
from contextlib import contextmanager

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.jobs import _read, _write_once


@contextmanager
def _gate_lock(workspace):
    # The guard inode remains in place permanently. Never unlink a lock file.
    path = workspace.resolve(".nx-sim-launch-guard")
    with path.open("a+b") as stream:
        if os.fstat(stream.fileno()).st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise NXToolError(
                "NX_SIM_LAUNCH_GATE_BUSY",
                "Another gate operation is in progress; inspect or retry this gate operation, not the solve",
            ) from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def claim_launch_gate(store, job_id):
    with _gate_lock(store.workspace):
        if store.workspace.resolve(store._directory(job_id) / "launch-gate-release.json").exists():
            raise NXToolError(
                "NX_SIM_GATE_ALREADY_RELEASED",
                "This job's launch gate was released; never relaunch the old job",
            )
        return _claim_launch_gate(store, job_id)


def _claim_launch_gate(store, job_id):
    current = store.inspect(job_id)
    if current["state"] == "unknown":
        raise NXToolError(
            "NX_SIM_LAUNCH_GATE_UNKNOWN", "Inspect incomplete job records before launching"
        )
    record = {
        "schema": 1,
        "job_directory": str(store._directory(job_id)),
        "job_id": job_id,
        "request_sha256": current["request_sha256"],
    }
    path = store.workspace.resolve(".nx-sim-launch-owner.json")
    try:
        _write_once(path, record)
    except FileExistsError:
        try:
            previous = _read(path)
        except (OSError, ValueError) as error:
            raise NXToolError(
                "NX_SIM_LAUNCH_GATE_UNKNOWN",
                "Retain and inspect the incomplete launch gate; do not retry a new launch",
            ) from error
        if previous != record:
            raise NXToolError(
                "NX_SIM_LAUNCH_GATE_BUSY",
                "Another job owns the workspace launch gate; inspect its terminal state before explicit recovery",
                details={
                    "mutation_outcome": "not_started",
                    "automatic_expiry": False,
                    "launch_gate": inspect_launch_gate(store.workspace),
                },
            ) from None
    return {**record, "automatic_release": False}


def release_launch_gate(store, job_id):
    from nx_mcp.simcenter.log_reader import owned_output
    from nx_mcp.simcenter.result_identity import fingerprint_file
    from nx_mcp.simcenter.solver_guard import require_solver_idle
    from nx_mcp.simcenter.solver_manifest import input_identity

    with _gate_lock(store.workspace):
        current, directory = owned_output(store, job_id)
        owner = {
            "schema": 1,
            "job_directory": str(store._directory(job_id)),
            "job_id": job_id,
            "request_sha256": current["request_sha256"],
        }
        path = store.workspace.resolve(".nx-sim-launch-owner.json")
        receipt_path = store.workspace.resolve(
            store._directory(job_id) / "launch-gate-release.json"
        )
        actual_owner = _read(path) if path.exists() else None
        if receipt_path.exists():
            receipt = _read(receipt_path)
            if receipt.get("owner") != owner or receipt.get("schema") != 1:
                raise NXToolError(
                    "NX_SIM_LAUNCH_GATE_UNKNOWN",
                    "Release receipt identity is invalid; retain gate for inspection",
                )
            if actual_owner != owner:
                return {
                    "job_id": job_id,
                    "released": True,
                    "replayed": True,
                    "receipt": str(receipt_path),
                    "other_gate_untouched": actual_owner is not None,
                }
        if actual_owner != owner:
            raise NXToolError(
                "NX_SIM_LAUNCH_GATE_BUSY",
                "This job does not own the launch gate; no ownership was changed",
            )
        evidence = current.get("record", {}).get("evidence", {})
        if current["state"] != "solver_exited" or evidence.get("observer_adapter") != 1:
            raise NXToolError(
                "NX_SIM_TERMINAL_UNVERIFIED",
                "A verified independent terminal observation is required before gate release",
            )
        checks = {}
        for kind, maximum in (("log", 8 * 1024 * 1024), ("result", 1024 * 1024 * 1024)):
            previous = evidence[kind]
            artifact_path = store.workspace.resolve(previous["path"])
            if artifact_path.parent != directory:
                raise NXToolError(
                    "NX_SIM_OUTPUT_CONFLICT",
                    "Terminal artifact is outside the owned output directory",
                )
            snapshot = fingerprint_file(artifact_path, maximum_bytes=maximum)
            if snapshot["sha256"] != previous["sha256"] or snapshot["bytes"] != previous["bytes"]:
                raise NXToolError(
                    "NX_SIM_TERMINAL_CHANGED",
                    "Terminal artifacts changed; retain gate and investigate",
                )
            checks[kind] = snapshot
        deck = store.workspace.resolve(current["manifest"]["prepared_input"]["input"]["path"])
        if deck.parent != directory:
            raise NXToolError(
                "NX_SIM_OUTPUT_CONFLICT", "Input is outside the owned output directory"
            )
        with deck.open("rb") as stream:
            data = stream.read(64 * 1024 * 1024 + 1)
        identity = input_identity(data)
        if (
            identity["xml_content_sha256"]
            != evidence["input_comparison"]["after"]["xml_content_sha256"]
        ):
            raise NXToolError(
                "NX_SIM_INPUT_CHANGED", "Input changed after terminal observation; retain gate"
            )
        require_solver_idle()
        receipt = {
            "schema": 1,
            "owner": owner,
            "observer_revision": current["revision"],
            "artifacts": checks,
            "input": identity,
            "action": "release workspace launch gate only",
            "numerical_acceptance": "not_established",
        }
        if receipt_path.exists():
            if _read(receipt_path) != receipt:
                raise NXToolError(
                    "NX_SIM_LAUNCH_GATE_UNKNOWN",
                    "Existing release intent differs; retain gate for inspection",
                )
        else:
            _write_once(receipt_path, receipt)
        # This deletes only bridge-owned synchronization metadata. Solver/CAD
        # files and the permanent output ownership record are never removed.
        path.unlink()
        return {
            "job_id": job_id,
            "released": True,
            "replayed": False,
            "receipt": str(receipt_path),
            "result_files_preserved": True,
            "job_state_changed": False,
            "old_job_relaunch_allowed": False,
        }


def inspect_launch_gate(workspace):
    """Read ownership without creating lock files, expiring claims or polling NX."""
    from nx_mcp.simcenter.jobs import JobStore

    path = workspace.resolve(".nx-sim-launch-owner.json")
    base = {
        "automatic_expiry": False,
        "solver_process_state": "not_checked",
        "launch_authorized_by_inspection": False,
    }
    try:
        owner = _read(path)
    except FileNotFoundError:
        return {
            **base,
            "state": "unclaimed",
            "note": "No persistent owner observed; this is not a solver-idle check or a launch reservation",
        }
    except (OSError, ValueError):
        return {
            **base,
            "state": "unknown",
            "reason": "owner_record_unreadable",
            "next_step": "Retain the gate and inspect its records; do not relaunch",
        }
    try:
        if not isinstance(owner, dict) or owner.get("schema") != 1:
            raise ValueError("owner_schema")
        directory = workspace.resolve(owner["job_directory"])
        store = JobStore(workspace, str(directory.parent))
        job_id = owner["job_id"]
        if store._directory(job_id) != directory:
            raise ValueError("owner_directory")
        job = store.inspect(job_id)
        if job["state"] == "unknown" or job["request_sha256"] != owner["request_sha256"]:
            raise ValueError("owner_job_identity")
        if _read(path) != owner:
            raise ValueError("owner_changed_during_inspection")
    except (OSError, ValueError, KeyError, TypeError, NXToolError):
        return {
            **base,
            "state": "unknown",
            "reason": "owner_job_identity_not_verified",
            "next_step": "Retain the gate and inspect job records; do not relaunch",
        }
    return {
        **base,
        "state": "claimed",
        "job_id": job_id,
        "job_folder": str(directory.parent),
        "request_sha256": job["request_sha256"],
        "recorded_job_state": job["state"],
        "recorded_job_revision": job["revision"],
        "next_step": "Inspect the owning job; use explicit release only after independently verified terminal evidence",
    }
