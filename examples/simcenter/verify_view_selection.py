def run(executor):
    import importlib

    import nx_mcp.simcenter.postprocessing as pp

    importlib.reload(pp)
    s = executor.session
    sim = s.Parts.BaseWork
    post = s.Post
    if "C-transient-fine-20260908" not in sim.FullPath:
        raise ValueError("Requires isolated benchmark")
    owned = getattr(executor, "_sim_post_result_handles", {})
    if list(post.GetPostviewIds()) != [2] or 2 not in owned:
        raise ValueError("Unexpected view ownership")
    result, params = post.GetResultForPostview(2)
    try:
        if result != owned[2]:
            raise ValueError("Result ownership mismatch")
        original = (params.GetLoadcase(), params.GetIteration())
    finally:
        s.ResultManager.DeleteResultParameters(params)
    receipts = []
    try:
        for index in [0, 20, 40]:
            receipts.append(pp.select_temperature_iteration(s, 2, loadcase_index=index))
        try:
            pp.select_temperature_iteration(s, 2, loadcase_index=999)
        except ValueError as ex:
            rejection = str(ex)
        else:
            raise ValueError("Invalid index accepted")
        _, p = post.GetResultForPostview(2)
        try:
            if p.GetLoadcase() != 40:
                raise ValueError("Invalid selection changed view")
        finally:
            s.ResultManager.DeleteResultParameters(p)
        c, _ = post.PostviewGetColorbar(2)
        if (c.ThresholdMinimum, c.ThresholdMaximum) != (20.0, 40.0):
            raise ValueError("Legend changed")
        return {
            "state": "verified",
            "selections": receipts,
            "invalid_index_rejection": rejection,
            "legend": [20, 40],
            "result_retained": True,
            "sim": sim.FullPath,
        }
    finally:
        pp.select_temperature_iteration(
            s, 2, loadcase_index=original[0], iteration_index=original[1]
        )
