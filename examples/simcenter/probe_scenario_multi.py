"""Native isolated fixture: two bodies, forced second-source failure, rollback and successful reapplication."""


def run(executor):
    import importlib
    import types

    import nx_mcp.hardened as hardened
    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.recovery import authoring_snapshot
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    for module in ("benchmark_geometry", "scenario_import", "scenario_apply", "server", "native"):
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
        "ui-benchmarks/scenario-multi-20260908-r1",
        length_mm=10,
        block_origins_mm=[[0, 0, 0], [20, 0, 0]],
    )
    sim = executor.session.Parts.BaseWork
    document = executor._reference(sim, "part", sim, "part")["id"]
    bodies = list(sim.FemPart.Bodies)
    assert len(bodies) == created["body_count"] == 2
    targets = [executor._reference(b, "body", sim.FemPart, "body")["id"] for b in bodies]
    source_path = executor.workspace.resolve("ui-benchmarks/scenario-multi-20260908-r1/sources.csv")
    with source_path.open("x") as stream:
        stream.write(
            "name,region,watts,category,accounting_id,provenance_kind,provenance_source\nCPU,SOC,8,internal_heat,cpu,assumed,benchmark\nSSD,SSD,2,internal_heat,ssd,assumed,benchmark\nUSB,,10,exported_electrical,usb,assumed,benchmark\n"
        )
    args = {
        "document": document,
        "path": str(source_path),
        "region_targets": {"SOC": targets[0], "SSD": targets[1]},
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

    calls = []

    def wrong_readback(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(result["power_w"])
        if len(calls) == 2:
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
    assert calls == [8.0, 2.0]
    assert authoring_snapshot(sim) == before
    result = executor._sim_scenario_apply(**args)
    assert result["applied_internal_heat_W"] == 10
    assert result["totals_W"]["exported_electrical"] == 10
    assert not result["ambient_applied"] and len(result["loads"]) == 2
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
        "created_powers_before_forced_failure": calls,
        "result": result,
        "repeated_application": conflict,
        "existing_part_flags_preserved": True,
    }
