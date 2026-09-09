"""Native result-group nodal summaries; no CAD or volume-weighting inference."""

import hashlib
import json
import math

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.nodal_availability import read_defined
from nx_mcp.simcenter.results import acquire_result


def temperature_regions(
    session,
    sim,
    *,
    dimension="3d",
    loadcase_index=0,
    iteration_index=0,
    offset=0,
    limit=10,
    maximum_entities=200000,
):
    if (
        dimension not in ("3d", "2d")
        or any(type(i) is not int or i < 0 for i in (loadcase_index, iteration_index, offset))
        or type(limit) is not int
        or not 1 <= limit <= 50
        or type(maximum_entities) is not int
        or not 1 <= maximum_entities <= 1000000
    ):
        raise NXToolError(
            "NX_INVALID_ARGUMENT",
            "dimension 3d|2d; indices/offset >=0; limit 1..50; maximum_entities 1..1000000",
        )
    import NXOpen.CAE as cae

    manager = session.ResultManager
    result, owned = acquire_result(session, sim)
    params = access = None
    try:
        units = result.AskBasicUnits()
        if len(units) != 5 or units[1] is None or units[1].Name != "MilliMeter":
            raise NXToolError(
                "NX_SIM_UNITS", "Region coordinates currently require millimeter results"
            )
        node_count, element_count = result.AskNumNodes(), result.AskNumElements()
        if any(type(n) is not int or n < 0 for n in (node_count, element_count)):
            raise NXToolError("NX_SIM_RESULT_DATA", "Invalid result counts")
        if node_count + element_count > maximum_entities:
            raise NXToolError(
                "NX_SIM_INSPECTION_LIMIT",
                "Whole-result node/element count exceeds the inspection budget",
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
            raise NXToolError("NX_SIM_RESULT_SELECTION", "Expected one nodal temperature field")
        kind = (
            cae.Result.GroupContainer.ThreeDimensional
            if dimension == "3d"
            else cae.Result.GroupContainer.TwoDimensional
        )
        total = result.AskNumGroupsInContainer(kind)
        if type(total) is not int or total < 0:
            raise NXToolError("NX_SIM_RESULT_DATA", "Invalid result-group count")
        rows = []
        visited = 0
        if offset < total:
            params = manager.CreateResultParameters()
            params.SetLoadcaseIteration(loadcase_index, iteration_index)
            params.SetGenericResultType(fields[0])
            params.SetResultComponent(cae.Result.Component.Scalar)
            params.SetUnit(sim.UnitCollection.FindObject("Celsius"))
            access = manager.CreateResultAccess(result, params)
        for group_index in range(offset, min(offset + limit, total)):
            elements = list(result.AskNumElementsOfGroup(kind, group_index))
            if (
                not elements
                or len(elements) > element_count
                or len(set(elements)) != len(elements)
                or any(type(e) is not int or not 1 <= e <= element_count for e in elements)
            ):
                raise NXToolError("NX_SIM_RESULT_DATA", "Invalid or empty group membership")
            nodes = set()
            for element in elements:
                connectivity = list(result.AskElementNodes(element))
                if not connectivity or any(
                    type(n) is not int or not 1 <= n <= node_count for n in connectivity
                ):
                    raise NXToolError("NX_SIM_RESULT_DATA", "Invalid group element connectivity")
                nodes.update(connectivity)
            indices = sorted(nodes)
            visited += len(elements) + len(indices)
            if visited > maximum_entities:
                raise NXToolError(
                    "NX_SIM_INSPECTION_LIMIT",
                    "Selected group traversal exceeds the inspection budget",
                )
            # Keep native array requests small even for a large selected group.
            values = []
            all_coordinates = []
            for start in range(0, len(indices), 200):
                selected = indices[start : start + 200]
                coords = result.AskNodeCoordinates(selected)
                temps = read_defined(access, selected)
                if len(coords) != len(selected) or len(temps) != len(selected):
                    raise NXToolError(
                        "NX_SIM_RESULT_DATA", "Native region array cardinality differs"
                    )
                for index, point, value in zip(selected, coords, temps, strict=True):
                    xyz = [float(point.X), float(point.Y), float(point.Z)]
                    if not all(math.isfinite(v) for v in xyz):
                        raise NXToolError("NX_SIM_RESULT_DATA", "Nonfinite region result")
                    all_coordinates.append(xyz)
                    if value is None:
                        continue
                    values.append(
                        {
                            "index": index,
                            "label": int(result.AskNodeLabel(index)),
                            "coordinates": xyz,
                            "temperature": value,
                        }
                    )
            minimum = min(values, key=lambda r: r["temperature"]) if values else None
            maximum = max(values, key=lambda r: r["temperature"]) if values else None
            rows.append(
                {
                    "group_index": group_index,
                    "dimension": dimension,
                    "element_count": len(elements),
                    "node_count": len(indices),
                    "defined_node_count": len(values),
                    "undefined_node_count": len(indices) - len(values),
                    "membership_sha256": hashlib.sha256(
                        json.dumps([sorted(elements), indices], separators=(",", ":")).encode()
                    ).hexdigest(),
                    "minimum": minimum,
                    "maximum": maximum,
                    "arithmetic_nodal_mean": math.fsum(
                        r["temperature"] / len(values) for r in values
                    )
                    if values
                    else None,
                    "bounds": {
                        "minimum": [min(xyz[i] for xyz in all_coordinates) for i in range(3)],
                        "maximum": [max(xyz[i] for xyz in all_coordinates) for i in range(3)],
                    },
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
            "mean_semantics": "Unweighted arithmetic mean over unique nodes with defined field values within each group; undefined values are excluded and counted, empty summaries are null; shared nodes may belong to multiple groups; not area/volume weighted",
            "extrema_semantics": "First node in increasing result-index order at each extremum",
            "selection_semantics": "Native dimension/group indices bound to the result file revision; not inferred CAD components or persistent semantic names",
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
