"""Interior rectangular contact footprints on horizontal planar solid faces."""
import math

from nx_mcp.authoring import finite
from nx_mcp.runtime import NXToolError


def rectangle_points(rectangle, box, margin=0.01, span_axis=None):
    if not isinstance(rectangle, list) or len(rectangle) != 4:
        raise NXToolError('NX_INVALID_ARGUMENT', 'rectangle requires xmin,ymin,xmax,ymax')
    x0, y0, x1, y1 = [finite(v, 'rectangle') for v in rectangle]
    if x1 - x0 <= 2 * margin or y1 - y0 <= 2 * margin:
        raise NXToolError('NX_INVALID_ARGUMENT', 'Rectangle must have positive usable dimensions')
    if abs(box[5] - box[2]) > 0.001:
        raise NXToolError('NX_INVALID_GEOMETRY', 'Select a horizontal planar face')
    if span_axis not in (None, 'X', 'Y'):
        raise NXToolError('NX_INVALID_ARGUMENT', 'span_axis must be X, Y or omitted')
    inside_x = box[0] + margin < x0 < x1 < box[3] - margin
    inside_y = box[1] + margin < y0 < y1 < box[4] - margin
    spans_x = abs(x0 - box[0]) <= .005 and abs(x1 - box[3]) <= .005
    spans_y = abs(y0 - box[1]) <= .005 and abs(y1 - box[4]) <= .005
    valid = (inside_x and inside_y) if span_axis is None else (
        spans_x and inside_y if span_axis == 'X' else inside_x and spans_y)
    if not valid:
        raise NXToolError('NX_INVALID_GEOMETRY', 'Rectangle must be interior or span exactly the requested axis')
    z = (box[2] + box[5]) / 2
    return [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]]


def horizontal_face_box(box, point, normal):
    """Use the native plane, not padded UF bounds, to establish elevation."""
    point = [finite(v, 'plane point') for v in point]
    normal = [finite(v, 'plane normal') for v in normal]
    if len(point) != 3 or len(normal) != 3:
        raise NXToolError('NX_INVALID_GEOMETRY', 'Invalid native plane data')
    length = math.sqrt(sum(v * v for v in normal))
    if length == 0 or max(abs(normal[0]), abs(normal[1])) / length > 1e-8:
        raise NXToolError('NX_INVALID_GEOMETRY', 'Select a horizontal planar face')
    result = list(box)
    result[2] = result[5] = point[2]
    return result


def check_preservation(before, after, before_faces, after_faces, added_faces=1):
    if after_faces != before_faces + added_faces:
        raise NXToolError('NX_INVALID_GEOMETRY', 'Divide produced an unexpected face count',
                          details={'face_count_before': before_faces, 'face_count_after': after_faces,
                                   'expected_added_faces': added_faces})
    for key in ('volume_m3', 'area_m2'):
        if not math.isclose(before[key], after[key], rel_tol=1e-9, abs_tol=1e-14):
            raise NXToolError('NX_INVALID_GEOMETRY', 'Divide changed solid mass properties',
                              details={'quantity': key, 'before': before[key], 'after': after[key]})


def divide(executor, face, rectangle, span_axis=None):
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
    _, point, normal, _, _, _, _ = uf.Modeling.AskFaceData(target.Tag)
    box = horizontal_face_box(box, point, normal)
    points = rectangle_points(rectangle, box, span_axis=span_axis)
    body_ref = executor._reference(body, 'body', part, 'Divided body')['id']
    before = executor._mass_properties(body_ref)
    before_count = len(body.GetFaces())
    segments = [(i, (i + 1) % 4) for i in range(4)]
    if span_axis is not None:
        segments = [(0, 1), (3, 2)] if span_axis == 'X' else [(0, 3), (1, 2)]
    curves = []
    for start, end in segments:
        a, b = list(points[start]), list(points[end])
        if span_axis is not None:
            axis = 0 if span_axis == 'X' else 1
            a[axis], b[axis] = box[axis] - .01, box[axis + 3] + .01
        curves.append(part.Curves.CreateLine(nx.Point3d(*a), nx.Point3d(*b)))
    refs = [executor._reference(c, 'curve', part, 'Contact footprint')['id'] for c in curves]
    builder = executor._freeform_builder('CreateDividefaceBuilder')
    try:
        builder.FacesToDivide = executor._engineering_collector([target], 'Face')
        builder.SelectDividingObject.ToolOption = G.SelectDividingObjectBuilder.ToolType.Object
        sections = [refs]
        for section in sections:
            builder.SelectDividingObject.DividingObjectsList.Add(executor._curve_section(section))
        builder.ProjectionOption.ProjectDirectionMethod = G.ProjectionOptions.DirectionType.FaceNormal
        builder.ProjectCurvesThatLieOnFaceOption = True
        builder.ExtendOption = False
        builder.BlankOption = True
        builder.Tolerance = 0.001
        result = executor._freeform_commit(builder)
        after = executor._mass_properties(body_ref)
        faces = list(body.GetFaces())
        check_preservation(before, after, before_count, len(faces), 2 if span_axis else 1)
        expected = [points[0][0], points[0][1], points[0][2], points[2][0], points[2][1], points[2][2]]
        matches = []
        for candidate in faces:
            bounds = list(uf.ModlGeneral.AskBoundingBox(candidate.Tag))
            if all(abs(a - b) <= 0.005 for a, b in zip(bounds, expected)) and len(candidate.GetEdges()) == 4:
                matches.append(candidate)
        if len(matches) != 1:
            raise NXToolError('NX_INVALID_GEOMETRY', 'Cannot identify one rectangular footprint face')
        result.update(rectangle=rectangle, span_axis=span_axis, plane_z=points[0][2],
                      footprint_face=executor._reference(matches[0], 'face', part, 'Contact footprint'),
                      face_count_before=before_count, face_count_after=len(faces),
                      mass_properties_before=before, mass_properties_after=after,
                      validation='Verified expected face increase, matched footprint bounds/four edges, preserved volume and total area; run native health and remesh before thermal use')
        return result
    finally:
        builder.Destroy()
