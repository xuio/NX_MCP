"""Public signatures and contracts for authoring/review tools."""

from __future__ import annotations

from typing import Any, Literal

READ_ONLY = {
    "nx_find_geometry",
    "nx_list_expressions",
    "nx_model_health",
    "nx_model_summary",
    "nx_resolve_geometry",
    "nx_recognize_holes",
    "nx_list_component_patterns",
    "nx_sketch_conflicts",
    "nx_feature_parameters",
}
NON_MODEL = {
    "nx_highlight_objects",
    "nx_save_presentation",
    "nx_inspection_report",
    "nx_preview_change",
}


def nx_find_geometry(
    owner: str | None = None,
    kind: Literal["face", "edge"] = "face",
    geometry_type: Literal["any", "plane", "cylinder", "circle", "line"] = "any",
    normal: list[float] | None = None,
    radius: float | None = None,
    near: list[float] | None = None,
    order: Literal["nearest", "highest", "lowest"] = "nearest",
    axis: Literal["X", "Y", "Z"] = "Z",
    tolerance: float = 0.001,
    offset: int = 0,
    limit: int = 50,
):
    """Find geometry within a body/feature/component or full assembly. Coordinates and radii use work-part units/frame. Nearest uses native BREP point-to-face/edge minimum distance and closest points; highest/lowest use conservative bounds centers. Returns a reusable geometric selector; resolve it explicitly after edits with nx_resolve_geometry. nearest requires near=[x,y,z]. Normal filter requires planar faces; tolerance is 1-dot for normals and absolute length for radii. Returns paginated candidates; never silently selects one."""


def nx_highlight_objects(objects: list[str]):
    """Preview candidate body/face/edge/curve/component references using native selection highlighting. Replaces MCP-owned highlights; clear with nx_clear_highlights. No persistent recoloring."""


def nx_list_expressions(name_contains: str | None = None, offset: int = 0, limit: int = 50):
    """Paginate work-part expressions, formulas, numeric values in expression units, editability and stored immediate dependencies. Names are case-sensitive. Non-numeric values are null. Conditional dependencies may be incomplete."""


def nx_set_expression(
    expression: str,
    formula: str,
    create: bool = False,
    units: Literal["unitless", "mm", "inch", "deg", "rad"] = "unitless",
):
    """Create a named Number expression or edit a local editable expression ID/name. Formula is NX expression syntax. Units apply only on creation; edits retain original units. Rebuild dependent features and roll back on errors. New name must be a simple identifier. Locked/interpart expressions are rejected."""


def nx_bind_parameter(
    feature: str, parameter: Literal["start", "end", "count", "spacing"], expression: str
):
    """Bind EXTRUDE start/end limits or PATTERN_FEATURE count/spacing to an existing Number expression. Native units/dimensional compatibility applies; failed updates roll back. Returns feature dependencies and expression read-back."""


def nx_model_health(scope: Literal["part", "assembly"] = "part", offset: int = 0, limit: int = 50):
    """Inspect native feature errors/warnings, suppression, unloaded prototype availability and UF body consistency. Assembly scope checks unique loaded unsuppressed prototypes. Does not force rebuild or certify design intent. Paginate issues; counts cover the whole query."""


def nx_rebuild_model():
    """Run native DoUpdate for pending changes and return model health. Update errors roll back this operation; does not force every already-current feature to regenerate."""


def nx_edit_sketch(sketch_id: str, operations: list[dict[str, Any]]):
    """Reopen an existing sketch for 1–100 atomic local edits; restore prior activation and return solver diagnostics. Points are local [x,y], angles degrees. Operations: {action:add_line,start,end}; {action:line,curve,start,end}; {action:arc,curve,center,radius,start_angle,end_angle}; {action:delete,object} for owned curve/constraint; {action:constraint,curve,type:fixed|horizontal|vertical}. Curve ownership is checked; another active sketch is rejected. Edit dimensional constraints through their expression IDs with nx_set_expression. Deleting or recreating constraints is explicit; no automatic constraint removal."""


def nx_component_action(
    component: str,
    action: Literal["rename", "suppress", "unsuppress", "remove", "replace"],
    name: str | None = None,
    part_path: str | None = None,
):
    """Edit an immediate child occurrence of the work assembly. rename requires name; replace requires existing workspace .prt part_path and replaces only this occurrence while retaining relationships. Other actions reject those fields. Suppression affects all arrangements. Checks unchanged placement; native errors roll back. Prototype files are not deleted by remove."""


