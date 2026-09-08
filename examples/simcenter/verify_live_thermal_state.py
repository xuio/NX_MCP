"""Read the live solid thermal fingerprint twice without modifying the FEM."""


def run(executor):
    from nx_mcp.simcenter.thermal_state import capture_thermal_state
    fem = next(p for p in executor.session.Parts if p.FullPath.endswith('OrthoZR1_mesh.fem'))
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    first = capture_thermal_state(fem, executor.nxopen)
    second = capture_thermal_state(fem, executor.nxopen)
    assert first == second
    assert first['sha256'] and not first['errors']
    row = first['collectors'][0]
    assert row['thermal_properties']['ThermalConductivity3']['value'] == 0.4
    assert row['orientation']['stored_frame']['axes_in_part_absolute'] == [[0.,1.,0.],[0.,0.,1.],[1.,0.,0.]]
    assert flags == {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    return {'thermal_state': first, 'stable_repeat': True, 'flags_preserved': True}
