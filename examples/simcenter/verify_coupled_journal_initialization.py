def run(executor):
    import hashlib
    import shutil
    import xml.etree.ElementTree as ET
    from pathlib import Path

    import NXOpen.CAE as cae

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    s = executor.session
    nx = executor.nxopen
    source = executor.workspace.resolve(
        "ui-benchmarks/E-coupled-fan-public-20260909-r1/coupled_fan_public_r1.sim"
    )
    outcomes = []
    for label, initialize in [("control", False), ("journal", True)]:
        root = executor.workspace.resolve("ui-benchmarks/E-journal-init-" + label + "-20260909-r1")
        if root.exists():
            raise ValueError("Comparison exists: inspect before retry")
        root.mkdir()
        target = root / (label + ".sim")
        shutil.copy2(source, target)
        sim, status = s.Parts.OpenBaseDisplay(str(target))
        status.Dispose()
        s.Parts.SetWork(sim)
        sim.ModelingViews.WorkView.Fit()
        sim.ModelingViews.WorkView.UpdateDisplay()
        sol = sim.Simulation.ActiveSolution
        pt = sol.PropertyTable
        mark = s.SetUndoMark(nx.Session.MarkVisibility.Visible, "Journal setup comparison " + label)
        for key, value, unit in [
            ("Fluid Temperature", "20", "Celsius"),
            ("Absolute Pressure", "0.101325", "PressureNewtonPerSquareMilliMeter"),
        ]:
            wrapper = pt.GetScalarFieldWrapperPropertyValue(key)
            expr = wrapper.GetExpression()
            if expr is None:
                raise ValueError("Expected existing native expression")
            sim.Expressions.EditWithUnits(expr, sim.UnitCollection.FindObject(unit), value)
            wrapper.SetExpression(expr)
            pt.SetScalarFieldWrapperPropertyValue(key, wrapper)
        pt.SetIntegerPropertyValue("Ambient Pressure", 0)
        if initialize:
            pt.SetIntegerPropertyValue("Solver Type", 6)
            units = {
                "Mass": "kg",
                "Length": "mm",
                "Time Solution Units": "second",
                "Power": "microWatt",
                "Heat Flux": "microW/mm^2",
                "Energy": "microJoule",
                "Velocity": "mm/s",
                "Pressure": "mN/mm^2",
                "Viscosity": "kg/mm-s",
                "Density": "kg/mm^3",
                "Specific Heat": "microJ/kg-C",
                "Force": "mN",
            }
            for key, value in units.items():
                pt.SetStringPropertyValue(key, value)
        errors = s.UpdateManager.DoUpdate(mark)
        if errors:
            raise ValueError("Native update errors")
        status = sim.Save(
            nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue
        )
        status.Dispose()
        sol.Solve(
            cae.SimSolutionSolveOption.WriteSolverInputFile,
            cae.SimSolutionSetupCheckOption.CompleteCheckAndOutputErrors,
        )
        (xml,) = root.glob("*.xml")
        tree = ET.parse(xml)
        vals = {
            p.attrib["name"]: p.findtext("Value")
            for p in tree.findall(".//AmbientConditions/Property")
            if p.attrib["name"] in ["Ambient Pressure", "Absolute Pressure", "Fluid Temperature"]
        }
        out = Path(r"Z:\nx-mcp-integration\simcenter-discovery") / ("journal-init-" + label + "-r1")
        out.mkdir(exist_ok=False)
        for p in root.iterdir():
            if p.is_file():
                shutil.copy2(p, out / p.name)
        outcomes.append(
            {
                "label": label,
                "ambient_xml": vals,
                "solver_type": pt.GetIntegerPropertyValue("Solver Type"),
                "xml_sha256": hashlib.sha256(xml.read_bytes()).hexdigest(),
                "path": sim.FullPath,
            }
        )
    return {"comparisons": outcomes, "solver_launched": False, "same_physical_inputs": True}
