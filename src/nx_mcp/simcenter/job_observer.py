"""Observe terminal solver artifacts independently of the NX UI thread.

This does not launch, cancel, release a gate, or certify numerical results.
Unknown/missing evidence retains the existing job state indefinitely.
"""

from datetime import datetime

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.jobs import JobStore, _read
from nx_mcp.simcenter.log_reader import owned_output
from nx_mcp.simcenter.result_identity import fingerprint_file
from nx_mcp.simcenter.solver_guard import require_solver_idle
from nx_mcp.simcenter.solver_log import inspect_solver_log
from nx_mcp.simcenter.solver_manifest import compare_inputs


def observe_terminal(workspace, job_id, job_folder="simcenter-jobs"):
    store = JobStore(workspace, job_folder)
    current, directory = owned_output(store, job_id)
    state = current["state"]
    if state not in ("launch_returned", "launch_uncertain", "running"):
        return {
            "job_id": job_id,
            "state": state,
            "job_state_changed": False,
            "reason": "no_pending_launch_observation",
        }
    manifest = current["manifest"]
    if manifest.get("preparation_adapter") != 1:
        raise NXToolError("NX_SIM_JOB_CONFLICT", "Terminal observer requires a prepared native job")
    # Intent is always revision 1 in this preparation/launch adapter.
    intent = _read(store._directory(job_id) / "state-00001.json")
    if (
        intent["state"] != "launch_requested"
        or intent["request_sha256"] != current["request_sha256"]
    ):
        raise NXToolError("NX_SIM_JOB_CONFLICT", "Cannot establish the original launch intent")
    launched_at = datetime.fromisoformat(intent["observed_at"]).timestamp()
    deck = workspace.resolve(manifest["prepared_input"]["input"]["path"])
    if deck.parent != directory or deck.suffix.lower() != ".xml":
        raise NXToolError(
            "NX_SIM_OUTPUT_CONFLICT", "Prepared input is outside the owned output directory"
        )
    log, result = [workspace.resolve(deck.with_suffix(suffix)) for suffix in (".log", ".bun")]
    if any(not p.is_file() or p.stat().st_mtime <= launched_at for p in (log, result)):
        return {
            "job_id": job_id,
            "state": state,
            "job_state_changed": False,
            "reason": "terminal_outputs_missing_or_predate_launch",
        }
    with log.open("rb") as stream:
        raw_log = stream.read(8 * 1024 * 1024 + 1)
    if len(raw_log) > 8 * 1024 * 1024:
        raise NXToolError("NX_SIM_LOG_TOO_LARGE", "Terminal audit log exceeds 8 MiB")
    text = raw_log.decode("utf-8", errors="replace").replace("\r", "")
    footer = "\n Solve completed at:\n"
    if (
        text.count(footer) != 1
        or footer not in text[-2048:]
        or inspect_solver_log(text)["state"] == "failed"
    ):
        return {
            "job_id": job_id,
            "state": state,
            "job_state_changed": False,
            "reason": "unverified_terminal_footer",
        }
    try:
        idle = require_solver_idle()
    except NXToolError as error:
        if error.code in ("NX_SIM_SOLVER_BUSY", "NX_SIM_SOLVER_STATE_UNKNOWN"):
            return {
                "job_id": job_id,
                "state": state,
                "job_state_changed": False,
                "reason": error.code,
            }
        raise
    before_path = workspace.resolve(store._directory(job_id) / "before-launch.xml")
    with before_path.open("rb") as stream:
        before = stream.read(64 * 1024 * 1024 + 1)
    with deck.open("rb") as stream:
        after = stream.read(64 * 1024 * 1024 + 1)
    comparison = compare_inputs(before, after)
    if (
        comparison["before"]["sha256"] != manifest["prepared_input"]["input"]["sha256"]
        or not comparison["xml_content_identical"]
    ):
        raise NXToolError(
            "NX_SIM_INPUT_CHANGED",
            "Solver input differs from preparation; retain job and gate for investigation",
        )
    artifact = fingerprint_file(result, maximum_bytes=1024 * 1024 * 1024)
    if artifact["bytes"] == 0:
        raise NXToolError(
            "NX_SIM_RESULT_EMPTY", "Native result is empty; retain job for investigation"
        )
    import hashlib

    evidence = {
        "observer_adapter": 1,
        "terminal_basis": "fresh owned completion log and native result, matching canonical input, known solver processes absent",
        "process_exit_code": None,
        "process_job_binding": "not_established",
        "solver_process_observation": idle,
        "input_comparison": comparison,
        "log": {
            "path": str(log),
            "sha256": hashlib.sha256(raw_log).hexdigest(),
            "bytes": len(raw_log),
        },
        "result": artifact,
        "numerical_convergence": "not_established",
        "model_result_freshness": "not_established",
        "gate_released": False,
    }
    observed = store.transition(
        job_id, expected_revision=current["revision"], state="solver_exited", evidence=evidence
    )
    return {
        "job_id": job_id,
        "state": observed["state"],
        "revision": observed["revision"],
        "job_state_changed": True,
        "evidence": evidence,
    }


def main():
    import argparse
    import json
    import time

    from nx_mcp.workspace import Workspace

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--job-folder", default="simcenter-jobs")
    parser.add_argument("--maximum-seconds", type=int, default=300)
    parser.add_argument("--interval-seconds", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.maximum_seconds <= 86400 or not 1 <= args.interval_seconds <= 60:
        parser.error("maximum-seconds: 1..86400; interval-seconds: 1..60")
    workspace = Workspace(args.workspace)
    deadline = time.monotonic() + args.maximum_seconds
    while True:
        result = observe_terminal(workspace, args.job_id, args.job_folder)
        print(json.dumps(result), flush=True)
        if result["state"] in ("solver_exited", "completed", "failed", "cancelled", "unknown"):
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(
                json.dumps(
                    {
                        "observer": "observation_timeout",
                        "job_id": args.job_id,
                        "job_state_changed": False,
                        "relaunch_allowed": False,
                    }
                ),
                flush=True,
            )
            return
        time.sleep(min(args.interval_seconds, remaining))


if __name__ == "__main__":
    main()
