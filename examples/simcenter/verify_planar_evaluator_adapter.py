"""Native DXF acceptance on isolated mm/inch sketches; public handler stays unchanged."""


def run(executor):
    import importlib
    import json
    import math
    from pathlib import Path

    import NXOpen as nx

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    module = importlib.reload(importlib.import_module("nx_mcp.planar_dxf"))
    importlib.reload(importlib.import_module("nx_mcp.evaluator_bridge"))
    root = executor.workspace.resolve("ui-benchmarks/F4-planar-adapter-20260908-r3")
    if root.exists():
        raise ValueError("Inspect retained DXF acceptance before retry")
    root.mkdir()
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    cases = []

    def record():
        (root / "verification.json").write_text(json.dumps({"cases": cases}, indent=2))

    for units, factor in (("mm", 1.0), ("inch", 25.4)):
        executor._create_part(str(root / ("f4_r3_curves_" + units + ".prt")), units)
        part = executor._work_part()
        sketch = executor._create_sketch("XY", "Evaluator acceptance")["object"]["id"]
        executor._sketch_line(sketch, {"x": 0, "y": 0}, {"x": 2, "y": 0})
        executor._sketch_arc_legacy(5, 5, 1, 0, 360, sketch)
        executor._sketch_arc_legacy(9, 5, 1, 0, 90, sketch)
        executor._finish_sketch(sketch)
        for reverse in (False, True):
            target = root / (units + ("_reverse" if reverse else "_normal") + ".dxf")
            before = bool(part.IsModified)
            result = module.PlanarDxfMixin._export_planar_dxf(
                executor,
                sketch,
                str(target),
                x_axis=[1, 0, 0],
                y_axis=[0, -1 if reverse else 1, 0],
            )
            assert result["entity_counts"] == {"LINE": 1, "CIRCLE": 1, "ARC": 1}
            entities = {e["type"]: e for e in result["entities"]}
            assert math.isclose(entities["LINE"]["end"][0], 2 * factor, abs_tol=1e-8)
            assert math.isclose(entities["CIRCLE"]["radius"], factor, abs_tol=1e-8)
            assert math.isclose(entities["ARC"]["start_angle"], 270 if reverse else 0, abs_tol=1e-8)
            assert math.isclose(entities["ARC"]["end_angle"], 0 if reverse else 90, abs_tol=1e-8)
            assert part.IsModified == before
            assert target.stat().st_size == result["size"]
            cases.append({"units": units, "reverse": reverse, "result": result, "passed": True})
            record()
        # An actual ellipse must be rejected, never tessellated into DXF segments.
        ellipse_sketch = executor._create_sketch("XY", "Unsupported ellipse")["object"]["id"]
        owner = executor.objects.resolve(ellipse_sketch, expected_kind="sketch")
        ellipse = part.Curves.CreateEllipse(
            nx.Point3d(0.0, 0.0, 0.0),
            nx.Vector3d(1.0, 0.0, 0.0),
            nx.Vector3d(0.0, 1.0, 0.0),
            2.0,
            1.0,
            0.0,
            2 * math.pi,
        )
        owner.AddGeometry(ellipse, nx.Sketch.InferConstraintsOption.InferNoConstraints)
        executor._finish_sketch(ellipse_sketch)
        rejected = root / (units + "_unsupported.dxf")
        try:
            module.PlanarDxfMixin._export_planar_dxf(executor, ellipse_sketch, str(rejected))
        except NXToolError as error:
            assert error.code == "NX_UNSUPPORTED_GEOMETRY"
            assert not rejected.exists()
            cases.append({"units": units, "unsupported_ellipse_rejected": True, "code": error.code})
            record()
        else:
            raise ValueError("Unsupported ellipse was accepted")
    after = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    assert all(after.get(path) == flag for path, flag in flags.items())
    result = {
        "cases": cases,
        "passed": True,
        "unrelated_modified_flags_preserved": True,
        "solver_launched": False,
    }
    (root / "verification.json").write_text(json.dumps(result, indent=2))
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\planar-evaluator-adapter.json").write_text(
        json.dumps(result, indent=2)
    )
    return result
