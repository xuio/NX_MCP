"""Verify stable collector inspection against the solved rotated conduction FEM."""


def run(executor):
    import importlib
    import types

    import nx_mcp.hardened as hardened
    import nx_mcp.simcenter.native as native
    import nx_mcp.simcenter.server as server

    importlib.reload(native)
    importlib.reload(server)
    method = types.MethodType(native.SimcenterMixin._sim_collectors, executor)
    executor._sim_collectors = method
    executor._handlers['nx_sim_collectors'] = method
    hardened.READ_ONLY.add('nx_sim_collectors')
    session = executor.session
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    work, display = session.Parts.BaseWork, session.Parts.BaseDisplay
    fem = next(p for p in session.Parts if p.FullPath.endswith('OrthoZR1_mesh.fem'))
    document = executor._reference(fem, 'part', fem, 'FEM')['id']
    page = method(document, limit=100)
    repeat = method(document, limit=100)
    assert page == repeat, 'Read-only inventory must return stable identity and hash'
    solids = [r for r in page['collectors'] if r['native_type'] == 'Solid']
    assert len(solids) == 1
    row = solids[0]
    assert row['material']['name'] == 'ORTHOTROPIC_STUDY_12_7_04'
    assert row['orientation']['native_selector'] == 1
    assert row['orientation']['stored_frame']['axes_in_part_absolute'] == [[0., 1., 0.], [0., 0., 1.], [1., 0., 0.]]
    assert len(row['state_sha256']) == 64
    assert flags == {p.FullPath: bool(p.IsModified) for p in session.Parts}
    assert work == session.Parts.BaseWork and display == session.Parts.BaseDisplay
    return {'inventory': page, 'repeat_stable': True, 'document_flags_preserved': True,
            'work_display_preserved': True}
