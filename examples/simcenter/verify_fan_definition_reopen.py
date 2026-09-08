"""Save/reopen the isolated fan fixture and compare semantic boundary values."""


def run(executor):
    import importlib
    import json
    from pathlib import Path

    import NXOpen as nx

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    capture_boundary_state = importlib.reload(
        importlib.import_module("nx_mcp.simcenter.boundary_state")
    ).capture_boundary_state
    sim = executor.session.Parts.BaseWork
    path = Path(sim.FullPath)
    if path.name != "f1_fan_definition_r1.sim":
        raise ValueError("Requires the isolated fan definition fixture")
    receipt = path.parent / "reopen-verification-v4.json"
    if receipt.exists():
        raise ValueError("Inspect retained reopen evidence before retry")
    before = capture_boundary_state(sim, nx)
    assert before["comparison_verified"]
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts if p != sim}
    inlet = next(b for b in sim.Simulation.SimulationObjects if b.DescriptorName == "Inlet")
    references = [
        executor._reference(sim, "part", sim, "SIM")["id"],
        executor._reference(inlet, "simulation_object", sim, "inlet")["id"],
    ]
    executor._sim_save(references[0])
    executor._sim_close(references[0])
    stale = []
    for ref in references:
        try:
            executor.objects.resolve(ref)
        except NXToolError as error:
            assert error.code == "NX_OBJECT_STALE"
            stale.append(error.code)
        else:
            raise AssertionError("Closed object unexpectedly resolves")
    executor._sim_open(str(path))
    reopened = executor.session.Parts.BaseWork
    after = capture_boundary_state(reopened, nx)
    assert after["comparison_verified"]

    def semantic(value):
        if isinstance(value, list):
            return [semantic(v) for v in value]
        if isinstance(value, dict):
            return {k: semantic(v) for k, v in value.items() if k not in {"sha256", "tag"}}
        return value

    assert before["sha256"] == after["sha256"], "Semantic fingerprint changed after reopen"
    assert semantic(before) == semantic(after), "Native boundary values changed after reopen"
    assert flags == {
        p.FullPath: bool(p.IsModified) for p in executor.session.Parts if p != reopened
    }
    result = {
        "passed": True,
        "before": before,
        "after": after,
        "semantic_values_preserved": True,
        "hash_preserved": before["sha256"] == after["sha256"],
        "stale_errors": stale,
        "unrelated_modified_flags_preserved": True,
        "document": executor._reference(reopened, "part", reopened, "SIM")["id"],
        "solver_launched": False,
    }
    receipt.write_text(json.dumps(result, indent=2))
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\fan-definition-reopen.json").write_text(
        json.dumps(result, indent=2)
    )
    return result