def nx_pattern_components(component: str, direction: list[float], spacing: float, count: int):
    """Create 2–100 total occurrences including the seed at a positive pitch in work-part units along normalized direction. Seed must be an unsuppressed immediate child. Returns independent positioned occurrences, not a native associative pattern. Runs serially in one rollback transaction."""


def nx_set_camera(rotation: list[list[float]], origin: list[float], scale: float):
    """Set absolute NX viewport camera. rotation is right-handed orthonormal row-major 3x3 with columns NX view axes; origin is the view-space point centered in the viewport; scale is positive absolute NX scale. Work and display part must match. Returns actual camera."""


def nx_save_presentation(path: str):
    """Save camera, one active section, explicit appearance and loaded assembly body/component visibility into a new workspace JSON file. Includes per-face colors/transparency and journal locators. Does not save the CAD part. Excludes datum visibility, materials and inherited-override semantics."""


def nx_restore_presentation(path: str):
    """Restore a saved presentation in its original owner part. Preflight all journal references before mutation; stale references reject restoration. Geometry is unchanged, but display attributes can mark the part modified. Across topology revisions verify journal references still denote intended geometry."""


def nx_inspection_report(
    path: str,
    objects: list[str] | None = None,
    minimum_clearance: float = 0.0,
    max_pairs: int = 100,
    include_clear: bool = False,
    capture: bool = True,
    section_planes: list[dict[str, list[float]]] | None = None,
):
    """Create a new workspace ZIP containing HTML/JSON clearance results, checksums, native viewport PNG, up to eight flagged-pair close-ups and six section screenshots. section_planes entries require origin and normal in work-part coordinates. Restores temporary view/visibility/section changes. max_pairs caps native clearance work; report does not imply unchecked pairs are clear. Retrieve with nx_download_file."""


def nx_model_summary(
    section: Literal["overview", "components", "features", "expressions", "sketches"] = "overview",
    offset: int = 0,
    limit: int = 50,
):
    """Compact work-part summary: counts, bounds, native health and paginated assembly hierarchy, feature parents/parameters, expressions or sketch frames. Owned-body and occurrence counts are separate. Does not infer missing design dimensions."""


def nx_preview_change(operations: list[dict[str, Any]], capture: bool = True):
    """Temporarily apply 1–25 edits under a native checkpoint, return before/after bounds/volume/parameters/health and optional screenshot, then roll back before returning. Each entry has method and params. Supports nx_set_expression, nx_bind_parameter, nx_edit_feature, nx_edit_sketch, nx_set_component_transform and nx_reposition_component. Returned geometry IDs are stale after rollback. Preview is session-scoped and expires on intervening mutations or manual handoff."""


def nx_finish_preview(preview_id: str, action: Literal["accept", "discard"]):
    """Accept by atomically reapplying stored preview edits only if its part and mutation epoch are unchanged, or discard the stored plan. Preview already restored original geometry. Accepted edits remain unsaved and undoable. Stable operation_id prevents double application."""


# Nested operation schemas are published explicitly; embedded NX validates the
# same exact key sets before changing sketch geometry.
POINT2_SCHEMA = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}
SKETCH_OPERATION_SCHEMAS = []
_SKETCH_FIELDS: dict[str, dict[str, Any]] = {
    "add_line": {"start": POINT2_SCHEMA, "end": POINT2_SCHEMA},
    "line": {"curve": {"type": "string"}, "start": POINT2_SCHEMA, "end": POINT2_SCHEMA},
    "arc": {
        "curve": {"type": "string"},
        "center": POINT2_SCHEMA,
        "radius": {"type": "number", "exclusiveMinimum": 0},
        "start_angle": {"type": "number"},
        "end_angle": {"type": "number"},
    },
    "delete": {"object": {"type": "string"}},
    "constraint": {
        "curve": {"type": "string"},
        "type": {"type": "string", "enum": ["fixed", "horizontal", "vertical"]},
    },
}
for _action, _fields in _SKETCH_FIELDS.items():
    SKETCH_OPERATION_SCHEMAS.append(
        {
            "type": "object",
            "properties": {"action": {"const": _action}, **_fields},
            "required": ["action", *_fields],
            "additionalProperties": False,
        }
    )


