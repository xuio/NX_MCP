"""Read solid collector assignments and bind subsequent edits to inspected state."""

import hashlib
import json

from nx_mcp.runtime import NXToolError


def state_hash(state):
    return hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def inspect_collector(fem, collector, reference, units):
    row = {
        "collector": reference(collector, "mesh_collector", fem, "collector"),
        "native_type": collector.CollectorNeutralType,
        "coordinate_frame": "part_absolute",
        "length_units": units,
    }
    if collector.CollectorNeutralType != "Solid":
        return {**row, "assignment_inspection": "unsupported_collector_type"}
    try:
        table = collector.ElementPropertyTable.GetNamedPropertyTablePropertyValue(
            "Solid Property"
        ).PropertyTable
        assignment = table.GetPhysicalMaterialPropertyValue("material")
        try:
            material = assignment.Material
            row["material"] = (
                reference(material, "material", material.OwningPart, "material")
                if material is not None
                else None
            )
            row["material_inherited"] = bool(assignment.MaterialInherited)
        finally:
            assignment.Dispose()
        selector = table.GetIntegerPropertyValue("material orientation type")
        frame = table.GetCoordinateSystemPropertyValue("material orientation")
        orientation = {"native_selector": selector, "stored_frame": None}
        if frame is not None:
            matrix, origin = frame.Orientation.Element, frame.Origin
            orientation["stored_frame"] = {
                "origin": [origin.X, origin.Y, origin.Z],
                "axes_in_part_absolute": [
                    [matrix.Xx, matrix.Xy, matrix.Xz],
                    [matrix.Yx, matrix.Yy, matrix.Yz],
                    [matrix.Zx, matrix.Zy, matrix.Zz],
                ],
                "native_tag": int(frame.Tag),
            }
        orientation["interpretation"] = (
            "default_frame_stored_frame_ignored"
            if selector == 0
            else "Cartesian"
            if selector == 1
            else "unsupported_selector"
        )
        row["orientation"] = orientation
        row["state_sha256"] = state_hash(row)
        row["state_scope"] = (
            "collector_identity_assignment_and_stored_frame_not_material_properties"
        )
    except Exception as error:
        row.pop("state_sha256", None)
        row["inspection_error"] = {
            "status": "read_failed",
            "nx_code": getattr(error, "ErrorCode", None),
        }
    return row


def inspect_collectors(fem, reference, units, offset=0, limit=20):
    if (
        isinstance(offset, bool)
        or not isinstance(offset, int)
        or offset < 0
        or isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= 100
    ):
        raise NXToolError("NX_INVALID_ARGUMENT", "offset >= 0; limit must be 1..100")
    collectors = list(fem.BaseFEModel.MeshManager.GetMeshCollectors())
    return {
        "collectors": [
            inspect_collector(fem, c, reference, units) for c in collectors[offset : offset + limit]
        ],
        "total": len(collectors),
        "next_offset": offset + limit if offset + limit < len(collectors) else None,
        "paging_consistency": "live_collection_restart_after_mutation",
    }
