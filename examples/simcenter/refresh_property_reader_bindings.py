"""Refresh five known stale consumers on the NX thread; no model operations."""


def run(executor):
    import dis
    import importlib

    from nx_mcp.simcenter import properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    expected = {
        "distributed_heat": ["create_distributed_heat"],
        "flow": ["create_initial_step", "attach_default_tables"],
        "fluid_material": ["assign_fluid_material"],
        "head_loss": ["attach_head_loss", "set_opening_head_loss"],
        "time_controls": ["configure_transient_steps"],
    }
    session = executor.session
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    work = session.Parts.BaseWork.FullPath
    display = session.Parts.BaseDisplay.FullPath
    rows = []
    for name, functions in expected.items():
        module = importlib.reload(importlib.import_module("nx_mcp.simcenter." + name))
        # Reload retains old globals. Refresh this legacy alias for any previously
        # captured function objects; new functions import the reader at call time.
        if hasattr(module, "read_properties"):
            module.read_properties = properties.read_properties
        for name in functions:
            fn = getattr(module, name)
            instructions = list(dis.get_instructions(fn))
            assert any(
                i.opname == "IMPORT_FROM" and i.argval == "read_properties" for i in instructions
            )
            assert not any(
                i.opname == "LOAD_GLOBAL" and i.argval == "read_properties" for i in instructions
            )
            rows.append(
                {"function": fn.__module__ + "." + fn.__name__, "call_time_reader_verified": True}
            )
    assert flags == {p.FullPath: bool(p.IsModified) for p in session.Parts}
    assert work == session.Parts.BaseWork.FullPath and display == session.Parts.BaseDisplay.FullPath
    return {
        "passed": True,
        "functions": rows,
        "document_flags_preserved": True,
        "work_path": work,
        "display_path": display,
        "solver_launched": False,
        "scope": "Live import binding and document-state preservation; existing authoring behavior covered by targeted regression tests",
    }
