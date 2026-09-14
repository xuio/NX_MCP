"""Intent-oriented contracts for freeform geometry and imported face editing."""

from __future__ import annotations

from typing import Literal

READ_ONLY: set[str] = set()
NON_MODEL: set[str] = set()


def nx_divide_face_rectangle(face: str, rectangle: list[float], span_axis: Literal["X", "Y"] | None = None):
    """Create one native Divide Face rectangular footprint on a work-part horizontal planar solid face. rectangle=[xmin,ymin,xmax,ymax] uses absolute millimeter part coordinates; requires >0.01 mm clearance from bounding edges unless span_axis is set. With span_axis=X or Y, the rectangle must span that entire face-bounds axis within 0.005 mm, and its other axis stays strictly interior. This strip uses two transverse cuts and no known solver process. Native curves must yield exactly one additional face for an interior footprint or two for a spanning strip and one four-edge footprint matching bounds, with volume and total surface area unchanged within 1e-9 relative tolerance. Bounds preflight alone is not trimmed-face containment proof; native result checks reject invalid splits. Does not move or cut solid material. Reacquire topology IDs, inspect model health, and update FEM/thermal selections afterward. Does not save or solve. Normal model-operation undo rolls back failures; supply operation_id to avoid replay. Experimental until validated in the installed NX version."""


def nx_spline(
    points: list[list[float]],
    degree: int = 3,
    method: Literal["through_points", "poles"] = "through_points",
    periodic: bool = False,
    feature: str | None = None,
):
    """Create or edit an associative native 3D Studio Spline using work-part coordinates and units. Supply 2..1000 points, more than degree (1..7). through_points interpolates the points; poles uses a control polygon. feature is an existing Studio Spline feature ID to replace its defining points. No sketch plane is imposed. Returns feature and curve IDs, actual degree and periodicity. Editing replaces defining-point constraints; downstream geometry updates under the operation rollback mark."""


def nx_surface_mesh(primary: list[list[str]], cross: list[list[str]], tolerance: float = 0.001):
    """Create a native associative Through Curve Mesh sheet from intersecting primary/cross curve sections. Each direction requires 2..100 ordered sections, each a list of work-part curve IDs. Curves must form a compatible intersecting network; tolerance uses part units. Returns every resulting body. Existing nx_loft remains available for through-sketch sections."""


def nx_bridge_surface(
    first: str,
    second: str,
    continuity: Literal["G0", "G1", "G2"] = "G0",
    reverse_second: bool = False,
):
    """Bridge two work-part sheet edges with an associative native surface. G0 means position, G1 tangent and G2 curvature continuity against adjacent surfaces. Uses full edge ranges; reverse_second changes edge parameter alignment. Requested continuity is a builder constraint, not an independent quality certification."""


def nx_sew(target: str, tools: list[str], tolerance: float = 0.001, solid: bool = False):
    """Sew work-part sheet bodies associatively with native NX tolerances in part units. target and tools are distinct body IDs. Reject and roll back incomplete sewing. solid=True additionally requires an actual closed solid result; NX's fallback sheet is rejected. Inputs become feature parents; return all result bodies."""


def nx_thicken(faces: list[str], first_offset: float, second_offset: float = 0.0):
    """Thicken selected work-part sheet faces into a native solid feature between two different signed normal offsets in part units. Returns all result bodies. Face normals determine offset direction. Uses native exact offset behavior; failures roll back."""


def nx_edit_faces(
    faces: list[str],
    action: Literal["move", "offset", "replace", "heal"],
    distance: float | None = None,
    direction: list[float] | None = None,
    replacement: str | None = None,
):
    """Edit selected work-part faces, including imported solids, through native features. move requires signed distance and a work-part direction vector; offset requires signed normal distance; replace requires a replacement face ID; heal deletes selected faces and extends neighbors to close the gap. Other arguments are rejected. No partial delete is allowed. Reacquire topology IDs after edits and inspect model health. Lengths use part units."""


def nx_trim_sheet(body: str, boundaries: list[str], region_point: list[float], keep: bool = True):
    """Trim a work-part sheet with curve boundaries supplied as a native section. region_point=[x,y,z] identifies the region to keep (or discard when keep=False); all coordinates use work-part units. Curves must divide the target into valid regions. Exact native trim, associative feature, rollback on invalid boundaries."""


def nx_curve_analysis(curve: str, samples: int = 21):
    """Read native curve derivatives at 2..1000 equally spaced normalized parameters. Accepts a work-part curve ID. Returns positions, tangents, curvature (1/part-unit), radius, singular samples, and spline knots/poles when applicable. Sampling is not uniform arc length and does not certify global extrema."""


def nx_surface_continuity(
    first: str,
    second: str,
    position_tolerance: float = 0.001,
    angle_tolerance: float = 0.1,
    curvature_tolerance: float = 0.01,
    samples: int = 21,
):
    """Sample G0/G1/G2 continuity between two work-part boundary edges with one adjacent face each. Returns bidirectional native closest-point gaps, normal angles and curvature-tensor differences. Position tolerance uses part units, angle degrees, curvature 1/part-unit. 2..200 samples per edge; G2 uses the orientation-aligned shape-operator Frobenius norm. Unresolved singular samples prevent a G1/G2 pass. Sampled checks are not a global continuity certificate."""


READ_ONLY.update({"nx_curve_analysis", "nx_surface_continuity"})
