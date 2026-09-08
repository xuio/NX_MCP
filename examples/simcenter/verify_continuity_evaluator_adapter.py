"""Native curved sheet-boundary acceptance; no solver or production geometry."""


def run(executor):
    import importlib
    import json
    from pathlib import Path

    import NXOpen as nx

    from nx_mcp.evaluator_bridge import EvaluatorBridge, decode_result
    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    module = importlib.reload(importlib.import_module("nx_mcp.freeform"))
    root = executor.workspace.resolve("ui-benchmarks/F4-continuity-20260908-r1")
    if root.exists():
        raise ValueError("Inspect retained acceptance before retry")
    root.mkdir()
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    executor._create_part(str(root / "f4_continuity_r1.prt"), "mm")
    part = executor._work_part()
    inspector = EvaluatorBridge(executor.session)
    edges = []
    for z in (0.0, 10.0):
        builder = part.Features.CreateCylinderBuilder(None)
        try:
            builder.Origin = nx.Point3d(0.0, 0.0, z)
            builder.Direction = nx.Vector3d(0.0, 0.0, 1.0)
            builder.Diameter.RightHandSide = "20"
            builder.Height.RightHandSide = "10"
            feature = builder.CommitFeature()
        finally:
            builder.Destroy()
        faces = [
            f
            for f in feature.GetBodies()[0].GetFaces()
            if f.SolidFaceType == nx.Face.FaceType.Cylindrical
        ]
        assert len(faces) == 1
        builder = part.Features.CreateExtractFaceBuilder(None)
        try:
            builder.Type = builder.ExtractType.Face
            builder.Associative = True
            builder.HideOriginal = False
            builder.ObjectToExtract.Add(faces[0])
            sheet = builder.CommitFeature().GetBodies()[0]
        finally:
            builder.Destroy()
        assert not sheet.IsSolidBody
        matches = []
        for edge in sheet.GetEdges():
            data = inspector.inspect(edge, 2)
            if data["kind"] == "arc" and abs(data["center"][2] - 10) < 1e-8:
                matches.append(edge)
        assert len(matches) == 1
        edges.append(matches[0])
    refs = [executor._reference(e, "edge", part, "curved boundary")["id"] for e in edges]
    before = list(executor.session.Execute(inspector.path, "EvaluatorHelper", "Audit", []))
    report = module.FreeformMixin._surface_continuity(executor, *refs, samples=21)
    assert report["checks"] == {"G0": True, "G1": True, "G2": True}
    assert report["sample_count"] == 42 and report["unresolved_count"] == 0
    failure = list(
        executor.session.Execute(
            inspector.path, "EvaluatorHelper", "InspectChecked", [edges[0], 2, True]
        )
    )
    try:
        decode_result(failure, 2)
    except NXToolError as error:
        assert error.code == "NX_EVALUATOR_OPERATION_FAILED"
    else:
        raise AssertionError("Injected evaluator failure was accepted")
    after = list(executor.session.Execute(inspector.path, "EvaluatorHelper", "Audit", []))
    assert after[1] - before[1] == 3 and after[2] - before[2] == 3 and after[3] == 0
    current = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    assert all(current.get(path) == flag for path, flag in flags.items())
    result = {
        "passed": True,
        "report": report,
        "references": refs,
        "helper_audit_before": before,
        "helper_audit_after": after,
        "injected_failure": failure,
        "unrelated_modified_flags_preserved": True,
        "solver_launched": False,
    }
    (root / "verification.json").write_text(json.dumps(result, indent=2))
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\continuity-evaluator-adapter.json").write_text(
        json.dumps(result, indent=2)
    )
    return result
