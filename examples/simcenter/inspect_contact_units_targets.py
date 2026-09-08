def run(executor):
    sim = executor.session.Parts.BaseWork
    if not sim.FullPath.endswith("contact_context_r2.sim"):
        raise ValueError("Expected isolated contact context")
    units = []
    for unit in sim.UnitCollection:
        if any(term in unit.Name.lower() for term in ("conduct", "resist")):
            units.append({"name": unit.Name, "symbol": unit.Symbol})
    targets = []
    for bc in sim.Simulation.Constraints:
        rows = []
        for i in range(bc.TargetSetManager.TargetSetCount):
            _, members = bc.TargetSetManager.GetTargetSetMembers(i)
            rows.append(
                [
                    {
                        "type": type(m.Obj).__name__,
                        "journal": m.Obj.JournalIdentifier,
                        "owner": m.Obj.OwningPart.FullPath,
                    }
                    for m in members
                    if m is not None and m.Obj is not None
                ]
            )
        targets.append({"name": bc.Name, "targets": rows})
    return {"units": units, "constraints": targets, "solver_launched": False}
