"""Refresh an incomplete completion footer without accepting solver results.

Explicit administrative CLI; retains original immutable history and launch gate.
Only a strict suffix completing the native timestamp is eligible. Arbitrary log
appends, changed inputs/results and active solvers require investigation.
"""
import copy
import hashlib
import re
from datetime import datetime

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.jobs import _read
from nx_mcp.simcenter.launch_gate import _gate_lock
from nx_mcp.simcenter.log_reader import owned_output
from nx_mcp.simcenter.result_identity import fingerprint_file
from nx_mcp.simcenter.solver_guard import require_solver_idle


def refresh_terminal_log(store, job_id, *, expected_revision, expected_log_sha256):
    if type(expected_revision) is not int or not 1 <= expected_revision < 9999:
        raise ValueError("Expected revision must be in 1..9998")
    if not isinstance(expected_log_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_log_sha256):
        raise ValueError("Supply the inspected current log SHA256")
    with _gate_lock(store.workspace):
        current, directory = owned_output(store, job_id)
        prior = current.get("record", {}).get("evidence", {})
        if (current["state"] != "solver_exited" or current["revision"] != expected_revision
                or prior.get("observer_adapter") != 1 or prior.get("result") is None):
            raise NXToolError("NX_SIM_RECOVERY_CONFLICT", "Reinspect terminal state and native result")
        owner = {"schema": 1, "job_directory": str(store._directory(job_id)),
                 "job_id": job_id, "request_sha256": current["request_sha256"]}
        gate = store.workspace.resolve(".nx-sim-launch-owner.json")
        release = store.workspace.resolve(store._directory(job_id) / "launch-gate-release.json")
        if not gate.exists() or _read(gate) != owner or release.exists():
            raise NXToolError("NX_SIM_LAUNCH_GATE_BUSY", "Unreleased matching gate required")
        deck = store.workspace.resolve(current["manifest"]["prepared_input"]["input"]["path"])
        log = store.workspace.resolve(prior["log"]["path"])
        result = store.workspace.resolve(prior["result"]["path"])
        if (deck.parent != directory or log != deck.with_suffix(".log")
                or result != deck.with_suffix(".bun")):
            raise NXToolError("NX_SIM_OUTPUT_CONFLICT", "Artifacts must belong to the prepared input")

        def snapshot():
            idle = require_solver_idle()
            files = {"log": fingerprint_file(log, maximum_bytes=8*1024*1024),
                     "input": fingerprint_file(deck, maximum_bytes=64*1024*1024),
                     "result": fingerprint_file(result, maximum_bytes=1024*1024*1024)}
            for name, expected in (("input", prior["input_comparison"]["after"]),
                                   ("result", prior["result"])):
                if any(files[name][k] != expected[k] for k in ("bytes", "sha256")):
                    raise NXToolError("NX_SIM_TERMINAL_CHANGED", "Input or result changed")
            if files["log"]["sha256"] != expected_log_sha256:
                raise NXToolError("NX_SIM_TERMINAL_CHANGED", "Log differs from inspected hash")
            return idle, files

        _, first = snapshot()
        with log.open("rb") as stream:
            raw = stream.read(8*1024*1024+1)
        if hashlib.sha256(raw).hexdigest() != first["log"]["sha256"]:
            raise NXToolError("NX_SIM_TERMINAL_CHANGED", "Log changed during read")
        old = prior["log"]
        if not 0 < len(raw)-old["bytes"] <= 2048 or hashlib.sha256(raw[:old["bytes"]]).hexdigest() != old["sha256"]:
            raise NXToolError("NX_SIM_TERMINAL_CHANGED", "Original log must be an exact strict prefix")
        # The observed prefix must already contain the last footer header;
        # everything after that header must be only its completed timestamp.
        header = b"\n Solve completed at:\n"
        normalized = raw.replace(b"\r", b"")
        prefix = raw[:old["bytes"]].replace(b"\r", b"")
        if normalized.count(header) != 1 or header not in prefix:
            raise NXToolError("NX_SIM_TERMINAL_CHANGED", "Expected one existing completion footer")
        footer = normalized.split(header)[1]
        match = re.fullmatch(rb" =+\n Time: ([A-Za-z]{3} [A-Za-z]{3} +\d{1,2} \d{2}:\d{2}:\d{2} \d{4})\n\n", footer)
        if match is None:
            raise NXToolError("NX_SIM_TERMINAL_CHANGED", "Append is not a native completion timestamp")
        try:
            datetime.strptime(match[1].decode("ascii"), "%a %b %d %H:%M:%S %Y")
        except ValueError as exc:
            raise NXToolError("NX_SIM_TERMINAL_CHANGED", "Invalid completion timestamp") from exc
        idle, second = snapshot()
        if first != second or _read(gate) != owner or release.exists():
            raise NXToolError("NX_SIM_TERMINAL_CHANGED", "Artifacts or gate changed during refresh")
        evidence = copy.deepcopy(prior)
        evidence.update(log=second["log"], solver_process_observation=idle,
                        numerical_convergence="not_established", results_validated=False,
                        model_result_freshness="not_established", gate_released=False)
        evidence["terminal_log_refresh"] = {
            "previous_revision": current["revision"], "previous_log": old,
            "appended_bytes": len(raw)-old["bytes"], "exact_prefix_verified": True,
            "scope": "completion timestamp only; unchanged executed input and native result",
        }
        refreshed = store.transition(job_id, expected_revision=expected_revision,
                                     state="solver_exited", evidence=evidence)
        return {"job_id": job_id, "state": refreshed["state"], "revision": refreshed["revision"],
                "refreshed": True, "gate_released": False, "results_validated": False,
                "evidence": evidence}


def main():
    import argparse
    import json

    from nx_mcp.simcenter.jobs import JobStore
    from nx_mcp.workspace import Workspace
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True)
    p.add_argument("--job-id", required=True)
    p.add_argument("--job-folder", default="simcenter-jobs")
    p.add_argument("--expected-revision", required=True, type=int)
    p.add_argument("--expected-log-sha256", required=True)
    a = p.parse_args()
    print(json.dumps(refresh_terminal_log(JobStore(Workspace(a.workspace), a.job_folder),
        a.job_id, expected_revision=a.expected_revision, expected_log_sha256=a.expected_log_sha256)))


if __name__ == "__main__":
    main()
