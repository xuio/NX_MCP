"""Bounded native element-nodal velocity samples; no averaging or live mesh IDs."""

import math

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.results import acquire_result


def velocity_samples(
    session, sim, *, element_labels, component="x", loadcase_index=0, iteration_index=0
):
    components = {"x": "X", "y": "Y", "z": "Z", "magnitude": "Magnitude"}
    if component not in components or any(
        type(i) is not int or i < 0 for i in (loadcase_index, iteration_index)
    ):
        raise NXToolError("NX_INVALID_ARGUMENT", "Select x/y/z/magnitude and nonnegative indices")
    if (
        not isinstance(element_labels, list)
        or not 1 <= len(element_labels) <= 1024
        or any(type(i) is not int or i <= 0 for i in element_labels)
        or len(set(element_labels)) != len(element_labels)
    ):
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Supply 1..1024 unique positive result-local element labels"
        )
    import NXOpen.CAE as cae

    manager = session.ResultManager
    result, owned = acquire_result(session, sim)
    params = access = None
    try:
        units = result.AskBasicUnits()
        if len(units) != 5 or units[1] is None or units[1].Name != "MilliMeter":
            raise NXToolError("NX_SIM_UNITS", "Requires millimeter result coordinates")
        cases = result.GetLoadcases()
        if loadcase_index >= len(cases):
            raise NXToolError("NX_SIM_RESULT_SELECTION", "Loadcase outside result")
        iterations = cases[loadcase_index].GetIterations()
        if iteration_index >= len(iterations):
            raise NXToolError("NX_SIM_RESULT_SELECTION", "Iteration outside loadcase")
        fields = [
            f
            for f in iterations[iteration_index].GetResultTypes()
            if f.Name == "Velocity - Element-Nodal"
        ]
        if len(fields) != 1:
            raise NXToolError(
                "NX_SIM_RESULT_SELECTION", "Expected one matching element-nodal velocity field"
            )
        total = result.AskNumElements()
        total_nodes = result.AskNumNodes()
        if any(type(n) is not int or n < 0 for n in (total, total_nodes)):
            raise NXToolError("NX_SIM_RESULT_DATA", "Invalid native result counts")
        indices = [result.AskElementIndex(label) for label in element_labels]
        if any(type(i) is not int or not 1 <= i <= total for i in indices):
            raise NXToolError("NX_SIM_RESULT_DATA", "Result element label not found")
        if [result.AskElementLabel(i) for i in indices] != element_labels:
            raise NXToolError("NX_SIM_RESULT_DATA", "Result element label round trip differs")
        params = manager.CreateResultParameters()
        params.SetLoadcaseIteration(loadcase_index, iteration_index)
        params.SetGenericResultType(fields[0])
        native_component = getattr(cae.Result.Component, components[component])
        params.SetResultComponent(native_component)
        if params.GetResultComponent() != native_component:
            raise NXToolError("NX_SIM_RESULT_DATA", "Velocity component readback differs")
        coordinate_system = cae.Result.CoordinateSystem.AbsoluteRectangular
        params.SetCoordinateSystem(coordinate_system)
        if params.GetCoordinateSystem() != coordinate_system:
            raise NXToolError("NX_SIM_RESULT_DATA", "Velocity coordinate-system readback differs")
        unit = sim.UnitCollection.FindObject("MilliMeterPerSecond")
        params.SetUnit(unit)
        if params.GetUnit() != unit:
            raise NXToolError("NX_SIM_UNITS", "Velocity unit readback differs")
        access = manager.CreateResultAccess(result, params)
        defined = list(access.IsResultDefined(indices))
        if len(defined) != len(indices) or any(type(v) is not bool for v in defined):
            raise NXToolError("NX_SIM_RESULT_DATA", "Element availability cardinality/type differs")
        rows = []
        count = 0
        for label, index, available in zip(element_labels, indices, defined, strict=True):
            nodes = list(result.AskElementNodes(index))
            if not 1 <= len(nodes) <= 32 or len(set(nodes)) != len(nodes):
                raise NXToolError("NX_SIM_RESULT_DATA", "Unsupported element connectivity")
            if any(type(i) is not int or not 1 <= i <= total_nodes for i in nodes):
                raise NXToolError("NX_SIM_RESULT_DATA", "Invalid result node index")
            count += len(nodes)
            points = result.AskNodeCoordinates(nodes)
            if len(points) != len(nodes):
                raise NXToolError("NX_SIM_RESULT_DATA", "Coordinate cardinality differs")
            samples = []
            for node, point in zip(nodes, points, strict=True):
                xyz = [float(point.X), float(point.Y), float(point.Z)]
                value = float(access.AskElementNodalResult(index, node)) if available else None
                if not all(math.isfinite(v) for v in xyz) or (
                    value is not None and not math.isfinite(value)
                ):
                    raise NXToolError("NX_SIM_RESULT_DATA", "Nonfinite velocity/coordinates")
                samples.append(
                    {
                        "node_index": node,
                        "node_label": int(result.AskNodeLabel(node)),
                        "coordinates": xyz,
                        "velocity": value,
                    }
                )
            rows.append(
                {
                    "element_index": index,
                    "element_label": label,
                    "defined": available,
                    "nodes": samples,
                }
            )
        return {
            "items": rows,
            "sample_count": count,
            "field": "Velocity - Element-Nodal",
            "component": component,
            "units": "mm/s",
            "coordinate_units": "mm",
            "coordinate_frame": "native_result_coordinates",
            "loadcase_index": loadcase_index,
            "iteration_index": iteration_index,
            "vector_coordinate_system": "absolute_rectangular",
            "result_freshness": "not_verified",
            "scope": "Unaveraged element-nodal scalar samples. Labels are result-local; prove coordinate/connectivity mapping before using input boundary selections. Undefined elements have null velocities. No profile, flux integration or convergence claim.",
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
