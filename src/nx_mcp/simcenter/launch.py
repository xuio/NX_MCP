"""Invoke a native launch once after its durable intent has been committed."""

from nx_mcp.runtime import NXToolError


def launch_isolated(store, job_id, manifest, launch, *, output_directory):
    """Reserve immutable outputs before committing launch intent.

    The native caller must verify NX actually exports to this directory and
    perform session/licence/resource preflight. Claiming a directory does not
    redirect NX output, validate existing artifacts, or establish job completion.
    """
    from nx_mcp.simcenter.output_claims import claim_output

    if not isinstance(manifest, dict) or not manifest:
        raise ValueError("A nonempty immutable configuration manifest is required")
    import os

    directory = os.path.normcase(str(store.workspace.resolve(output_directory)))
    if (
        "isolated_output_directory" in manifest
        and manifest["isolated_output_directory"] != directory
    ):
        raise ValueError("Manifest output directory differs from the requested isolated directory")
    configuration = {**manifest, "isolated_output_directory": directory}
    current = store.reserve(job_id, configuration)
    if current["state"] != "accepted":
        return {**current, "replayed": True}
    claim = claim_output(store, job_id, directory)
    result = launch_once(store, job_id, configuration, launch)
    return {**result, "output_claim": claim}


def launch_once(store, job_id, manifest, launch):
    """The callback runs synchronously on its caller's NX thread.

    Its return means only that the API returned. It must launch asynchronously
    and perform its own native preflight. Neither return nor exception proves
    whether a solver process exists. Reconnects never replay an existing intent.
    Independent jobs still require model/output/session concurrency gating.
    """
    current = store.reserve(job_id, manifest)
    if current["state"] != "accepted":
        return {**current, "replayed": True}
    intent = store.transition(
        job_id,
        expected_revision=current["revision"],
        state="launch_requested",
        evidence={"intent": "invoke native asynchronous solve once"},
    )
    try:
        readback = launch()
    except Exception as error:
        try:
            store.transition(
                job_id,
                expected_revision=intent["revision"],
                state="launch_uncertain",
                evidence={
                    "api_exception": True,
                    "nx_code": getattr(error, "ErrorCode", None),
                    "process_state": "unknown",
                },
            )
        except Exception as persistence_error:
            raise NXToolError(
                "NX_SIM_LAUNCH_UNCERTAIN",
                "Native launch raised and its observation could not be persisted; inspect the reserved job, never replay it",
                details={
                    "job_id": job_id,
                    "mutation_outcome": "unknown",
                    "observation_persisted": False,
                },
            ) from persistence_error
        raise NXToolError(
            "NX_SIM_LAUNCH_UNCERTAIN",
            "Native launch raised; a solver may still have started. Inspect this job before recovery",
            nx_code=getattr(error, "ErrorCode", None),
            details={
                "job_id": job_id,
                "mutation_outcome": "unknown",
                "observation_persisted": True,
            },
        ) from error
    try:
        result = store.transition(
            job_id,
            expected_revision=intent["revision"],
            state="launch_returned",
            evidence={
                "api_returned": True,
                "readback": readback,
                "process_state": "not_yet_observed",
            },
        )
    except Exception as persistence_error:
        # The launch intent is already durable. A missing or torn observation
        # cannot justify invoking NX a second time, even when the API returned.
        raise NXToolError(
            "NX_SIM_LAUNCH_UNCERTAIN",
            "Native launch returned but its observation could not be persisted; inspect the reserved job, never replay the launch",
            details={
                "job_id": job_id,
                "mutation_outcome": "unknown",
                "api_returned": True,
                "observation_persisted": False,
            },
        ) from persistence_error
    return {**result, "replayed": False}
