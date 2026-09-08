"""Read installed property descriptor names for the selected coupled solution."""


def run(executor):
    sim = executor.session.Parts.BaseWork
    solution = sim.Simulation.ActiveSolution
    if solution.AnalysisType != "Coupled Thermal-Flow":
        raise ValueError("Select the coupled benchmark")
    before = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    table = solution.PropertyTable
    rows = []
    for key in (
        "Thermal Parameters",
        "Flow Solution Parameters",
        "Flow Surface Parameters",
        "Coupled Solution Parameters",
        "Thermal-Flow Output Requests",
    ):
        rows.append(
            {"property": key, "property_descriptor_name": table.GetPropertyDescriptorName(key)}
        )
    assert before == {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    return {
        "path": sim.FullPath,
        "descriptor_neutral_name": table.DescriptorNeutralName,
        "descriptor_specific_name": table.DescriptorSpecificName,
        "properties": rows,
        "document_flags_preserved": True,
    }
