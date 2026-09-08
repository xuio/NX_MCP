"""Native pressure extrema from observed Simcenter 2606 element-nodal fields."""

import math

from nx_mcp.simcenter.results import acquire_result


def pressure_extrema(session, sim, *, field="pressure", loadcase_index=0, iteration_index=0):
    import NXOpen.CAE as cae

    names = {
        "pressure": "Pressure - Element-Nodal",
        "total_pressure": "Total Pressure - Element-Nodal",
    }
    if field not in names:
        raise ValueError("field must be pressure or total_pressure")
    for value in (loadcase_index, iteration_index):
        if type(value) is not int or value < 0:
            raise ValueError("Result indices must be nonnegative integers")
    if session.Parts.BaseWork != sim or not isinstance(sim, cae.SimPart):
        raise ValueError("Activate the selected SIM before extracting pressure")
    manager = session.ResultManager
    result, owned = acquire_result(session, sim)
    params = access = None
    try:
        loadcases = result.GetLoadcases()
        if loadcase_index >= len(loadcases):
            raise ValueError("Loadcase index outside result")
        iterations = loadcases[loadcase_index].GetIterations()
        if iteration_index >= len(iterations):
            raise ValueError("Iteration index outside loadcase")
        matches = [
            t for t in iterations[iteration_index].GetResultTypes() if t.Name == names[field]
        ]
        if len(matches) != 1:
            raise ValueError("Expected one native element-nodal pressure field")
        params = manager.CreateResultParameters()
        params.SetLoadcaseIteration(loadcase_index, iteration_index)
        params.SetGenericResultType(matches[0])
        params.SetResultComponent(cae.Result.Component.Scalar)
        params.SetUnit(sim.UnitCollection.FindObject("PressurePascals"))
        if params.GetUnit() != sim.UnitCollection.FindObject("PressurePascals"):
            raise ValueError("Native pressure result unit readback differs")
        access = manager.CreateResultAccess(result, params)
        location, minimum, maximum, min_id, max_id, min_sub, max_sub = access.AskMinMaxLocation()
        if not math.isfinite(minimum) or not math.isfinite(maximum) or minimum > maximum:
            raise ValueError("Invalid native pressure extrema")
        return {
            "field": names[field],
            "units": "Pa",
            "minimum": minimum,
            "maximum": maximum,
            "native_location": str(location),
            "minimum_native_id": min_id,
            "maximum_native_id": max_id,
            "minimum_native_sub_id": min_sub,
            "maximum_native_sub_id": max_sub,
            "node_count": result.AskNumNodes(),
            "loadcase_index": loadcase_index,
            "iteration_index": iteration_index,
            "result_freshness": "not_verified",
            "pressure_reference": "native_solution_reference",
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
