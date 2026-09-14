"""Interior rectangular contact footprints on horizontal planar solid faces."""
import math

from nx_mcp.authoring import finite
from nx_mcp.runtime import NXToolError


def rectangle_points(rectangle, box, margin=0.01):
    if not isinstance(rectangle, list) or len(rectangle) != 4:
        raise NXToolError('NX_INVALID_ARGUMENT', 'rectangle requires xmin,ymin,xmax,ymax')
    x0, y0, x1, y1 = [finite(v, 'rectangle') for v in rectangle]
    if x1 - x0 <= 2 * margin or y1 - y0 <= 2 * margin:
        raise NXToolError('NX_INVALID_ARGUMENT', 'Rectangle must have positive usable dimensions')
    if abs(box[5] - box[2]) > 0.001:
        raise NXToolError('NX_INVALID_GEOMETRY', 'Select a horizontal planar face')
    if not (box[0] + margin < x0 < x1 < box[3] - margin
            and box[1] + margin < y0 < y1 < box[4] - margin):
        raise NXToolError('NX_INVALID_GEOMETRY', 'Rectangle must lie strictly inside face bounds')
    z = (box[2] + box[5]) / 2
    return [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]]


def check_preservation(before, after, before_faces, after_faces):
    if after_faces != before_faces + 1:
        raise NXToolError('NX_INVALID_GEOMETRY', 'Divide must produce exactly one additional face')
    for key in ('volume_m3', 'area_m2'):
        if not math.isclose(before[key], after[key], rel_tol=1e-9, abs_tol=1e-14):
            raise NXToolError('NX_INVALID_GEOMETRY', 'Divide changed solid mass properties',
                              details={'quantity': key, 'before': before[key], 'after': after[key]})


def divide(executor, face, rectangle):
    import NXOpen.UF as UF
    import NXOpen.GeometricUtilities as G
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    if executor._units() != 'mm':
        raise NXToolError('NX_UNSUPPORTED_UNITS', 'Select a millimeter work part')
    target = executor._engineering_owned(face, 'face')
    nx = executor.nxopen
    if target.SolidFaceType != nx.Face.FaceType.Planar:
        raise NXToolError('NX_INVALID_GEOMETRY', 'Select a planar face')
    body = target.GetBody()
    if not body.IsSolidBody:
        raise NXToolError('NX_NOT_SOLID', 'Select a solid face')
    part = executor._work_part()
    uf = UF.UFSession.GetUFSession()
    box = list(uf.ModlGeneral.AskBoundingBox(target.Tag))
    points = rectangle_points(rectangle, box)
    body_ref = executor._reference(body, 'body', part, 'Divided body')['id']
    before = executor._mass_properties(body_ref)
    before_count = len(body.GetFaces())
    curves = [part.Curves.CreateLine(nx.Point3d(*points[i]), nx.Point3d(*points[(i + 1) % 4]))
              for i in range(4)]
    refs = [executor._reference(c, 'curve', part, 'Contact footprint')['id'] for c in curves]
    builder = executor._freeform_builder('CreateDividefaceBuilder')
    try:
        builder.FacesToDivide = executor._engineering_collector([target], 'Face')
        builder.SelectDividingObject.ToolOption = G.SelectDividingObjectBuilder.ToolType.Object
        builder.SelectDividingObject.DividingObjectsList.Add(executor._curve_section(refs))
        builder.ProjectionOption.ProjectDirectionMethod = G.ProjectionOptions.DirectionType.FaceNormal
        builder.ProjectCurvesThatLieOnFaceOption = True
        builder.ExtendOption = False
        builder.BlankOption = True
        builder.Tolerance = 0.001
        result = executor._freeform_commit(builder)
        after = executor._mass_properties(body_ref)
        faces = list(body.GetFaces())
        check_preservation(before, after, before_count, len(faces))
        expected = [points[0][0], points[0][1], points[0][2], points[2][0], points[2][1], points[2][2]]
        matches = []
        for candidate in faces:
            bounds = list(uf.ModlGeneral.AskBoundingBox(candidate.Tag))
            if all(abs(a - b) <= 0.005 for a, b in zip(bounds, expected)) and len(candidate.GetEdges()) == 4:
                matches.append(candidate)
        if len(matches) != 1:
            raise NXToolError('NX_INVALID_GEOMETRY', 'Cannot identify one rectangular footprint face')
        result.update(rectangle=rectangle, plane_z=points[0][2],
                      footprint_face=executor._reference(matches[0], 'face', part, 'Contact footprint'),
                      face_count_before=before_count, face_count_after=len(faces),
                      mass_properties_before=before, mass_properties_after=after,
                      validation='One added face, matched footprint bounds/four edges, preserved volume and total area; run native health and remesh before thermal use')
        return result
    finally:
        builder.Destroy()
