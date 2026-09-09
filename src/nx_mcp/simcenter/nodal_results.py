"""Bounded native nodal temperatures; labels are result-local, not live mesh IDs."""

import math

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.results import acquire_result


def temperature_nodes(session, sim, *, loadcase_index=0, iteration_index=0, offset=0, limit=100):
    if (
        any(type(i) is not int or i < 0 for i in (loadcase_index, iteration_index, offset))
        or type(limit) is not int
        or not 1 <= limit <= 200
    ):
        raise NXToolError("NX_INVALID_ARGUMENT", "Indices/offset >= 0; limit must be 1..200")
    import NXOpen.CAE as cae

    manager = session.ResultManager
    result, owned = acquire_result(session, sim)
    params = access = None
    try:
        units = result.AskBasicUnits()
        if len(units) != 5 or units[1] is None or units[1].Name != "MilliMeter":
            raise NXToolError(
                "NX_SIM_UNITS", "Nodal coordinate extraction currently requires millimeter results"
            )
        loadcases = result.GetLoadcases()
        if loadcase_index >= len(loadcases):
            raise NXToolError("NX_SIM_RESULT_SELECTION", "loadcase_index is outside this result")
        iterations = loadcases[loadcase_index].GetIterations()
        if iteration_index >= len(iterations):
            raise NXToolError("NX_SIM_RESULT_SELECTION", "iteration_index is outside this loadcase")
        fields = [
            t
            for t in iterations[iteration_index].GetResultTypes()
            if t.Name == "Temperature - Nodal"
        ]
        if len(fields) != 1:
            raise NXToolError(
                "NX_SIM_RESULT_SELECTION", "Expected exactly one nodal temperature field"
            )
        total = result.AskNumNodes()
        if type(total) is not int or total < 0:
            raise NXToolError("NX_SIM_RESULT_DATA", "Invalid native node count")
        indices = list(range(offset + 1, min(offset + limit, total) + 1))
        rows = []
        if indices:
            params = manager.CreateResultParameters()
            params.SetLoadcaseIteration(loadcase_index, iteration_index)
            params.SetGenericResultType(fields[0])
            params.SetResultComponent(cae.Result.Component.Scalar)
            params.SetUnit(sim.UnitCollection.FindObject("Celsius"))
            access = manager.CreateResultAccess(result, params)
            coords = result.AskNodeCoordinates(indices)
            values = access.AskNodalResult(indices)
            if len(coords) != len(indices) or len(values) != len(indices):
                raise NXToolError("NX_SIM_RESULT_DATA", "Native nodal array cardinality differs")
            for index, point, value in zip(indices, coords, values, strict=True):
                xyz = [float(point.X), float(point.Y), float(point.Z)]
                value = float(value)
                if not all(math.isfinite(v) for v in [*xyz, value]):
                    raise NXToolError("NX_SIM_RESULT_DATA", "Nonfinite native nodal data")
                rows.append(
                    {
                        "index": index,
                        "label": int(result.AskNodeLabel(index)),
                        "coordinates": xyz,
                        "temperature": value,
                    }
                )
        return {
            "items": rows,
            "total": total,
            "next_offset": offset + len(rows) if offset + len(rows) < total else None,
            "loadcase_index": loadcase_index,
            "iteration_index": iteration_index,
            "field": "Temperature - Nodal",
            "units": "degC",
            "coordinate_units": "mm",
            "coordinate_frame": "native_result_coordinates",
            "result_freshness": "not_verified",
            "reference_lifetime": "Indices and labels belong to this result file revision; not live geometry or FEM references",
            "scope": "Native result nodes only; coupled nodal temperature may exclude fluid values; no region or averaging inference",
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
