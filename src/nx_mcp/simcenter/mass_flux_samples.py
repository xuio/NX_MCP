"""Bounded native nodal mass-flux samples, with explicit native area units."""

import math

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.nodal_availability import read_defined
from nx_mcp.simcenter.results import acquire_result


def mass_flux_samples(session, sim, *, node_labels, loadcase_index=0, iteration_index=0):
    if (
        any(type(i) is not int or i < 0 for i in (loadcase_index, iteration_index))
        or not isinstance(node_labels, list)
        or not 1 <= len(node_labels) <= 1024
        or any(type(i) is not int or i <= 0 for i in node_labels)
        or len(set(node_labels)) != len(node_labels)
    ):
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Use 1..1024 unique positive node labels and nonnegative indices"
        )
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
            t for t in iterations[iteration_index].GetResultTypes() if t.Name == "Mass Flux - Nodal"
        ]
        if len(fields) != 1:
            raise NXToolError(
                "NX_SIM_RESULT_SELECTION", "Expected exactly one nodal mass-flux field"
            )
        total = result.AskNumNodes()
        if type(total) is not int or total < 0:
            raise NXToolError("NX_SIM_RESULT_DATA", "Invalid native node count")
        indices = [result.AskNodeIndex(label) for label in node_labels]
        if any(type(i) is not int or not 1 <= i <= total for i in indices):
            raise NXToolError("NX_SIM_RESULT_DATA", "Requested result node label not found")
        if [result.AskNodeLabel(i) for i in indices] != node_labels:
            raise NXToolError("NX_SIM_RESULT_DATA", "Node label round trip differs")
        rows = []
        if indices:
            params = manager.CreateResultParameters()
            params.SetLoadcaseIteration(loadcase_index, iteration_index)
            params.SetGenericResultType(fields[0])
            params.SetResultComponent(cae.Result.Component.Scalar)
            unit = sim.UnitCollection.FindObject("MassFlux_Metric1")
            if unit.Symbol != "kg/sec-mm^2" or unit.Measure != "Mass Flux":
                raise NXToolError("NX_SIM_UNITS", "Unexpected native mass-flux unit definition")
            params.SetUnit(unit)
            if (
                params.GetUnit() != unit
                or params.GetResultComponent() != cae.Result.Component.Scalar
            ):
                raise NXToolError("NX_SIM_RESULT_DATA", "Mass-flux unit/component readback differs")
            access = manager.CreateResultAccess(result, params)
            coords = result.AskNodeCoordinates(indices)
            values = read_defined(access, indices)
            if len(coords) != len(indices) or len(values) != len(indices):
                raise NXToolError("NX_SIM_RESULT_DATA", "Native nodal array cardinality differs")
            for index, point, value in zip(indices, coords, values, strict=True):
                xyz = [float(point.X), float(point.Y), float(point.Z)]
                if not all(math.isfinite(v) for v in xyz):
                    raise NXToolError("NX_SIM_RESULT_DATA", "Nonfinite native nodal data")
                rows.append(
                    {
                        "index": index,
                        "label": int(result.AskNodeLabel(index)),
                        "coordinates": xyz,
                        "mass_flux": value,
                        "defined": value is not None,
                    }
                )
        return {
            "items": rows,
            "total": total,
            "sample_count": len(rows),
            "loadcase_index": loadcase_index,
            "iteration_index": iteration_index,
            "field": "Mass Flux - Nodal",
            "units": "kg/(s*mm^2)",
            "coordinate_units": "mm",
            "coordinate_frame": "native_result_coordinates",
            "result_freshness": "not_verified",
            "reference_lifetime": "Indices and labels belong to this result file revision; not live geometry or FEM references",
            "sign_convention": "native scalar; not independently established",
            "scope": "Native nodal mass-flux values; undefined nodes are null, never zero-filled. Result-local labels require coordinate validation. No face mapping, integration, conservation or cooling acceptance claim.",
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
