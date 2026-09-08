"""Native scalar-temperature extraction; NXOpen objects stay on the NX thread."""


def acquire_result(session, sim):
    """Return a result plus ownership, preserving results used by visible views."""
    manager = session.ResultManager
    displayed = []
    post = getattr(session, "Post", None)
    if post is not None and not getattr(session, "IsBatch", False):
        for view in post.GetPostviewIds():
            result, parameters = post.GetResultForPostview(view)
            try:
                displayed.append(result)
            finally:
                manager.DeleteResultParameters(parameters)
    result = manager.CreateSolutionResult(sim.Simulation.ActiveSolution)
    return result, not any(result == existing for existing in displayed)


def temperature_extrema(session, sim, *, loadcase_index=0, iteration_index=0, location="nodal"):
    """Read a selected loadcase/iteration's nodal temperature in explicit Celsius.

    This does not certify result freshness. Callers must verify the model/job
    revision before using the values as engineering evidence.
    """
    for name, value in (("loadcase_index", loadcase_index), ("iteration_index", iteration_index)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")

    fields = {
        "nodal": "Temperature - Nodal",
        "elemental": "Temperature - Elemental",
        "element_nodal": "Temperature - Element-Nodal",
    }
    if location not in fields:
        raise ValueError("location must be nodal, elemental or element_nodal")

    import NXOpen.CAE as cae

    manager = session.ResultManager
    result, owned = acquire_result(session, sim)
    params = access = None
    try:
        loadcases = result.GetLoadcases()
        if loadcase_index >= len(loadcases):
            raise ValueError("loadcase_index is outside this result")
        iterations = loadcases[loadcase_index].GetIterations()
        if iteration_index >= len(iterations):
            raise ValueError("iteration_index is outside this loadcase")
        types = iterations[iteration_index].GetResultTypes()
        matches = [t for t in types if t.Name == fields[location]]
        if len(matches) != 1:
            raise ValueError("Expected exactly one selected temperature field in this iteration")
        params = manager.CreateResultParameters()
        params.SetLoadcaseIteration(loadcase_index, iteration_index)
        params.SetGenericResultType(matches[0])
        params.SetResultComponent(cae.Result.Component.Scalar)
        params.SetUnit(sim.UnitCollection.FindObject("Celsius"))
        access = manager.CreateResultAccess(result, params)
        native_location, minimum, maximum, min_id, max_id, min_sub, max_sub = (
            access.AskMinMaxLocation()
        )
        return {
            "field": matches[0].Name,
            "field_location": location,
            "loadcase_index": loadcase_index,
            "iteration_index": iteration_index,
            "units": "degC",
            "minimum": minimum,
            "maximum": maximum,
            "native_location": str(native_location),
            "minimum_native_id": min_id,
            "maximum_native_id": max_id,
            "minimum_native_sub_id": min_sub,
            "maximum_native_sub_id": max_sub,
            "node_count": result.AskNumNodes(),
            "result_freshness": "not_verified",
            "reference_lifetime": "indices apply only to this result revision",
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


def iteration_inventory(session, sim, *, offset=0, limit=50):
    """Page native field/time metadata; do not infer time from a loadcase index."""
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a nonnegative integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ValueError("limit must be an integer from 1 to 200")
    import NXOpen.CAE as cae

    manager = session.ResultManager
    result, owned = acquire_result(session, sim)
    try:
        rows = []
        total = 0
        for li, loadcase in enumerate(result.GetLoadcases()):
            for ii, iteration in enumerate(loadcase.GetIterations()):
                position = total
                total += 1
                if not offset <= position < offset + limit:
                    continue
                values = []
                for kind in iteration.GetValueTypes():
                    dtype = iteration.GetValueDataType(kind)
                    if dtype == cae.BaseIteration.IterationValueDataType.Double:
                        value = iteration.GetDoubleValueOfType(kind)
                    elif dtype == cae.BaseIteration.IterationValueDataType.Integer:
                        value = iteration.GetIntegerValueOfType(kind)
                    else:
                        raise ValueError(f"Unsupported iteration value data type: {dtype}")
                    unit = iteration.GetUnitOfType(kind)
                    values.append(
                        {
                            "kind": "time"
                            if kind == cae.BaseIteration.IterationValueType.Time
                            else "other",
                            "native_type": str(kind),
                            "value": value,
                            "native_unit": unit.Name if unit else None,
                        }
                    )
                rows.append(
                    {
                        "loadcase_index": li,
                        "iteration_index": ii,
                        "values": values,
                        "fields": [field.Name for field in iteration.GetResultTypes()],
                    }
                )
        return {
            "items": rows,
            "total": total,
            "next_offset": offset + len(rows) if offset + len(rows) < total else None,
            "result_freshness": "not_verified",
            "reference_lifetime": "indices apply only to this result revision",
        }
    finally:
        if owned:
            manager.DeleteResult(result)
