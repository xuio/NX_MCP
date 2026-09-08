"""Native fixture: fresh CSV and read-only preview in the isolated contact test SIM."""


def run(executor):
    import importlib
    import types

    import nx_mcp.hardened as hardened

    for module in ("scenario_import", "server", "native"):
        importlib.reload(importlib.import_module("nx_mcp.simcenter." + module))
    from nx_mcp.simcenter import native, server

    for name in server.READ_ONLY | server.NON_MODEL:
        method = "_" + name[3:]
        bound = types.MethodType(getattr(native.SimcenterMixin, method), executor)
        setattr(executor, method, bound)
        executor._handlers[name] = bound
    hardened.READ_ONLY.update(server.READ_ONLY)
    hardened.NON_MODEL.update(server.NON_MODEL)
    before = [(int(p.Tag), bool(p.IsModified)) for p in executor.session.Parts]
    work, display = executor.session.Parts.BaseWork, executor.session.Parts.BaseDisplay
    sim = next(p for p in executor.session.Parts if p.FullPath.endswith("contact_context_r2.sim"))
    body = list(sim.FemPart.Bodies)[0]
    document = executor._reference(sim, "part", sim, "part")["id"]
    target = executor._reference(body, "body", sim.FemPart, "body")["id"]
    path = executor.workspace.resolve("ui-benchmarks/scenario-preview-20260908-r1.csv")
    if path.exists():
        raise RuntimeError("Fresh preview fixture path required")
    path.write_text(
        "name,region,watts,category,accounting_id,provenance_kind,provenance_source\nCPU,SOC,8,internal_heat,cpu,assumed,benchmark\nUSB,,10,exported_electrical,usb,assumed,benchmark\n"
    )
    args = {
        "document": document,
        "path": str(path),
        "region_targets": {"SOC": target},
        "format": "csv",
        "metadata": {
            "name": "preview-benchmark",
            "workload_revision": "assumed-r1",
            "ambient_K": 298.15,
        },
    }
    result = executor._sim_scenario_preview(**args)
    assert result["totals_W"]["internal_heat"] == 8
    assert result["totals_W"]["exported_electrical"] == 10
    assert not result["applied_to_nx"] and not result["ready_to_apply"]
    assert before == [(int(p.Tag), bool(p.IsModified)) for p in executor.session.Parts]
    assert executor.session.Parts.BaseWork == work and executor.session.Parts.BaseDisplay == display
    return {"result": result, "args": args, "document_state_preserved": True}
