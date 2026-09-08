"""One isolated active heat-field scale/export/reopen check; never launch a solve."""


def run(executor):
    import importlib
    import json
    import time
    from pathlib import Path

    import NXOpen as nx

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.boundary_state import capture_effective_membership

    importlib.reload(importlib.import_module("nx_mcp.simcenter.properties"))
    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    started = time.monotonic()
    sim = executor.session.Parts.BaseWork
    resuming_draft = sim.FullPath.endswith(r"F1-active-field-20260908-r1\draft\field_draft.sim")
    if "F2-membership-audit-20260908-r1" not in sim.FullPath and not resuming_draft:
        raise ValueError("Requires the isolated F2 fixture; do not modify other work parts")
    root = executor.workspace.resolve("ui-benchmarks/F1-active-field-20260908-r1")
    if root.exists() and not resuming_draft:
        raise ValueError("Inspect retained field lifecycle receipt before any replay")
    if (root / "export").exists():
        raise ValueError("Export already attempted; inspect retained files")
    root.mkdir(exist_ok=True)
    receipt = root / "verification.json"
    result = {"stages": [], "solver_launched": False}

    def record(stage, **values):
        result["stages"].append({"stage": stage, "elapsed_s": time.monotonic() - started, **values})
        receipt.write_text(json.dumps(result, indent=2))

    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts if p != sim}
    if not resuming_draft:
        executor._sim_save_as(
            executor._reference(sim, "part", sim, "SIM")["id"],
            str(root / "draft" / "field_draft.sim"),
        )
    loads = list(sim.Simulation.Loads)
    if len(loads) != 1 or loads[0] not in list(sim.Simulation.ActiveSolution.GetBcs()):
        raise ValueError("Expected exactly one active heat load")
    load = loads[0]
    table = load.PropertyTable
    original = next(p for p in read_properties(table, nx) if p["name"] == "Heat Load")
    if float(original["expression"]) != 0.1 or original.get("unit_symbol") != "W":
        raise ValueError("Unexpected baseline heat load")
    mark = executor.session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "MCP active field scale fixture"
    )
    try:
        field = sim.FieldManager.CreateFieldExpression("0.1", sim.UnitCollection.FindObject("Watt"))
        wrapper = sim.FieldManager.CreateScalarFieldWrapperWithField(field, 2.0)
        table.SetScalarFieldWrapperPropertyValue("Heat Load", wrapper)
        actual = next(p for p in read_properties(table, nx) if p["name"] == "Heat Load")
        if (
            actual.get("field_scale") != 2
            or actual.get("evaluated_value") != 0.2
            or actual.get("unit_symbol") != "W"
        ):
            raise ValueError("Native heat scale readback mismatch")
    except Exception:
        executor.session.UndoToMark(mark, None)
        record("authoring_failed_rolled_back")
        raise
    record("authored", property=actual)
    executor._sim_save_as(
        executor._reference(sim, "part", sim, "SIM")["id"],
        str(root / "export" / "active_field.sim"),
    )
    ref = executor._reference(sim, "part", sim, "SIM")["id"]
    path = sim.FullPath

    def inspect(part):
        heat = list(part.Simulation.Loads)[0]
        row = next(p for p in read_properties(heat.PropertyTable, nx) if p["name"] == "Heat Load")
        return {"property": row, "membership": capture_effective_membership(part)}

    before = inspect(sim)
    record("saved_before_export", state=before)
    try:
        exported = executor._sim_export_input(ref)
        record("exported", result=exported)
    except Exception as error:
        record("export_failed", code=getattr(error, "code", None), message=str(error))
        raise
    executor._sim_save(ref)
    executor._sim_close(ref)
    try:
        executor.objects.resolve(ref, expected_kind="part")
    except NXToolError as error:
        stale_code = error.code
    else:
        raise ValueError("Closed reference still resolves")
    executor._sim_open(path)
    reopened = executor.session.Parts.BaseWork
    after = inspect(reopened)

    # Native tags are session-local handles, not persistent semantic field identity.
    def semantic(state):
        value = json.loads(json.dumps(state))
        value["property"]["field_reference"].pop("tag", None)
        return value

    if semantic(before) != semantic(after):
        record("reopen_mismatch", before=before, after=after)
        raise ValueError("Field definition, scale or membership changed after reopen")
    if flags != {p.FullPath: bool(p.IsModified) for p in executor.session.Parts if p != reopened}:
        raise ValueError("Unrelated document modified flags changed")
    result.update(
        document=executor._reference(reopened, "part", reopened, "SIM")["id"],
        native_lifecycle_passed=True,
        stale_reference_error=stale_code,
        before=before,
        after=after,
        export_heat_value_verified=False,
        numerical_acceptance="not_tested",
        unrelated_modified_flags_preserved=True,
    )
    record("reopened")
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\active-field-lifecycle.json").write_text(
        json.dumps(result, indent=2)
    )
    return result
