"""Bind and exercise the public material handler, then roll back the isolated mutation."""


def run(executor):
    import importlib
    import types

    import nx_mcp.hardened as hardened
    import nx_mcp.simcenter.native as native
    import nx_mcp.simcenter.server as server

    importlib.reload(native)
    importlib.reload(server)
    name = 'nx_sim_orthotropic_material'
    method = types.MethodType(native.SimcenterMixin._sim_orthotropic_material, executor)
    executor._sim_orthotropic_material = method
    executor._handlers[name] = method
    hardened.NON_MODEL.add(name)
    session = executor.session
    work, display = session.Parts.BaseWork, session.Parts.BaseDisplay
    fem = next(p for p in session.Parts if p.FullPath.endswith('VariantTxnR1_mesh.fem'))
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    tags = [int(m.Tag) for m in fem.MaterialManager.PhysicalMaterials]
    history = len(executor._history)
    mark = None
    try:
        result = method(
            executor._reference(fem, 'part', fem, 'FEM')['id'], 'MCP_PUBLIC_ORTHOTROPIC_PROBE',
            [12, 7, 0.4], 1900, 900,
            'Synthetic API acceptance properties; not production PCB data',
        )
        mark = executor._history[-1]['mark']
        assert len(list(fem.MaterialManager.PhysicalMaterials)) == len(tags) + 1
        assert result['properties']['ThermalConductivity3']['value'] == 0.4
        assert result['material']['owner_part_path'] == fem.FullPath
        assert result['collector_assignment'] is False
        return {'public_handler': name, 'readback': result, 'verification': 'native_handler_only',
                'rolled_back_after_readback': True, 'stdio_schema_tested': False}
    finally:
        if mark is not None:
            session.UndoToMark(mark, None)
            session.DeleteUndoMark(mark, None)
            del executor._history[history:]
        assert tags == [int(m.Tag) for m in fem.MaterialManager.PhysicalMaterials]
        _, status = session.Parts.SetDisplay(display, False, False)
        if status:
            status.Dispose()
        session.Parts.SetWork(work)
        assert flags == {p.FullPath: bool(p.IsModified) for p in session.Parts}
