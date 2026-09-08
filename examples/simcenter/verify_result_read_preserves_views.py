"""Verify result-query cleanup preserves existing native pressure postviews."""


def run(executor):
    from nx_mcp.simcenter.flow_results import pressure_extrema

    session = executor.session
    sim = session.Parts.BaseWork
    if not sim.FullPath.endswith(r"F-input-export-20260908-r2\flow_input_r2.sim"):
        raise ValueError("Activate the isolated duct SIM")
    post = session.Post
    before = set(post.GetPostviewIds())
    main = post.GetMainPostviewIdInActivePart()
    if len(before) < 2:
        raise ValueError("Requires existing pressure postviews")
    fields = {}
    for view in before:
        result, params = post.GetResultForPostview(view)
        try:
            fields[view] = {
                "result_tag": int(result.Tag),
                "field": params.GetGenericResultType().Name,
            }
        finally:
            session.ResultManager.DeleteResultParameters(params)
    values = pressure_extrema(session, sim)
    try:
        pressure_extrema(session, sim, loadcase_index=10000)
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid loadcase accepted")
    assert set(post.GetPostviewIds()) == before
    assert post.GetMainPostviewIdInActivePart() == main
    for view in before:
        result, params = post.GetResultForPostview(view)
        try:
            assert fields[view] == {
                "result_tag": int(result.Tag),
                "field": params.GetGenericResultType().Name,
            }
        finally:
            session.ResultManager.DeleteResultParameters(params)
    return {
        "existing_views": fields,
        "main": main,
        "pressure": values,
        "successful_and_failed_reads_preserved_views": True,
        "solver_launched": False,
    }