def nx_resolve_geometry(selector: dict[str, Any], tie_tolerance: float = 0.001):
    """Re-evaluate a selector returned by nx_find_geometry in its original owner part. Returns a fresh face/edge ID only if the best match is unique within tie_tolerance in part units. No match, ambiguous rank or stale owner is an explicit error. Survives edits/reopen by geometric rule, not a promise of persistent topological identity. Whole-part rules may select new geometry that now satisfies the rule."""


def nx_recognize_holes(owner: str | None = None, offset: int = 0, limit: int = 50):
    """Recognize inward cylindrical BREP faces and return bore radius, axis, angular coverage and coaxial groups in work-part coordinates/units. Partial cylindrical faces are identified explicitly. Does not infer threads, manufacturing features, blind/through termination or fit classes."""


def nx_native_component_pattern(component: str, direction: list[float], spacing: float, count: int):
    """Create a native associative linear component pattern with 2–100 total occurrences including one immediate unsuppressed seed. Direction is normalized in work-part coordinates; spacing is positive part units. Native builder and pattern members are read back. Rollback on update/count failure. Existing nx_pattern_components retains independent-instance behavior."""


def nx_edit_component_pattern(pattern: str, spacing: float | None = None, count: int | None = None):
    """Edit pitch and/or total count (including seed, 2–100) of a native associative linear component pattern by ID. Read back native parameters and member poses. Unsupported native pattern types are rejected before editing."""


def nx_list_component_patterns():
    """Enumerate native work-assembly component patterns, IDs, native type, association, count/pitch expressions for linear patterns and member occurrence poses. Independent instances are not patterns."""


def nx_sketch_dimension(
    sketch_id: str,
    curve: str,
    dimension_type: Literal["length", "horizontal", "vertical", "radius", "diameter"],
    value: float,
    origin: list[float],
    reference: bool = False,
):
    """Create a native sketch dimension: line endpoint length/horizontal/vertical distance or arc radius/diameter. Value is positive part units; annotation origin is local [x,y]. Driving dimensions use value, reference dimensions measure existing geometry and require value matching it within 0.001 part units. Returns the associated expression for later formula editing. Atomic and restores activation; conflicting solver state rolls back."""


def nx_sketch_relation(
    sketch_id: str,
    curve1: str,
    curve2: str,
    relation: Literal[
        "parallel", "perpendicular", "equal_length", "equal_radius", "concentric", "coincident"
    ],
    point1: Literal["start", "end", "center"] | None = None,
    point2: Literal["start", "end", "center"] | None = None,
):
    """Create a persistent two-curve sketch relation using the installed solver; modern sketches keep curve1 stationary and move curve2 as needed. Geometric residual is checked before success. Parallel/perpendicular/equal_length require lines; equal_radius/concentric require arcs; coincident requires explicit start/end (line) or center (arc) for each curve. Other relations reject point arguments. Ownership and types checked before mutation. Conflicting solver results roll back; no constraints are automatically removed."""


def nx_sketch_conflicts(sketch_id: str, max_checks: int = 20):
    """Diagnose an over/inconsistently constrained sketch by temporary single-constraint removal and native solver reevaluation, restoring each trial. max_checks 1–50 bounds serial NX work. Returns constraints whose removal relieves the conflict, statuses, checked/total and completeness. Also checks contradictory horizontal/vertical persistent relations on a nonzero line because NX solver status can omit them. This is not a minimal conflicting set; multiple independent conflicts may produce no single-removal relief. No geometry or constraints retained from trials."""


def nx_feature_parameters(feature: str):
    """List native expressions owned by a feature, with IDs, formulas, units, editability and dependencies. Parameter names are NX expression names, not inferred semantic labels. Applicable to feature types exposing GetExpressions."""


def nx_set_feature_parameters(feature: str, values: dict[str, str]):
    """Atomically set 1–25 owned, editable local Number expressions on a feature. Keys are expression IDs or exact names from nx_feature_parameters; values are NX formulas in existing expression units. Preflight ownership/editability; native update failures roll back all changes. Can bind to another expression by its name. Does not alter unexposed builder options or locked/interpart expressions."""
