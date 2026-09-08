"""Native temperature contour creation on the interactive NX thread.

Callers must establish result freshness and retain the returned native result for
as long as the view is displayed. This adapter does not save simulation files.
"""


def create_temperature_view(session, sim, *, loadcase_index, iteration_index=0):
    """Create a contour in an empty postprocessing display and verify selection.

    Returns (JSON-compatible receipt, native result). The caller owns the result
    lifetime. Existing postviews are rejected so user-created views are preserved.
    """
    for value in (loadcase_index, iteration_index):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("Result indices must be nonnegative integers")
    import NXOpen.CAE as cae

    if session.Parts.BaseWork != sim or session.Parts.BaseDisplay != sim:
        raise ValueError("The selected SIM must be the work and display document")
    post, manager = session.Post, session.ResultManager
    if list(post.GetPostviewIds()):
        raise ValueError("Postviews already exist; inspect them before creating a new display")
    result = manager.CreateSolutionResult(sim.Simulation.ActiveSolution)
    params = view = actual = None
    retain_result = False
    try:
        cases = result.GetLoadcases()
        if loadcase_index >= len(cases):
            raise ValueError("Loadcase is outside this result")
        iterations = cases[loadcase_index].GetIterations()
        if iteration_index >= len(iterations):
            raise ValueError("Iteration is outside this loadcase")
        fields = [
            t
            for t in iterations[iteration_index].GetResultTypes()
            if t.Name == "Temperature - Nodal"
        ]
        if len(fields) != 1:
            raise ValueError("Selected iteration does not have a unique nodal temperature field")
        params = manager.CreateResultParameters()
        params.SetLoadcaseIteration(loadcase_index, iteration_index)
        params.SetGenericResultType(fields[0])
        params.SetResultComponent(cae.Result.Component.Scalar)
        params.SetUnit(sim.UnitCollection.FindObject("Celsius"))
        view = post.CreatePostviewForResult(0, result, False, params)
        post.PostviewRename(view, "MCP nodal temperature")
        post.PostviewUpdate(view)
        post.SetMainPostviewIdInActivePart(view)
        _, actual = post.GetResultForPostview(view)
        readback = {
            "loadcase_index": actual.GetLoadcase(),
            "iteration_index": actual.GetIteration(),
            "field": actual.GetGenericResultType().Name,
            "unit": actual.GetUnit().Name,
        }
        expected = {
            "loadcase_index": loadcase_index,
            "iteration_index": iteration_index,
            "field": "Temperature - Nodal",
            "unit": "Celsius",
        }
        if readback != expected or post.GetMainPostviewIdInActivePart() != view:
            raise ValueError("Postview selection or main-view readback differs from request")
        retain_result = True
        return {
            "postview_id": view,
            "selection": readback,
            "units": "degC",
            "reference_lifetime": "current NX session and result lifetime",
            "saved": False,
            "result_freshness": "caller_must_verify",
        }, result
    except Exception:
        if view is not None:
            post.PostviewDelete(view)
        raise
    finally:
        try:
            try:
                if actual is not None:
                    manager.DeleteResultParameters(actual)
            finally:
                if params is not None:
                    manager.DeleteResultParameters(params)
        finally:
            if not retain_result:
                manager.DeleteResult(result)


