"""Prepare the isolated finned baseline; inspect the exported deck before launch."""


def run(executor):
    import json
    import shutil
    import time

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if "E-finned-baseline-20260908-r1" not in sim.FullPath:
        raise ValueError("Activate saved finned baseline")
    receipt = executor.workspace.resolve("ui-benchmarks/E-finned-prepare-r1.json")
    if receipt.exists():
        return {
            "replayed": True,
            "receipt": json.loads(receipt.read_text()),
            "solver_launched": False,
        }
    rows = {"solver_launched": False, "acceptance": False}

    def record(key, value):
        rows[key] = value
        receipt.write_text(json.dumps(rows, indent=2))

    record(
        "copy",
        executor._sim_save_as(
            executor._reference(sim, "part", sim, "SIM")["id"],
            "ui-benchmarks/E-finned-run-20260908-r1/finned_run_r1.sim",
        ),
    )
    started = time.monotonic()
    record(
        "prepare",
        executor._sim_prepare_solve(
            executor._reference(sim, "part", sim, "SIM")["id"], "coupled-finned-baseline-r1"
        ),
    )
    root = executor.workspace.resolve("ui-benchmarks/E-finned-run-20260908-r1")
    decks = list(root.glob("*.xml"))
    assert len(decks) == 1
    shutil.copyfile(decks[0], r"Z:\nx-mcp-integration\simcenter-discovery\finned-baseline-deck.xml")
    record("prepare_seconds", time.monotonic() - started)
    return rows
