"""Persistent solve identities and append-only state records.

A reservation is not a solver launch. Callers must persist launch_requested before
calling NX, and must never retry that launch merely because observation failed.
All paths pass Workspace validation. Interrupted or competing writes fail closed.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone

from nx_mcp.runtime import NXToolError

_LIMIT = 1024 * 1024
_TRANSITIONS = {
    "accepted": {"launch_requested", "cancelled", "failed"},
    "launch_requested": {
        "launch_returned",
        "launch_uncertain",
        "running",
        "solver_exited",
        "failed",
    },
    "launch_returned": {"running", "solver_exited", "failed"},
    "launch_uncertain": {"running", "solver_exited", "failed"},
    "running": {"solver_exited", "failed", "cancelled"},
    "solver_exited": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}


def _encode(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(data) > _LIMIT:
        raise ValueError("Job record exceeds 1 MiB limit")
    return data


def _write_once(path, value):
    data = _encode(value)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _read(path):
    with path.open("rb") as stream:
        raw = stream.read(_LIMIT + 1)
    if len(raw) > _LIMIT:
        raise ValueError("Job record exceeds size limit")
    return json.loads(raw)


class JobStore:
    """Single-job compare-and-append, safe across reconnects and competing writers.

    Each immutable revision is claimed with exclusive file creation. A crash
    during a write leaves an incomplete record: inspection returns unknown and
    further mutations are rejected. There is no automatic lock expiry, cleanup,
    launch replay or inference that a missing process completed successfully.
    This records caller observations; it does not discover processes or validate
    simulation physics. A terminal job remains reserved permanently.
    """

    def __init__(self, workspace, folder="simcenter-jobs"):
        self.workspace = workspace
        self.root = workspace.resolve(folder)

    def _directory(self, job_id):
        if not isinstance(job_id, str) or not re.fullmatch("[a-z0-9][a-z0-9_-]{0,79}", job_id):
            raise NXToolError(
                "NX_INVALID_ARGUMENT",
                "job_id must be 1..80 lowercase letters, digits, underscores or hyphens",
                details={"mutation_outcome": "not_started"},
            )
        return self.workspace.ensure_inside(self.root / job_id)

    def inspect(self, job_id):
        directory = self._directory(job_id)
        if not directory.exists():
            raise NXToolError("NX_SIM_JOB_NOT_FOUND", "No reserved job with this identity")
        try:
            request = _read(self.workspace.ensure_inside(directory / "request.json"))
            digest = hashlib.sha256(_encode(request["manifest"])).hexdigest()
            if (
                request.get("job_id") != job_id
                or request.get("schema") != 1
                or request.get("request_sha256") != digest
            ):
                raise ValueError("Invalid request identity")
            paths = sorted(directory.glob("state-*.json"))
            if not paths or len(paths) > 10000:
                raise ValueError("Missing or excessive state history")
            previous = None
            process_binding_evidence = None
            process_binding_revision = None
            for index, path in enumerate(paths):
                if path.name != f"state-{index:05d}.json":
                    raise ValueError("State sequence has a gap")
                row = _read(self.workspace.ensure_inside(path))
                if (
                    row.get("revision") != index
                    or row.get("job_id") != job_id
                    or row.get("request_sha256") != digest
                ):
                    raise ValueError("State identity mismatch")
                if previous is None:
                    if row.get("state") != "accepted" or row.get("previous_sha256") is not None:
                        raise ValueError("Invalid initial state")
                elif (
                    row.get("previous_sha256") != hashlib.sha256(_encode(previous)).hexdigest()
                    or row.get("state") not in _TRANSITIONS[previous["state"]]
                ):
                    raise ValueError("Invalid state chain")
                evidence = row.get("evidence", {})
                if isinstance(evidence, dict) and (
                    "previous_processes" in evidence or "process_observations" in evidence
                ):
                    # Keep an explicit replacement even if it is malformed; the
                    # observer must reject it, not silently revive older identities.
                    process_binding_evidence = {
                        key: evidence[key]
                        for key in ("previous_processes", "process_observations")
                        if key in evidence
                    }
                    process_binding_revision = index
                previous = row
            return {
                "job_id": job_id,
                "manifest": request["manifest"],
                "request_sha256": digest,
                "state": previous["state"],
                "revision": previous["revision"],
                "record": previous,
                "process_binding_evidence": process_binding_evidence,
                "process_binding_revision": process_binding_revision,
                "launch_retry_allowed": previous["state"] == "accepted",
                "numerical_convergence": "not_established",
                "results_validated": False,
            }
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return {
                "job_id": job_id,
                "state": "unknown",
                "revision": None,
                "launch_retry_allowed": False,
                "next_action": "Inspect retained job records and native solver state; do not relaunch or overwrite this identity",
                "numerical_convergence": "not_established",
                "results_validated": False,
            }

    def reserve(self, job_id, manifest):
        if not isinstance(manifest, dict) or not manifest:
            raise ValueError("A nonempty immutable configuration manifest is required")
        digest = hashlib.sha256(_encode(manifest)).hexdigest()
        directory = self._directory(job_id)
        self.workspace.ensure_inside(self.root).mkdir(parents=True, exist_ok=True)
        try:
            directory.mkdir()
        except FileExistsError:
            current = self.inspect(job_id)
            if current["state"] == "unknown":
                return {**current, "replayed": True}
            if current["request_sha256"] != digest:
                raise NXToolError(
                    "NX_SIM_JOB_CONFLICT",
                    "This job ID belongs to another configuration; inspect it before selecting a new ID",
                    details={"mutation_outcome": "not_started"},
                ) from None
            return {**current, "replayed": True}
        _write_once(
            self.workspace.ensure_inside(directory / "request.json"),
            {"schema": 1, "job_id": job_id, "manifest": manifest, "request_sha256": digest},
        )
        _write_once(
            self.workspace.ensure_inside(directory / "state-00000.json"),
            {
                "revision": 0,
                "job_id": job_id,
                "request_sha256": digest,
                "state": "accepted",
                "previous_sha256": None,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "evidence": {},
            },
        )
        return {**self.inspect(job_id), "replayed": False}

    def transition(self, job_id, *, expected_revision, state, evidence):
        if type(expected_revision) is not int or not 0 <= expected_revision < 9999:
            raise ValueError("expected_revision must be an integer in 0..9998")
        if not isinstance(evidence, dict) or not evidence:
            raise ValueError("An explicit observation or launch-intent record is required")
        _encode(evidence)
        current = self.inspect(job_id)
        if current["state"] == "unknown" or current["revision"] != expected_revision:
            raise NXToolError(
                "NX_SIM_JOB_REVISION_CONFLICT",
                "Reinspect this job; its revision is unknown or has changed",
                details={"mutation_outcome": "not_started"},
            )
        if state not in _TRANSITIONS[current["state"]]:
            raise NXToolError(
                "NX_SIM_JOB_TRANSITION",
                "Transition is not allowed; a launch or terminal job cannot be replayed",
                details={"mutation_outcome": "not_started"},
            )
        record = {
            "revision": expected_revision + 1,
            "job_id": job_id,
            "request_sha256": current["request_sha256"],
            "state": state,
            "previous_sha256": hashlib.sha256(_encode(current["record"])).hexdigest(),
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "evidence": evidence,
        }
        target = self.workspace.ensure_inside(
            self._directory(job_id) / f"state-{expected_revision + 1:05d}.json"
        )
        try:
            _write_once(target, record)
        except FileExistsError as exc:
            raise NXToolError(
                "NX_SIM_JOB_REVISION_CONFLICT",
                "Another writer claimed this revision; inspect the job",
                details={"mutation_outcome": "not_started"},
            ) from exc
        return self.inspect(job_id)
