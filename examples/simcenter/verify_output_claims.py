"""Verify output exclusion on the NX host; no solver or CAD mutation."""


def run(executor):
    import importlib

    import nx_mcp.simcenter.jobs as jobs
    import nx_mcp.simcenter.output_claims as claims

    importlib.reload(jobs)
    importlib.reload(claims)
    root = "ui-benchmarks/F-output-claims-20260908-r1"
    first = jobs.JobStore(executor.workspace, root + "/ledger-a")
    second = jobs.JobStore(executor.workspace, root + "/ledger-b")
    manifest = {"fixture": "output-ownership-only", "solver_launch_permitted": False}
    first.reserve("owner", manifest)
    second.reserve("owner", manifest)
    output = root + "/isolated-output"
    owned = claims.claim_output(first, "owner", output)
    replay = claims.claim_output(first, "owner", output)
    windows_alias = claims.claim_output(first, "owner", output.upper())
    if not replay["replayed"] or not windows_alias["replayed"]:
        raise ValueError("Repeated/case-alias ownership was not recognized")
    try:
        claims.claim_output(second, "owner", output)
    except jobs.NXToolError as error:
        if error.code != "NX_SIM_OUTPUT_CONFLICT":
            raise
        conflict = error.code
    else:
        raise ValueError("Another job store incorrectly acquired these outputs")
    incomplete = executor.workspace.resolve(root + "/interrupted-output")
    incomplete.mkdir(parents=True, exist_ok=True)
    record = incomplete / ".nx-sim-output-owner.json"
    if not record.exists():
        with record.open("x") as stream:
            stream.write("{")
    try:
        claims.claim_output(first, "owner", str(incomplete))
    except jobs.NXToolError as error:
        if error.code != "NX_SIM_OUTPUT_UNCERTAIN":
            raise
        interrupted = error.code
    else:
        raise ValueError("Incomplete ownership was overwritten")
    if record.read_text() != "{":
        raise ValueError("Interrupted record changed")
    return {
        "owner": owned,
        "reconnect": replay,
        "windows_case_alias": windows_alias,
        "cross_store_conflict": conflict,
        "interrupted_record": interrupted,
        "application": executor.session.ApplicationName,
        "display_document": executor.session.Parts.BaseDisplay.FullPath,
        "solver_launched": False,
        "scope": "Windows output ownership only; not solve/cancellation acceptance",
    }