def set_temperature_range(session, postview_id, minimum_c, maximum_c):
    """Set a fixed Celsius range on a caller-owned nodal temperature view."""
    import math

    if (
        any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            for v in (minimum_c, maximum_c)
        )
        or minimum_c >= maximum_c
    ):
        raise ValueError("Supply a finite increasing Celsius range")
    import NXOpen.CAE as cae

    post = session.Post
    _, parameters = post.GetResultForPostview(postview_id)
    try:
        if (
            parameters.GetUnit().Name != "Celsius"
            or parameters.GetGenericResultType().Name != "Temperature - Nodal"
        ):
            raise ValueError("The selected view is not nodal temperature in Celsius")
    finally:
        session.ResultManager.DeleteResultParameters(parameters)
    before, _ = post.PostviewGetColorbar(postview_id)
    updated, _ = post.PostviewGetColorbar(postview_id)
    try:
        updated.Threshold = cae.Post.Threshold.Specified
        updated.ThresholdMinimum = float(minimum_c)
        updated.ThresholdMaximum = float(maximum_c)
        updated.Scale = cae.Post.Scale.Linear
        updated.NumberOfLevels = 10
        updated.AutomaticLevel = False
        updated.Position = cae.Post.Position.Right
        post.PostviewSetColorbar(postview_id, updated)
        post.PostviewUpdate(postview_id)
        actual, _ = post.PostviewGetColorbar(postview_id)
        if (
            actual.ThresholdMinimum != minimum_c
            or actual.ThresholdMaximum != maximum_c
            or actual.Threshold != cae.Post.Threshold.Specified
            or actual.Scale != cae.Post.Scale.Linear
        ):
            raise ValueError("Displayed legend differs from requested Celsius range")
        return {
            "minimum": actual.ThresholdMinimum,
            "maximum": actual.ThresholdMaximum,
            "units": "degC",
            "scale": "linear",
            "range_mode": "specified",
        }
    except Exception:
        post.PostviewSetColorbar(postview_id, before)
        post.PostviewUpdate(postview_id)
        raise


def select_temperature_iteration(session, postview_id, *, loadcase_index, iteration_index=0):
    """Change an owned temperature view, preserving its result and legend.

    Caller verifies view ownership and result freshness before this operation.
    Failed updates restore the original parameters; failed recovery is explicit.
    """
    for value in (loadcase_index, iteration_index):
        if type(value) is not int or value < 0:
            raise ValueError("Result indices must be nonnegative integers")
    post, manager = session.Post, session.ResultManager
    result, before = post.GetResultForPostview(postview_id)
    updated = actual = None
    changed = False
    try:
        if (
            before.GetUnit().Name != "Celsius"
            or before.GetGenericResultType().Name != "Temperature - Nodal"
        ):
            raise ValueError("The selected view is not nodal temperature in Celsius")
        cases = result.GetLoadcases()
        if loadcase_index >= len(cases):
            raise ValueError("Loadcase is outside this result")
        iterations = cases[loadcase_index].GetIterations()
        if iteration_index >= len(iterations):
            raise ValueError("Iteration is outside this loadcase")
        fields = [
            field
            for field in iterations[iteration_index].GetResultTypes()
            if field.Name == "Temperature - Nodal"
        ]
        if len(fields) != 1:
            raise ValueError("Selected iteration does not have a unique nodal temperature field")
        _, updated = post.GetResultForPostview(postview_id)
        updated.SetLoadcaseIteration(loadcase_index, iteration_index)
        updated.SetGenericResultType(fields[0])
        changed = True
        post.PostviewSetResult(postview_id, updated)
        post.PostviewUpdate(postview_id)
        actual_result, actual = post.GetResultForPostview(postview_id)
        selection = {
            "loadcase_index": actual.GetLoadcase(),
            "iteration_index": actual.GetIteration(),
            "field": actual.GetGenericResultType().Name,
            "unit": actual.GetUnit().Name,
        }
        if actual_result != result or selection != {
            "loadcase_index": loadcase_index,
            "iteration_index": iteration_index,
            "field": "Temperature - Nodal",
            "unit": "Celsius",
        }:
            raise ValueError("Postview readback differs from requested selection")
        return {"postview_id": postview_id, "selection": selection, "saved": False}
    except Exception as error:
        if changed:
            try:
                post.PostviewSetResult(postview_id, before)
                post.PostviewUpdate(postview_id)
            except Exception as recovery:
                raise RuntimeError(
                    f"Postview update failed: {error}; rollback failed: {recovery}; inspect view"
                ) from error
        raise
    finally:
        # These are parameter copies. Never unload the result backing the display.
        for parameters in (actual, updated, before):
            if parameters is not None:
                manager.DeleteResultParameters(parameters)
