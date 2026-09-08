"""Inspect retained native coupled setup and actual named-table properties."""


def run(executor):
    import NXOpen as nx

    from nx_mcp.simcenter.properties import read_properties

    sim = executor.session.Parts.BaseWork
    if "E-coupled-setup-20260908-r1" not in sim.FullPath:
        raise ValueError("Inspect only the retained coupled fixture")
    solution = sim.Simulation.ActiveSolution
    rows = []
    table = solution.PropertyTable
    for index in range(table.GetPropertyCount()):
        name = table.GetPropertyNameByIndex(index)
        if "licen" in name.lower():
            continue
        if str(table.GetBasePropertyType(name)) != "0":
            continue
        row = {"property": name}
        try:
            value = table.GetNamedPropertyTablePropertyValue(name)
            row.update(
                read=True,
                assigned=value is not None,
                descriptor=value.DescriptorType if value else None,
            )
        except Exception as error:
            row.update(read=False, nx_code=getattr(error, "ErrorCode", None))
        rows.append(row)
    return {
        "path": sim.FullPath,
        "step_count": solution.StepCount,
        "steps": [
            {
                "name": solution.GetStepByIndex(i).Name,
                "properties": read_properties(solution.GetStepByIndex(i).PropertyTable, nx),
            }
            for i in range(solution.StepCount)
        ],
        "named_properties": rows,
        "existing_tables": [
            {"name": t.Name, "descriptor": t.DescriptorType}
            for t in sim.ModelingObjectPropertyTables
        ],
        "solution_properties": read_properties(table, nx),
    }
