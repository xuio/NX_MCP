"""Read loaded thermal/flow/coupled ambient representations without setters."""


def run(executor):
    import time

    import NXOpen.CAE as cae

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    started = time.monotonic()
    parts = list(executor.session.Parts)
    before = {int(p.Tag): bool(p.IsModified) for p in parts}
    rows = []
    found = set()
    for sim in parts:
        if not isinstance(sim, cae.SimPart):
            continue
        for solution in sim.Simulation.Solutions:
            kind = solution.AnalysisType
            if kind not in ("Thermal", "Flow", "Coupled Thermal-Flow") or kind in found:
                continue
            found.add(kind)
            table = solution.PropertyTable
            row = {
                "path": sim.FullPath,
                "solution": solution.Name,
                "analysis_type": kind,
                "properties": [],
            }
            for key in ("Fluid Temperature", "Absolute Pressure"):
                value = {"name": key, "property_type": str(table.GetPropertyType(key))}
                for method in (
                    "GetScalarWithDataPropertyValue",
                    "GetScalarFieldWrapperPropertyValue",
                    "GetScalarFieldPropertyValue",
                ):
                    try:
                        obj = getattr(table, method)(key)
                        if method == "GetScalarWithDataPropertyValue":
                            value[method] = {
                                "value": obj[0],
                                "units": obj[1].Name if obj[1] else None,
                            }
                        else:
                            item = (
                                {"type": type(obj).__name__, "tag": int(obj.Tag)}
                                if obj
                                else {"value": None}
                            )
                            if obj and hasattr(obj, "GetExpression"):
                                expression = obj.GetExpression()
                                item["expression"] = (
                                    expression.RightHandSide if expression else None
                                )
                            if obj and hasattr(obj, "GetFieldExpressionString"):
                                item["field_expression"] = obj.GetFieldExpressionString()
                            value[method] = item
                    except Exception as error:
                        value[method] = {
                            "error": str(error),
                            "nx_code": getattr(error, "ErrorCode", None),
                        }
                row["properties"].append(value)
            rows.append(row)
    after = {int(p.Tag): bool(p.IsModified) for p in parts}
    return {
        "rows": rows,
        "elapsed_seconds": time.monotonic() - started,
        "document_flags_preserved": before == after,
        "changed_flags": [tag for tag in before if before[tag] != after.get(tag)],
        "solver_launched": False,
    }
