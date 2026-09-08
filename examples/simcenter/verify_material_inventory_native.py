"""Bind and verify material inspection without changing document or UI state."""


def run(executor):
    import importlib
    import types

    import nx_mcp.hardened as hardened
    import nx_mcp.simcenter.native as native
    import nx_mcp.simcenter.server as server

    importlib.reload(native)
    importlib.reload(server)
    method = types.MethodType(native.SimcenterMixin._sim_materials, executor)
    executor._sim_materials = method
    executor._handlers['nx_sim_materials'] = method
    hardened.READ_ONLY.add('nx_sim_materials')
    session = executor.session
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    work, display = session.Parts.BaseWork, session.Parts.BaseDisplay
    fem = next(p for p in session.Parts if p.FullPath.endswith('VariantTxnR1_mesh.fem'))
    document = executor._reference(fem, 'part', fem, 'FEM')['id']
    rows, offset = [], 0
    while True:
        page = method(document, offset=offset, limit=1)
        rows.extend(page['materials'])
        if page['next_offset'] is None:
            break
        offset = page['next_offset']
    matches = [r for r in rows if r['material']['name'] == 'MCP_STDIO_ORTHOTROPIC_R1']
    assert len(matches) == 1, 'Creation replay must leave exactly one material'
    assert 'inspection_errors' not in matches[0]
    assert matches[0]['provenance'] == 'Synthetic MCP acceptance material; not production data'
    assert flags == {p.FullPath: bool(p.IsModified) for p in session.Parts}
    assert work == session.Parts.BaseWork and display == session.Parts.BaseDisplay
    return {'materials': rows, 'paging_verified': True, 'duplicate_count': len(matches),
            'document_flags_preserved': True, 'work_display_preserved': True}
