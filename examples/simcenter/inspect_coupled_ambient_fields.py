"""Compare documented scalar-field and wrapper readers without mutation."""


def run(executor):
    import time

    sim = executor.session.Parts.BaseWork
    if "E-environment-wrapper-20260908-r1" not in sim.FullPath:
        raise ValueError("Unexpected SIM")
    before = {int(p.Tag): bool(p.IsModified) for p in executor.session.Parts}
    table = sim.Simulation.ActiveSolution.PropertyTable
    rows = []
    started = time.monotonic()
    for key in ("Absolute Pressure", "Fluid Temperature", "Radiative Environment Temperature"):
        row = {"key": key}
        for label, method in [
            ("scalar_field", table.GetScalarFieldPropertyValue),
            ("wrapper", table.GetScalarFieldWrapperPropertyValue),
        ]:
            try:
                obj = method(key)
                value = (
                    {"type": type(obj).__name__, "tag": int(obj.Tag)} if obj else {"value": None}
                )
                if obj and hasattr(obj, "GetFieldExpressionString"):
                    value["expression"] = obj.GetFieldExpressionString()
                    value["units"] = (
                        obj.FieldExpressionUnits.Name if obj.FieldExpressionUnits else None
                    )
                if obj and hasattr(obj, "GetExpression"):
                    expr = obj.GetExpression()
                    value["expression"] = expr.RightHandSide if expr else None
                    value["units"] = expr.Units.Name if expr and expr.Units else None
                row[label] = value
            except Exception as error:
                row[label] = {
                    "error": type(error).__name__,
                    "nx_code": getattr(error, "ErrorCode", None),
                }
        rows.append(row)
    after = {int(p.Tag): bool(p.IsModified) for p in executor.session.Parts}
    return {
        "rows": rows,
        "document_flags_preserved": before == after,
        "changed_flags": [tag for tag in before if before[tag] != after.get(tag)],
        "elapsed_seconds": time.monotonic() - started,
    }
