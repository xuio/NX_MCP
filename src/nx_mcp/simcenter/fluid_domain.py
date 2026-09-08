"""Native, explicitly bounded fluid-domain construction on the NX UI thread."""

import math

from nx_mcp.runtime import NXToolError


def inspect_region_geometry(fem, bodies):
    """Read native polygon-body measurements; this does not certify topology."""
    import NXOpen as nx
    import NXOpen.UF as uf

    if fem.PartUnits != nx.BasePart.Units.Millimeters:
        raise NXToolError("NX_SIM_UNITS", "This adapter requires a millimeter FEM")
    if not bodies or any(body.OwningPart != fem for body in bodies):
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Select fluid bodies owned by the FEM")
    sf = uf.UFSession.GetUFSession().Sf
    measurements = []
    for body in bodies:
        bounds = list(sf.BodyAskBoundingBox(body.Tag))
        volume, centroid = sf.BodyAskVolumeAndCentroid(body.Tag)
        centroid = list(centroid)
        if (
            len(bounds) != 6
            or len(centroid) != 3
            or any(not math.isfinite(v) for v in [*bounds, volume, *centroid])
            or volume <= 0
            or any(bounds[i] >= bounds[i + 3] for i in range(3))
        ):
            raise NXToolError("NX_SIM_INVALID_REGION", "Invalid native fluid-body measurements")
        measurements.append({"bounds_mm": bounds, "volume_mm3": volume, "centroid_mm": centroid})
    return {
        "bodies": measurements,
        "body_count": len(measurements),
        "coordinate_frame": "FEM_absolute",
        "volume_semantics": "individual polygon bodies; overlaps are not removed",
        "topology_validation": "not_performed",
    }


def create_wrapped_region(session, fem, bodies, point_mm, resolution_mm, name):
    """Wrap around an interior seed and create a body, not a CFD volume mesh.

    Callers must independently validate geometry, connectivity and interfaces
    before using the result. No gap closing is requested. No files are saved.
    """
    import NXOpen as nx
    import NXOpen.CAE as cae

    if session.Parts.BaseWork != fem or not isinstance(fem, cae.FemPart):
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected FEM first")
    if fem.PartUnits != nx.BasePart.Units.Millimeters:
        raise NXToolError("NX_SIM_UNITS", "This adapter requires a millimeter FEM")
    if not isinstance(point_mm, (list, tuple)) or len(point_mm) != 3:
        raise NXToolError("NX_INVALID_ARGUMENT", "Supply a three-coordinate interior point in mm")
    if (
        any(type(v) not in (int, float) or not math.isfinite(v) for v in [*point_mm, resolution_mm])
        or resolution_mm <= 0
    ):
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Point coordinates must be finite and resolution positive"
        )
    if not bodies or any(body.OwningPart != fem for body in bodies):
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Select bodies owned by the active FEM")
    if not isinstance(name, str) or not name.strip():
        raise NXToolError("NX_INVALID_ARGUMENT", "Supply a nonempty region name")
    domains = fem.BaseFEModel.FluidDomains
    before = {int(recipe.Tag) for recipe in domains}
    if any(recipe.GetName() == name for recipe in domains):
        raise NXToolError("NX_SIM_NAME_CONFLICT", "A fluid-domain recipe already uses this name")
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP fluid-domain wrap")
    builder = None
    try:
        builder = domains.CreateBuilder(None)
        builder.GeometrySelection.Add(bodies)
        builder.InteriorExteriorType = cae.FluidDomainBuilder.IntExtType.Point
        builder.InteriorPoint = fem.Points.CreatePoint(nx.Point3d(*[float(v) for v in point_mm]))
        builder.OutputType = cae.FluidDomainBuilder.OutputOptionsType.BodyOnly
        builder.Resolution.RightHandSide = str(float(resolution_mm))
        builder.ClosingSize.RightHandSide = "0.0"
        builder.AcousticWrapEnabled = False
        builder.SnapToSourceBoundaries = True
        builder.DoExportMeshToSolver = False
        builder.CommitFluidDomain()
        builder.Destroy()
        builder = None
        created = [recipe for recipe in domains if int(recipe.Tag) not in before]
        if len(created) != 1:
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Expected exactly one fluid-domain recipe"
            )
        recipe = created[0]
        recipe.SetName(name)
        domains.UpdateRecipe(recipe)
        result_bodies = list(recipe.GetFluidBodies())
        if not result_bodies:
            raise NXToolError("NX_SIM_EMPTY_REGION", "No fluid body was generated")
        reader = domains.CreateBuilder(recipe)
        try:
            if reader.InteriorPoint is None:
                raise NXToolError("NX_SIM_READBACK_MISMATCH", "Fluid seed point was not retained")
            point = reader.InteriorPoint.Coordinates
            actual_point = [point.X, point.Y, point.Z]
            if any(abs(a - b) > 1e-9 for a, b in zip(actual_point, point_mm, strict=True)):
                raise NXToolError(
                    "NX_SIM_READBACK_MISMATCH", "Fluid seed coordinates differ after commit"
                )
            actual = {
                "interior_point_mm": actual_point,
                "coordinate_frame": "FEM_absolute",
                "resolution_mm": reader.Resolution.Value,
                "closing_size_mm": reader.ClosingSize.Value,
                "output_type": str(reader.OutputType),
                "source_count": len(reader.GeometrySelection.GetArray()),
            }
            if (
                actual["resolution_mm"] != resolution_mm
                or actual["closing_size_mm"] != 0
                or reader.OutputType != cae.FluidDomainBuilder.OutputOptionsType.BodyOnly
                or {int(b.Tag) for b in reader.GeometrySelection.GetArray()}
                != {int(b.Tag) for b in bodies}
            ):
                raise NXToolError(
                    "NX_SIM_READBACK_MISMATCH", "Fluid-domain settings differ after commit"
                )
        finally:
            reader.Destroy()
        return {
            "recipe": recipe,
            "bodies": result_bodies,
            "body_count": len(result_bodies),
            "name": recipe.GetName(),
            "settings": actual,
            "volume_mesh_created": False,
            "geometry_validation": "required",
            "geometry": inspect_region_geometry(fem, result_bodies),
            "saved": False,
        }
    except Exception as error:
        try:
            if builder is not None:
                builder.Destroy()
                builder = None
            session.UndoToMark(mark, None)
            if {int(recipe.Tag) for recipe in domains} != before:
                raise RuntimeError("Fluid-domain recipe set differs after rollback")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError(
                "NX_SIM_ROLLBACK_FAILED",
                "Fluid-domain creation failed with incomplete recovery",
                details={
                    "operation_error": str(error),
                    "recovery_error": str(recovery),
                    "mutation_outcome": "partial",
                },
            ) from error
        raise
    finally:
        if builder is not None:
            builder.Destroy()
