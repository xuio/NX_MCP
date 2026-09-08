def run(executor):
    import json, math
    from pathlib import Path
    import NXOpen as nx

    dll = r"Z:\nx-mcp-integration\simcenter-discovery\NxMcpEvaluator_r2.dll"
    session = executor.session
    before_flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    part = next(
        p
        for p in session.Parts
        if isinstance(p, nx.Part)
        and p.FullPath.startswith(str(executor.workspace.root))
        and list(p.Bodies)
    )
    body = list(part.Bodies)[0]
    edge = list(body.GetEdges())[0]

    def call(method, args):
        return list(session.Execute(dll, "EvaluatorHelper", method, args))

    before = call("Audit", [])
    sample = call("Inspect", [edge, 5, False])
    after_success = call("Audit", [])
    failure = None
    try:
        call("Inspect", [edge, 5, True])
    except Exception as error:
        failure = {"nx_code": getattr(error, "ErrorCode", None), "message": str(error)}
    after_failure = call("Audit", [])
    vertices = edge.GetVertices()
    endpoints = [[p.X, p.Y, p.Z] for p in vertices]
    sampled = [sample[15:18], sample[-3:]]
    # Compare edge endpoints in either natural orientation, using part-native units.
    distance = lambda a, b: math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
    endpoint_error = min(
        max(distance(sampled[0], endpoints[0]), distance(sampled[1], endpoints[1])),
        max(distance(sampled[0], endpoints[1]), distance(sampled[1], endpoints[0])),
    )
    result = {
        "part": part.FullPath,
        "edge_journal": edge.JournalIdentifier,
        "sample": sample,
        "before": before,
        "after_success": after_success,
        "failure": failure,
        "after_failure": after_failure,
        "endpoint_error_part_units": endpoint_error,
        "modified_flags_preserved": before_flags
        == {p.FullPath: bool(p.IsModified) for p in session.Parts},
        "python_pointer_accessed": False,
    }
    result["passed"] = (
        bool(failure)
        and after_success[1] - before[1] == 1
        and after_success[2] - before[2] == 1
        and after_failure[1] - after_success[1] == 1
        and after_failure[2] - after_success[2] == 1
        and after_failure[3] == 0
        and endpoint_error < 1e-8
        and result["modified_flags_preserved"]
    )
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\evaluator-helper-geometry.json").write_text(
        json.dumps(result, indent=2)
    )
    return result
