"""Inspect native getters on a clean, saved diagnostic SIM."""


def run(executor):
    import hashlib

    import NXOpen as nx

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    session = executor.session
    part = session.Parts.BaseWork
    if not part.FullPath.endswith("reopen_modified_probe_r1.sim") or part.IsModified:
        raise ValueError("Expected clean diagnostic copy")
    before = {p.FullPath: bool(p.IsModified) for p in session.Parts if p != part}
    path = executor.workspace.resolve(part.FullPath)
    target = path
    original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    stages = []

    def record(stage):
        stages.append({"stage": stage, "modified": bool(part.IsModified)})

    record("before_inspection")
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
