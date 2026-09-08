"""Verify saved temperature persistence; close only the unmodified test SIM."""


def run(executor):
    import NXOpen as nx

    from nx_mcp.simcenter.properties import read_properties

    session = executor.session
    sim = session.Parts.BaseWork
    path = sim.FullPath
    if not path.endswith(r"A-temperature-mcp-20260908-r1\saved_temperature.sim") or sim.IsModified:
        raise ValueError("Expected the saved, unmodified temperature test SIM")
    other_flags = {p.FullPath: bool(p.IsModified) for p in session.Parts if p != sim}
    old_id = executor._part_id(sim)
    sim.Close(nx.BasePart.CloseWholeTree.FalseValue, nx.BasePart.CloseModified.CloseModified, None)
    executor.objects.invalidate_part(old_id)
    reopened, status = session.Parts.OpenBaseDisplay(path)
    if status:
        status.Dispose()
    session.Parts.SetWork(reopened)
    constraints = [
        bc for bc in reopened.Simulation.Constraints if bc.Name == "MCP_FIXED_TEMPERATURE"
    ]
    if len(constraints) != 1:
        raise ValueError("Saved constraint count differs")
    boundary = constraints[0]
    provenance = boundary.GetStringUserAttribute("NX_MCP_PROVENANCE", -1)
    basis = boundary.GetStringUserAttribute("NX_MCP_TEMPERATURE_BASIS", -1)
    if (
        provenance != "Prescribed 293.15 K cold end for isolated conduction authoring benchmark"
        or basis != "prescribed"
    ):
        raise ValueError("Native provenance attributes did not survive reopen")
    properties = read_properties(boundary.PropertyTable, nx)
    coefficient = next(p for p in properties if p["name"] == "Temperature")
    if float(coefficient["expression"]) != 293.15:
        raise ValueError("Saved temperature coefficient differs")
    _, members = boundary.TargetSetManager.GetTargetSetMembers(0)
    if len(members) != 1 or any(m.Obj.OwningPart != reopened for m in members):
        raise ValueError("Saved SIM face targets did not resolve")
    after = {p.FullPath: bool(p.IsModified) for p in session.Parts if p != reopened}
    if after != other_flags:
        raise ValueError("Other loaded document flags changed")
    return {
        "document_path": path,
        "coefficient": coefficient,
        "provenance": provenance,
        "temperature_basis": basis,
        "target_face_count": len(members),
        "other_documents_unchanged": True,
        "reopened_modified": bool(reopened.IsModified),
        "solver_launched": False,
        "scope": "Saved temperature persistence only; no mesh or solve acceptance",
    }
