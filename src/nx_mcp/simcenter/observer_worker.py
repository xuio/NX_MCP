"""Bounded observer worker: no NXOpen calls, solver launch or cancellation."""

import json
import os
import threading
import time
from contextlib import suppress
from datetime import datetime, timezone
from uuid import uuid4

from nx_mcp.simcenter.job_observer import observe_terminal
from nx_mcp.simcenter.jobs import JobStore

_PENDING = {"launch_requested", "launch_returned", "launch_uncertain", "running"}


def _run(workspace, job_id, job_folder, path, maximum_seconds, presentation=None):
    deadline = time.monotonic() + maximum_seconds
    written = 0

    def record(value):
        nonlocal written
        timestamp = datetime.now(timezone.utc).isoformat()
        if presentation is not None:
            # Replace one immutable snapshot; UI thread performs no solver/file I/O.
            presentation["snapshot"] = {
                **presentation.get("snapshot", {}),
                **value,
                "observed_at": timestamp,
            }
        raw = (json.dumps({"observed_at": timestamp, **value}, allow_nan=False) + "\n").encode()
        if written + len(raw) > 65536:
            return
        with path.open("ab") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        written += len(raw)

    try:
        record({"worker": "started", "job_id": job_id, "maximum_seconds": maximum_seconds})
        previous = None
        while True:
            result = observe_terminal(workspace, job_id, job_folder)
            # The durable job record carries full evidence; keep worker logs compact.
            status = {k: v for k, v in result.items() if k != "evidence"}
            if status != previous:
                record({"worker": "observing", **status})
                previous = status
            if result["state"] not in _PENDING:
                record({"worker": "finished", "job_state": result["state"]})
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                record(
                    {
                        "worker": "observation_timeout",
                        "job_state_changed": False,
                        "solver_cancelled": False,
                    }
                )
                return
            time.sleep(min(5, remaining))
    except Exception as error:
        # Do not echo arbitrary exception messages, environment or licence details.
        with suppress(OSError):
            record(
                {
                    "worker": "failed",
                    "error_type": type(error).__name__,
                    "error_code": getattr(error, "code", None),
                    "solver_relaunch_allowed": False,
                }
            )


def ensure_observer(registry, workspace, job_id, job_folder="simcenter-jobs", maximum_seconds=3600):
    """Called on the serialized NX thread; the worker receives filesystem state only."""
    if type(maximum_seconds) is not int or not 1 <= maximum_seconds <= 86400:
        raise ValueError("maximum_seconds must be 1..86400")
    store = JobStore(workspace, job_folder)
    current = store.inspect(job_id)
    key = os.path.normcase(str(store._directory(job_id)))
    existing = registry.get(key)
    if existing is not None and existing["thread"].is_alive():
        return {
            "state": "observing",
            "reused": True,
            "log_path": str(existing["path"]),
            "nx_api_calls": False,
            "maximum_seconds": existing.get("maximum_seconds", 3600),
            "deadline_restarted": False,
            "timeout_semantics": "maximum_seconds applies only when starting a new worker",
        }
    if current["state"] not in _PENDING:
        return {"state": "not_needed", "job_state": current["state"]}
    for old_key in list(registry):
        if not registry[old_key]["thread"].is_alive():
            del registry[old_key]
    if len(registry) >= 32:
        return {
            "state": "not_started",
            "reason": "observer_worker_limit",
            "solver_relaunch_allowed": False,
        }
    path = workspace.resolve(store._directory(job_id) / ("observer-" + uuid4().hex + ".log"))
    presentation = {}
    thread = threading.Thread(
        target=_run,
        args=(workspace, job_id, job_folder, path, maximum_seconds, presentation),
        name="nx-sim-observer-" + job_id,
        daemon=True,
    )
    registry[key] = {
        "thread": thread,
        "path": path,
        "maximum_seconds": maximum_seconds,
        "presentation": presentation,
    }
    try:
        thread.start()
    except Exception as error:
        del registry[key]
        return {
            "state": "not_started",
            "error_type": type(error).__name__,
            "solver_relaunch_allowed": False,
        }
    return {
        "state": "started",
        "reused": False,
        "log_path": str(path),
        "maximum_seconds": maximum_seconds,
        "nx_api_calls": False,
        "lifetime": "NX process; durable job survives observer exit",
        "timeout_semantics": "observation ends; solver is not cancelled or relaunched",
    }
