"""Explicit administrative gate recovery; never a successful-solve observation.

The operator supplies previously verified runtime/solver associations. We cannot
reconstruct that historical association from absent processes. Both identities
must now be missing or demonstrably exited; running/reused/unknown PIDs fail.
This command changes only the launch gate and its immutable release receipt.
"""

import json
import re

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.jobs import _read, _write_once
from nx_mcp.simcenter.launch_gate import _gate_lock
from nx_mcp.simcenter.log_reader import owned_output, valid_log_name
from nx_mcp.simcenter.process_identity import correlate_process, inspect_process
from nx_mcp.simcenter.result_identity import fingerprint_file
from nx_mcp.simcenter.solver_guard import require_solver_idle
from nx_mcp.simcenter.validation_limits import MAX_INPUT_BYTES


def recover_stopped_job(store, job_id, recovery):
    required = {"request_sha256", "revision", "input_sha256", "log_name", "log_sha256",
                "runtime_identity", "solver_identity", "reason", "association_attestation"}
    if not isinstance(recovery, dict) or set(recovery) != required:
        raise NXToolError("NX_INVALID_ARGUMENT", "Supply the exact recovery fields")
    if (type(recovery["revision"]) is not int or recovery["revision"] < 1
            or not valid_log_name(recovery["log_name"])
            or not isinstance(recovery["reason"], str) or not 10 <= len(recovery["reason"]) <= 1000
            or recovery["association_attestation"] != "operator_verified_job_runtime_and_solver"):
        raise NXToolError("NX_INVALID_ARGUMENT", "Invalid stopped-job recovery attestation")
    for key in ("request_sha256", "input_sha256", "log_sha256"):
        if not isinstance(recovery[key], str) or not re.fullmatch(r"[a-f0-9]{64}", recovery[key]):
            raise NXToolError("NX_INVALID_ARGUMENT", "Supply lowercase SHA256 values")
    for key in ("runtime_identity", "solver_identity"):
        try:
            correlate_process(recovery[key], {})  # validates the complete historical identity
        except (ValueError, TypeError) as exc:
            raise NXToolError("NX_INVALID_ARGUMENT", "Complete process identities required") from exc
    if recovery["runtime_identity"]["pid"] == recovery["solver_identity"]["pid"]:
        raise NXToolError("NX_INVALID_ARGUMENT", "Runtime and solver must be distinct")

    with _gate_lock(store.workspace):
        current, directory = owned_output(store, job_id)
        owner = {"schema": 1, "job_directory": str(store._directory(job_id)),
                 "job_id": job_id, "request_sha256": current["request_sha256"]}
        gate = store.workspace.resolve(".nx-sim-launch-owner.json")
        receipt_path = store.workspace.resolve(store._directory(job_id) / "launch-gate-release.json")
        actual_owner = _read(gate) if gate.exists() else None
        prior = _read(receipt_path) if receipt_path.exists() else None
        if prior is not None:
            if prior.get("owner") != owner or prior.get("recovery") != recovery or prior.get("schema") != 1:
                raise NXToolError("NX_SIM_LAUNCH_GATE_UNKNOWN", "Different release receipt; retain gate")
            if actual_owner != owner:
                return {"released": True, "replayed": True, "other_gate_untouched": actual_owner is not None}
        if actual_owner != owner:
            raise NXToolError("NX_SIM_LAUNCH_GATE_BUSY", "Job does not own this gate")
        if (current["request_sha256"] != recovery["request_sha256"]
                or current["revision"] != recovery["revision"] or current["state"] != "launch_returned"):
            raise NXToolError("NX_SIM_RECOVERY_CONFLICT", "Inspected job identity/state changed")

        def verify():
            require_solver_idle()
            processes = {}
            for role in ("runtime_identity", "solver_identity"):
                expected = recovery[role]
                observed = inspect_process(expected["pid"])
                matched = correlate_process(expected, observed)
                if matched["state"] not in ("original_process_not_present", "same_process_exited"):
                    raise NXToolError("NX_SIM_TERMINAL_UNVERIFIED", "Original process absence/exit unverified",
                                      details={"role": role, "observation": observed, "correlation": matched})
                processes[role] = {"observation": observed, "correlation": matched}
            deck = store.workspace.resolve(current["manifest"]["prepared_input"]["input"]["path"])
            log = store.workspace.resolve(directory / recovery["log_name"])
            if deck.parent != directory or log.parent != directory:
                raise NXToolError("NX_SIM_OUTPUT_CONFLICT", "Artifact escapes owned output directory")
            artifacts = {}
            for key, path, limit in (("input", deck, MAX_INPUT_BYTES), ("log", log, 8*1024*1024)):
                value = fingerprint_file(path, maximum_bytes=limit)
                if value["sha256"] != recovery[key+"_sha256"]:
                    raise NXToolError("NX_SIM_TERMINAL_CHANGED", "Inspected artifact changed")
                artifacts[key] = value
            return processes, artifacts

        processes, artifacts = verify()
        receipt = {"schema": 1, "owner": owner, "recovery": recovery,
                   "action": "administratively release explicitly stopped job gate only",
                   "process_checks": processes, "artifacts": artifacts,
                   "historical_process_binding": "operator_attested; not independently reconstructed",
                   "numerical_acceptance": "not_established", "job_state_changed": False}
        # Verify again before recording release intent. Any intervening activity
        # fails closed; this is not protection against unrelated manual launches.
        _, second = verify()
        if any(second[k]["sha256"] != artifacts[k]["sha256"] for k in artifacts):
            raise NXToolError("NX_SIM_TERMINAL_CHANGED", "Artifacts changed during recovery")
        if prior is None:
            _write_once(receipt_path, receipt)
        if _read(gate) != owner:
            raise NXToolError("NX_SIM_LAUNCH_GATE_BUSY", "Gate changed; release receipt retained")
        gate.unlink()
        return {"released": True, "replayed": prior is not None, "receipt": str(receipt_path),
                "result_files_preserved": True, "job_state_changed": False,
                "old_job_relaunch_allowed": False, "numerical_acceptance": "not_established"}


def main():
    import argparse

    from nx_mcp.simcenter.jobs import JobStore
    from nx_mcp.workspace import Workspace
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request")
    args = parser.parse_args()
    from pathlib import Path
    raw = Path(args.request).read_bytes()
    if len(raw) > 16384:
        raise ValueError("Recovery request exceeds 16 KiB")
    data = json.loads(raw)
    store = JobStore(Workspace(data["workspace"]), data.get("job_folder", "simcenter-jobs"))
    print(json.dumps(recover_stopped_job(store, data["job_id"], data["recovery"])))


if __name__ == "__main__":
    main()
