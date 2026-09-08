"""Verify saved heat-load persistence; close only the unmodified test SIM."""


def run(executor):
    import NXOpen as nx

    from nx_mcp.simcenter.properties import read_properties

    session = executor.session
    sim = session.Parts.BaseWork
    path = sim.FullPath
    if not path.endswith(r"F-convection-mcp-20260908-r1\saved_power.sim") or sim.IsModified:
        raise ValueError("Expected the saved, unmodified heat-load test SIM")
    other_flags = {p.FullPath: bool(p.IsModified) for p in session.Parts if p != sim}
    old_id = executor._part_id(sim)
    sim.Close(nx.BasePart.CloseWholeTree.FalseValue, nx.BasePart.CloseModified.CloseModified, None)
    executor.objects.invalidate_part(old_id)
    reopened, status = session.Parts.OpenBaseDisplay(path)
    if status:
        status.Dispose()
    session.Parts.SetWork(reopened)
    constraints = [bc for bc in reopened.Simulation.Loads if bc.Name == "MCP_INTERNAL_POWER"]
    if len(constraints) != 1:
        raise ValueError("Saved constraint count differs")
    boundary = constraints[0]
    provenance = boundary.GetStringUserAttribute("NX_MCP_PROVENANCE", -1)
    basis = boundary.GetStringUserAttribute("NX_MCP_ENERGY_ACCOUNTING", -1)
    if (
        provenance != "Assumed 0.1 W internal heat for isolated thermal authoring verification"
        or basis != "internal_heat"
    ):
        raise ValueError("Native provenance attributes did not survive reopen")
    properties = read_properties(boundary.PropertyTable, nx)
    coefficient = next(p for p in properties if p["name"] == "Heat Load")
    if float(coefficient["expression"]) != 0.1:
        raise ValueError("Saved heat-load coefficient differs")
    _, members = boundary.TargetSetManager.GetTargetSetMembers(0)
    if len(members) != 1 or any(m.Obj.OwningPart != reopened for m in members):
        raise ValueError("Saved SIM body targets did not resolve")
    after = {p.FullPath: bool(p.IsModified) for p in session.Parts if p != reopened}
    if after != other_flags:
        raise ValueError("Other loaded document flags changed")
    return {
        "document_path": path,
        "coefficient": coefficient,
        "provenance": provenance,
        "energy_accounting": basis,
        "target_body_count": len(members),
        "other_documents_unchanged": True,
        "reopened_modified": bool(reopened.IsModified),
        "solver_launched": False,
        "scope": "Saved heat-load persistence only; no mesh or solve acceptance",
    }
