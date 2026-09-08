"""Inspect actual samples of the pre-metadata synthetic duct fan; no mutation."""


def run(executor):
    sim=next(p for p in executor.session.Parts if p.FullPath.endswith('rpm_flow_r1.sim'))
    inlet=next(o for o in sim.Simulation.SimulationObjects if o.Name=='Duct Inlet')
    wrapper=inlet.PropertyTable.GetScalarFieldWrapperPropertyValue('Fan Curve')
    table=wrapper.GetField()
    iv,dv=table.GetIndependentVariables(),table.GetDependentVariables()
    assert len(iv)==len(dv)==1
    u=sim.UnitCollection
    q=[u.Convert(iv[0].Units,u.FindObject('CubicMeterPerSecond'),v) for v in table.GetData(iv[0])]
    p=[u.Convert(dv[0].Units,u.FindObject('PressurePascals'),v) for v in table.GetData(dv[0])]
    assert len(q)==len(p)==3
    assert all(abs(a-b)<1e-12 for a,b in zip(q,[0.,0.0002,0.0004]))
    assert all(abs(a-b)<1e-12 for a,b in zip(p,[1.,0.5,0.]))
    assert wrapper.GetFieldScaleFactor()==1
    return {'path':sim.FullPath,'field':table.Name,'flow_m3_s':q,'pressure_Pa':p,
            'scale':wrapper.GetFieldScaleFactor(),'interpolation':str(table.InterpolationMethod),
            'rpm_metadata':'absent; 1000 RPM synthetic source recorded by benchmark fixture',
            'read_only':True}
