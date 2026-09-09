"""Refresh initial-condition handler and verify post-write rollback on an isolated SIM."""


def run(executor):
    import importlib
    import types

    from nx_mcp import hardened
    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter import initial_conditions, native

    importlib.reload(initial_conditions)
    importlib.reload(native)
    method = types.MethodType(native.SimcenterMixin._sim_initial_conditions, executor)
    executor._sim_initial_conditions = method
    executor._handlers["nx_sim_initial_conditions"] = method
    hardened.NON_MODEL.add("nx_sim_initial_conditions")
    sim = executor.session.Parts.BaseWork
    assert sim.FullPath.endswith("temperature_material_public_r1.sim")
    sol = sim.Simulation.ActiveSolution
    before = initial_conditions.readback(sim, sol)
    flags = [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts]
    original = initial_conditions.readback
    calls = []

    def fail_after_write(*args):
        actual = original(*args)
        calls.append(actual)
        if len(calls) == 2:
            raise ValueError("Injected failure after native initial-temperature write")
        return actual

    try:
        initial_conditions.readback = fail_after_write
        try:
            method(executor._reference(sim, "part", sim, "SIM")["id"], "uniform", 323.15)
        except NXToolError as error:
            assert error.details["mutation_outcome"] == "rolled_back"
            failure = {"code": error.code, "details": error.details}
        else:
            raise AssertionError("Expected post-write failure")
    finally:
        initial_conditions.readback = original
    assert len(calls) == 2 and calls[1]["stored_temperature"]["temperature_k"] == 323.15
    assert before == original(sim, sol)
    assert flags == [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts]
    return {
        "rollback": failure,
        "post_write_readback": calls[1],
        "state_restored": True,
        "document_flags_restored": True,
        "solver_launched": False,
    }
