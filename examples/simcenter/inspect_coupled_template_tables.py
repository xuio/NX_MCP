"""Inspect isolated copies of shipped metric simulation templates; never solve."""


def run(executor):
    import shutil
    import time
    from pathlib import Path

    started = time.monotonic()
    root = executor.workspace.resolve("ui-benchmarks/E-template-inspection-20260908-r1")
    root.mkdir(parents=True, exist_ok=True)
    original_parts = list(executor.session.Parts)
    before = {int(p.Tag): bool(p.IsModified) for p in original_parts}
    rows = []
    for name in ("SimMultiPhysicsMetric.sim", "SimThermalFlowMetric.sim"):
        target = root / name
        source = Path(r"C:\Program Files\Siemens\Designcenter2606\SIMULATION\templates") / name
        if not target.exists():
            shutil.copy2(source, target)
        part = next((p for p in executor.session.Parts if p.FullPath == str(target)), None)
        load_warnings = []
        if part is None:
            part, status = executor.session.Parts.OpenBase(str(target))
            try:
                load_warnings = [
                    {"part": status.GetPartName(i), "description": status.GetStatusDescription(i)}
                    for i in range(status.NumberUnloadedParts)
                ]
            finally:
                status.Dispose()
        row = {
            "path": part.FullPath,
            "solutions": [],
            "tables": [],
            "load_warnings": load_warnings,
            "solve_ready": False,
        }
        for table in part.ModelingObjectPropertyTables:
            row["tables"].append(
                {
                    "name": table.Name,
                    "descriptor": table.DescriptorType,
                    "language": table.LanguageName,
                    "solver": table.SolverName,
                }
            )
        for solution in part.Simulation.Solutions:
            props = solution.PropertyTable
            keys = [props.GetPropertyNameByIndex(i) for i in range(props.GetPropertyCount())]
            refs = []
            for key in keys:
                if not any(word in key for word in ("Parameters", "Output Requests")):
                    continue
                try:
                    value = props.GetNamedPropertyTablePropertyValue(key)
                    refs.append({"key": key, "descriptor": value.DescriptorType if value else None})
                except Exception as error:
                    refs.append({"key": key, "nx_code": getattr(error, "ErrorCode", None)})
            row["solutions"].append(
                {
                    "name": solution.Name,
                    "solver": solution.SolverType,
                    "analysis": solution.AnalysisType,
                    "references": refs,
                }
            )
        rows.append(row)
    assert before == {int(p.Tag): bool(p.IsModified) for p in original_parts}
    return {
        "templates": rows,
        "original_document_flags_preserved": True,
        "solver_launched": False,
        "elapsed_seconds": time.monotonic() - started,
    }
