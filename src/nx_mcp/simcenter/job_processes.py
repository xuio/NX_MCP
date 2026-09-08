"""Read live state for identities already recorded by a job observer."""

from nx_mcp.simcenter.process_identity import correlate_process, inspect_process


def observe_job_processes(job):
    evidence = job.get("process_binding_evidence")
    if evidence is None:
        evidence = job.get("record", {}).get("evidence", {})
    if not isinstance(evidence, dict):
        return {"state": "unbound", "reason": "invalid_binding_evidence", "processes": []}
    # Terminal fixture records retain the original identities separately from
    # the final missing-process observations. Never treat a bare PID as binding.
    rows = evidence.get("previous_processes", evidence.get("process_observations", []))
    if not isinstance(rows, list) or not rows or len(rows) > 32:
        return {
            "state": "unbound",
            "reason": "no_bounded_recorded_process_identities",
            "processes": [],
        }
    identities, seen = [], set()
    try:
        for row in rows:
            identity = row["identity"]
            # Validate the full reference before any process lookup.
            correlate_process(identity, {"pid": identity["pid"], "state": "missing"})
            if identity["pid"] in seen:
                raise ValueError("Duplicate process binding")
            seen.add(identity["pid"])
            identities.append(identity)
    except (ValueError, KeyError, TypeError):
        return {
            "state": "unbound",
            "reason": "incomplete_or_ambiguous_process_identity",
            "processes": [],
        }
    processes = []
    for identity in identities:
        observation = inspect_process(identity["pid"])
        processes.append(
            {
                "recorded_identity": identity,
                "observation": observation,
                "correlation": correlate_process(identity, observation),
            }
        )
    return {
        "state": "observed",
        "processes": processes,
        "job_state_changed": False,
        "binding_revision": job.get("process_binding_revision"),
        "solver_success": "not_established",
        "scope": "recorded identities only; does not discover children or prove original job binding",
    }
