"""Read installed load/constraint catalogs for the isolated Thermal context."""


def run(executor):
    from nx_mcp.simcenter.descriptors import descriptor_inventory

    session = executor.session
    sim = next(p for p in session.Parts if p.FullPath.endswith("contact_context_r2.sim"))
    before = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    work, display = session.Parts.BaseWork, session.Parts.BaseDisplay
    rows = {}
    for kind in ("load", "constraint"):
        offset, names = 0, []
        while True:
            page = descriptor_inventory(sim, kind=kind, offset=offset, limit=100)
            names.extend(r["descriptor_name"] for r in page["descriptors"])
            if page["next_offset"] is None:
                break
            offset = page["next_offset"]
        rows[kind] = names
    assert before == {p.FullPath: bool(p.IsModified) for p in session.Parts}
    assert work == session.Parts.BaseWork and display == session.Parts.BaseDisplay
    return {
        "catalogs": rows,
        "path": sim.FullPath,
        "read_only": True,
        "simulation_objects_enumerated": False,
        "document_state_preserved": True,
    }
