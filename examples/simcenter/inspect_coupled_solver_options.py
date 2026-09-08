"""Inspect native solver-option and coupled step tables without launching a solver."""


def run(executor):
    import NXOpen as nx

    from nx_mcp.simcenter.properties import read_properties

    sim = executor.session.Parts.BaseWork
    solution = sim.Simulation.ActiveSolution
    if solution.AnalysisType != "Coupled Thermal-Flow":
        raise ValueError("Select the isolated coupled benchmark")
    before = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    options = solution.SolverOptionsPropertyTable
    result = {
        "path": sim.FullPath,
        "solver_options": None
        if options is None
        else {
            "neutral": options.DescriptorNeutralName,
            "specific": options.DescriptorSpecificName,
            "properties": read_properties(options, nx),
        },
        "steps": [
            {
                "name": solution.GetStepByIndex(i).Name,
                "properties": read_properties(solution.GetStepByIndex(i).PropertyTable, nx),
            }
            for i in range(solution.StepCount)
        ],
    }
    result["changed_flags"] = [
        p.FullPath
        for p in executor.session.Parts
        if p.FullPath in before and bool(p.IsModified) != before[p.FullPath]
    ]
    result["solver_launched"] = False
    return result
