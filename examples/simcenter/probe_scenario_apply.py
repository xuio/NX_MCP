"""Native isolated fixture: forced post-commit failure, rollback, then scenario creation."""


def run(executor):
    import importlib
    import types

    import nx_mcp.hardened as hardened
    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.recovery import authoring_snapshot
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    for module in ("scenario_import", "scenario_apply", "server", "native"):
        importlib.reload(importlib.import_module("nx_mcp.simcenter." + module))
    from nx_mcp.simcenter import native, scenario_apply, server

    for name in server.READ_ONLY | server.NON_MODEL:
        method = "_" + name[3:]
        bound = types.MethodType(getattr(native.SimcenterMixin, method), executor)
        setattr(executor, method, bound)
        executor._handlers[name] = bound
    hardened.READ_ONLY.update(server.READ_ONLY)
    hardened.NON_MODEL.update(server.NON_MODEL)
    old_parts = [(p, bool(p.IsModified)) for p in executor.session.Parts]
    created = executor._sim_create_benchmark(
        "ui-benchmarks/scenario-apply-20260908-r1", length_mm=10
    )
    sim = executor.session.Parts.BaseWork
    document = executor._reference(sim, "part", sim, "part")["id"]
    body = list(sim.FemPart.Bodies)[0]
    target = executor._reference(body, "body", sim.FemPart, "body")["id"]
    args = {
        "document": document,
        "path": "ui-benchmarks/scenario-preview-20260908-r1.csv",
        "region_targets": {"SOC": target},
        "format": "csv",
        "metadata": {
            "name": "apply-benchmark",
            "workload_revision": "assumed-r1",
            "ambient_K": 298.15,
        },
    }
    args["expected_preview_sha256"] = executor._sim_scenario_preview(**args)["preview_sha256"]
    before = authoring_snapshot(sim)
    original = scenario_apply.create_body_power

    def wrong_readback(*args, **kwargs):
        result = original(*args, **kwargs)
        result["power_w"] += 1
        return result

    scenario_apply.create_body_power = wrong_readback
    try:
        try:
            executor._sim_scenario_apply(**args)
        except NXToolError as error:
            assert error.details["mutation_outcome"] == "rolled_back", error.details
            failure = {"code": error.code, "details": error.details}
        else:
            raise AssertionError("Forced mismatch must fail")
    finally:
        scenario_apply.create_body_power = original
    assert authoring_snapshot(sim) == before
    result = executor._sim_scenario_apply(**args)
    assert result["applied_internal_heat_W"] == 8
    assert result["totals_W"]["exported_electrical"] == 10
    assert not result["ambient_applied"] and len(result["loads"]) == 1
    try:
        executor._sim_scenario_apply(**args)
    except NXToolError as error:
        assert error.code == "NX_SIM_SCENARIO_CONFLICT"
        conflict = error.code
    else:
        raise AssertionError("Existing loads must reject repeated application")
    assert all(p.IsModified == modified for p, modified in old_parts)
    return {
        "created": created,
        "args": args,
        "forced_failure": failure,
        "result": result,
        "repeated_application": conflict,
        "existing_part_flags_preserved": True,
    }
