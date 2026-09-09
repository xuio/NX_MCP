"""Read 90 native nodal temperatures and connectivity for the isolated benchmark."""


def run(executor):
    import shutil
    from pathlib import Path

    import NXOpen.CAE as cae

    from nx_mcp.simcenter.results import acquire_result

    sim = executor.session.Parts.BaseWork
    filename = Path(sim.FullPath).name
    assert filename in ("contact_numerical_r1.sim", "contact_explicit_r1.sim")
    prefix = "contact-explicit" if filename == "contact_explicit_r1.sim" else "contact"

    manager = executor.session.ResultManager
    result, owned = acquire_result(executor.session, sim)
    params = access = None
    try:
        assert result.AskNumNodes() == 90
        field = next(
            t
            for t in result.GetLoadcases()[0].GetIterations()[0].GetResultTypes()
            if t.Name == "Temperature - Nodal"
        )
        params = manager.CreateResultParameters()
        params.SetLoadcaseIteration(0, 0)
        params.SetGenericResultType(field)
        params.SetResultComponent(cae.Result.Component.Scalar)
        params.SetUnit(sim.UnitCollection.FindObject("Celsius"))
        access = manager.CreateResultAccess(result, params)
        indices = list(range(1, 91))
        coords = result.AskNodeCoordinates(indices)
        temperatures = access.AskNodalResult(indices)
        assert len(coords) == len(temperatures) == 90
        rows = []
        for i, coord, temp in zip(indices, coords, temperatures, strict=True):
            row = {
                "index": i,
                "label": result.AskNodeLabel(i),
                "xyz": [coord.X, coord.Y, coord.Z],
                "temperature_deg_c": temp,
            }
            if abs(coord.X - 10) < 1e-6:
                adjacent = result.AskNodeElements(i)
                nodes = {n for e in adjacent for n in result.AskElementNodes(e)}
                xs = [p.X for p in result.AskNodeCoordinates(sorted(nodes))]
                left = any(x < 10 - 1e-6 for x in xs)
                right = any(x > 10 + 1e-6 for x in xs)
                assert left != right, "Interface node connects both/neither physical block"
                row["interface_region"] = "heated" if left else "sink"
            rows.append(row)
        root = Path(sim.FullPath).parent
        log = root / (Path(sim.FullPath).stem + "-Conduction.log")
        shutil.copy2(
            log, Path(r"Z:\nx-mcp-integration\simcenter-discovery") / (prefix + "-numerical.log")
        )
        shutil.copy2(
            root / (Path(sim.FullPath).stem + "-Conduction.xml"),
            Path(r"Z:\nx-mcp-integration\simcenter-discovery") / (prefix + "-numerical.xml"),
        )
        return {
            "document_path": sim.FullPath,
            "nodes": rows,
            "result_coordinate_frame": "native result absolute coordinates; bounds checked against 20 x 10 x 10 mm fixture",
            "temperature_units": "degC",
            "log_path": str(log),
            "solver_launched": False,
        }
    finally:
        try:
            if access is not None:
                manager.DeleteResultAccess(access)
        finally:
            try:
                if params is not None:
                    manager.DeleteResultParameters(params)
            finally:
                if owned:
                    manager.DeleteResult(result)
