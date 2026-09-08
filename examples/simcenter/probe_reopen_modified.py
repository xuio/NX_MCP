"""Locate a native SIM modified-flag transition using a fresh disk copy."""


def run(executor):
    import hashlib
    import shutil

    import NXOpen as nx

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    session = executor.session
    source = session.Parts.BaseWork
    if "scenario-multi-mcp-20260908-r1" not in source.FullPath:
        raise ValueError("Expected isolated scenario source")
    before = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    path = executor.workspace.resolve(source.FullPath)
    target = executor.workspace.resolve(path.parent / "reopen_modified_probe_r1.sim")
    if target.exists():
        raise ValueError("Fresh probe copy required")
    original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    shutil.copy2(path, target)
    part, status = session.Parts.OpenBaseDisplay(str(target))
    stages = []

    def record(stage):
        stages.append({"stage": stage, "modified": bool(part.IsModified)})

    record("OpenBaseDisplay_returned")
    if status:
        status.Dispose()
    record("load_status_disposed")
    session.Parts.SetWork(part)
    record("SetWork")
    loads = list(part.Simulation.Loads)
    record("enumerate_loads")
    enum = nx.BasePropertyTable.BasePropertyType
    for load in loads:
        table = load.PropertyTable
        record(load.Name + ":PropertyTable")
        count = table.GetPropertyCount()
        for i in range(count):
            name = table.GetPropertyNameByIndex(i)
            if "licen" in name.lower():
                continue
            kind = table.GetBasePropertyType(name)
            record(load.Name + ":" + name + ":type")
            if kind == enum.ScalarFieldWrapper:
                wrapper = table.GetScalarFieldWrapperPropertyValue(name)
                record(load.Name + ":" + name + ":wrapper")
                if wrapper:
                    expression = wrapper.GetExpression()
                    record(load.Name + ":" + name + ":GetExpression")
                    if expression:
                        expression.GetFormula()
                        record(load.Name + ":" + name + ":GetFormula")
                    wrapper.GetField()
                    record(load.Name + ":" + name + ":GetField")
        load.TargetSetManager.GetTargetSetMembers(0)
        record(load.Name + ":targets")
        load.GetStringUserAttribute("NX_MCP_PROVENANCE", -1)
        record(load.Name + ":provenance")
    assert {p.FullPath: bool(p.IsModified) for p in session.Parts if p != part} == before
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original_hash
    return {
        "path": str(target),
        "source_unchanged": True,
        "other_flags_preserved": True,
        "stages": stages,
        "saved": False,
    }
