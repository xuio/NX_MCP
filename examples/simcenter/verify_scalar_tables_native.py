"""Batch native scalar-table units, metadata and property-wrapper inspection; no solve."""


def run(executor):
    import importlib
    import json
    import time
    import types
    from pathlib import Path

    from nx_mcp import hardened
    from nx_mcp.simcenter import field_definition, native, scalar_tables
    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    importlib.reload(scalar_tables)
    importlib.reload(field_definition)
    importlib.reload(native)
    for suffix in ["scalar_table", "scalar_tables"]:
        method = types.MethodType(getattr(native.SimcenterMixin, "_sim_" + suffix), executor)
        setattr(executor, "_sim_" + suffix, method)
        executor._handlers["nx_sim_" + suffix] = method
    hardened.NON_MODEL.add("nx_sim_scalar_table")
    hardened.READ_ONLY.add("nx_sim_scalar_tables")
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    fixture = executor._sim_create_benchmark(
        "ui-benchmarks/T-scalar-tables-20260909-r1", length_mm=10, width_mm=10, height_mm=10
    )
    session = executor.session
    sim = session.Parts.BaseWork
    trials = []
    before = {int(f.Tag) for f in sim.FieldManager.Fields}
    for axis in scalar_tables.AXES:
        for quantity in scalar_tables.VALUES:
            mark = session.SetUndoMark(
                executor.nxopen.Session.MarkVisibility.Invisible, "Scalar table fixture trial"
            )
            started = time.monotonic()
            builder = None
            try:
                x = [0, 10, 20] if axis == "time" else [273.15, 293.15, 313.15]
                y = [280, 300, 320] if quantity == "temperature" else [1, 2, 3]
                m = {
                    "name": "MCP_SCALAR_TRIAL",
                    "axis": axis,
                    "quantity": quantity,
                    "samples": [list(p) for p in zip(x, y, strict=True)],
                    "provenance": "Generic API unit fixture",
                }
                created = scalar_tables.create(session, sim, m)
                table = created.pop("table")
                inspected = scalar_tables.inspect(sim, table)
                assert inspected["manifest"] == scalar_tables.validate(m)
                if axis == "time" and quantity == "power":
                    builder = sim.Simulation.CreateBcBuilderForLoadDescriptor(
                        "Heat Load", "MCP_WRAPPER_PROBE"
                    )
                    wrapper = sim.FieldManager.CreateScalarFieldWrapperWithField(table, 2.0)
                    builder.PropertyTable.SetScalarFieldWrapperPropertyValue("Heat Load", wrapper)
                    prop = next(
                        p
                        for p in read_properties(builder.PropertyTable, executor.nxopen)
                        if p["name"] == "Heat Load"
                    )
                    assert (
                        prop["field_scale"] == 2.0
                        and prop["field_definition"]["kind"] == "validated_scalar_table"
                    )
                    assert (
                        prop["field_definition"]["native_samples_si"]["samples_si"] == m["samples"]
                    )
                    inspected["property_wrapper_readback"] = prop
                inspected["native_seconds"] = time.monotonic() - started
                trials.append(inspected)
            finally:
                if builder:
                    builder.Destroy()
                session.UndoToMark(mark, None)
                session.DeleteUndoMark(mark, None)
            assert {int(f.Tag) for f in sim.FieldManager.Fields} == before
    sid = executor._reference(sim, "part", sim, "SIM")["id"]
    executor._sim_save(sid)
    assert all(
        {p.FullPath: bool(p.IsModified) for p in session.Parts}[path] == value
        for path, value in flags.items()
    )
    sim.ModelingViews.WorkView.Fit()
    sim.ModelingViews.WorkView.UpdateDisplay()
    result = {
        "fixture": fixture,
        "document": sid,
        "path": sim.FullPath,
        "trials": trials,
        "rollback_verified": True,
        "unrelated_flags_preserved": True,
        "solver_launched": False,
    }
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\scalar-tables-native.json").write_text(
        json.dumps(result, indent=2)
    )
    return result
