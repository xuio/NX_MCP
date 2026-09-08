"""Explicit Cartesian solid-material frames for the verified NX 2606 adapter."""

import math

from nx_mcp.runtime import NXToolError


def validate_frame(origin_mm, x_axis, y_axis):
    vectors = []
    for vector in (origin_mm, x_axis, y_axis):
        if (
            not isinstance(vector, (list, tuple))
            or len(vector) != 3
            or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in vector
            )
        ):
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "Frame origin and axes require three finite numbers each"
            )
        vectors.append([float(v) for v in vector])
    origin, x, y = vectors

    def dot(a, b):
        return sum(i * j for i, j in zip(a, b, strict=True))

    if abs(dot(x, x) - 1) > 1e-8 or abs(dot(y, y) - 1) > 1e-8 or abs(dot(x, y)) > 1e-8:
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Material axes must be unit length and perpendicular"
        )
    z = [x[1] * y[2] - x[2] * y[1], x[2] * y[0] - x[0] * y[2], x[0] * y[1] - x[1] * y[0]]
    return origin, x, y, z


def assign_frame(
    session, nx, fem, collector, *, origin_mm, x_axis, y_axis, expected_type, expected_frame
):
    """Compare-and-set a solid frame, returning actual axes and an undo mark; no save."""
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    origin, x, y, z = validate_frame(origin_mm, x_axis, y_axis)
    require_solver_idle()
    if fem.PartUnits != nx.BasePart.Units.Millimeters or collector.CollectorNeutralType != "Solid":
        raise NXToolError(
            "NX_SIM_UNSUPPORTED", "Frame assignment requires a millimeter FEM solid collector"
        )
    if collector not in list(fem.BaseFEModel.MeshManager.GetMeshCollectors()):
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Collector does not belong to the selected FEM")
    table = collector.ElementPropertyTable.GetNamedPropertyTablePropertyValue(
        "Solid Property"
    ).PropertyTable
    if (
        table.GetIntegerPropertyValue("material orientation type") != expected_type
        or table.GetCoordinateSystemPropertyValue("material orientation") != expected_frame
    ):
        raise NXToolError("NX_SIM_REVISION_MISMATCH", "Material frame changed since inspection")
    _, status = session.Parts.SetDisplay(fem, False, False)
    if status:
        status.Dispose()
    session.Parts.SetWork(fem)
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP Cartesian material frame")
    try:
        frame = fem.CoordinateSystems.CreateCoordinateSystem(
            nx.Point3d(*origin), nx.Vector3d(*x), nx.Vector3d(*y)
        )
        table.SetCoordinateSystemPropertyValue("material orientation", frame)
        # Native selector probe verified 1 exports Cartesian axes; 0 omits the frame.
        table.SetIntegerPropertyValue("material orientation type", 1)
        if (
            table.GetIntegerPropertyValue("material orientation type") != 1
            or table.GetCoordinateSystemPropertyValue("material orientation") != frame
        ):
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Material frame assignment did not persist"
            )
        m, o = frame.Orientation.Element, frame.Origin
        actual = [[m.Xx, m.Xy, m.Xz], [m.Yx, m.Yy, m.Yz], [m.Zx, m.Zy, m.Zz]]
        for requested, observed in zip([origin, x, y, z], [[o.X, o.Y, o.Z], *actual], strict=True):
            if any(abs(a - b) > 1e-8 for a, b in zip(requested, observed, strict=True)):
                raise NXToolError("NX_SIM_READBACK_MISMATCH", "Committed material axes differ")
        return (
            frame,
            {
                "origin_mm": [o.X, o.Y, o.Z],
                "axes_in_part_absolute": actual,
                "native_selector": 1,
                "coordinate_system": "Cartesian",
                "saved": False,
                "solver_verified": False,
            },
            mark,
        )
    except Exception as error:
        outcome = "rolled_back"
        try:
            session.UndoToMark(mark, None)
            session.DeleteUndoMark(mark, None)
        except Exception:
            outcome = "partial"
        raise NXToolError(
            "NX_SIM_MATERIAL_FRAME_FAILED",
            "Material frame assignment failed",
            nx_code=getattr(error, "ErrorCode", None),
            details={"mutation_outcome": outcome, "cause_code": getattr(error, "code", None)},
        ) from error
