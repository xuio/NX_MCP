"""Reconcile native table-reference keys without modifying the coupled fixture."""


def run(executor):
    import time
    import NXOpen.UF as uf

    started = time.monotonic()
    parts = list(executor.session.Parts)
    before = {int(p.Tag): bool(p.IsModified) for p in parts}
    sim = next(
        p
        for p in parts
        if "E-coupled-mcp-20260908-r1" in p.FullPath and p.FullPath.endswith(".sim")
    )
    solution = sim.Simulation.ActiveSolution
    pt = solution.PropertyTable
    native = uf.UFSession.GetUFSession()
    names = [pt.GetPropertyNameByIndex(i) for i in range(pt.GetPropertyCount())]
    rows = []
    for key in (
        "Thermal Parameters",
        "Thermal Solution Parameters",
        "Coupled Solution Parameters",
        "Flow Solution Parameters",
        "Flow Surface Parameters",
        "Thermal-Flow Output Requests",
    ):
        row = {"key": key, "enumerated": key in names}
        for label, getter in (
            ("uf_tag", lambda: int(native.Sf.SolutionAskPropertyNx(solution.Tag, key))),
            ("base_type", lambda: str(pt.GetBasePropertyType(key))),
            ("reference", lambda: pt.GetNamedPropertyTablePropertyValue(key)),
        ):
            try:
                value = getter()
                row[label] = (
                    (
                        {
                            "tag": int(value.Tag),
                            "name": value.Name,
                            "descriptor": value.DescriptorType,
                        }
                        if value is not None
                        else None
                    )
                    if label == "reference"
                    else value
                )
            except Exception as error:
                row[label + "_error"] = {
                    "type": type(error).__name__,
                    "nx_code": getattr(error, "ErrorCode", None),
                }
        rows.append(row)
    assert before == {int(p.Tag): bool(p.IsModified) for p in executor.session.Parts}
    return {
        "path": sim.FullPath,
        "references": rows,
        "all_tables": [
            {"name": t.Name, "descriptor": t.DescriptorType, "tag": int(t.Tag)}
            for t in sim.ModelingObjectPropertyTables
        ],
        "document_flags_preserved": True,
        "elapsed_seconds": time.monotonic() - started,
    }
