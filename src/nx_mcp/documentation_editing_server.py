"""Drawing inspection and precise native documentation edits."""

from typing import Literal

READ_ONLY = {"nx_list_drawings", "nx_list_annotations"}
NON_MODEL = {"nx_activate_drawing"}


def nx_list_drawings():
    """List work-part drawing sheets and views with typed IDs, dimensions, scale and active-sheet state. No activation or mutation."""


def nx_activate_drawing(drawing: str | None = None):
    """Open an owned drawing sheet, or return to modeling when drawing=null. Work/display parts must match and no sketch may be active. Preserves unrelated parts."""


def nx_list_annotations(offset: int = 0, limit: int = 100):
    """Enumerate native notes, PMI, BOMs, balloons and explosion traces in the work part. Returns subtype, typed references, position/text where available, and managed-refresh metadata. Paged, maximum 200 items per call."""


def nx_edit_annotation(
    annotation: str,
    position: list[float] | None = None,
    name: str | None = None,
    delete: bool = False,
):
    """Move or rename a native annotation (including associative balloons), or delete it explicitly. Position uses the annotation's existing sheet/work-part frame. Preserves callout text and native associations; does not convert balloons to plain text. Delete cannot be combined with other changes."""


def nx_parts_list_column(
    parts_list: str,
    action: Literal["edit", "append", "remove"],
    index: int | None = None,
    title: str | None = None,
    width: float | None = None,
    field: str | None = None,
    key: bool | None = None,
    protected: bool | None = None,
):
    """Edit, append or remove a zero-based native BOM column. width uses sheet units. field is an explicit native NX parts-list default expression, such as <W$=@$PART_NAME>; inspect existing columns first. Appends general columns; existing callout/quantity semantics are preserved. Remove requires index and rejects other properties. Returns actual evaluated rows and column preferences."""


def nx_edit_explosion_trace(
    traceline: str,
    start_percent: float | None = None,
    end_percent: float | None = None,
    start_offset: float | None = None,
    end_offset: float | None = None,
):
    """Edit a managed native explosion trace's anchored edge arc-length percentages (0..100) and native endpoint offsets in assembly units. Persistent edge/component anchors and the named explosion are retained. Recomputes endpoints and returns readback. Use nx_edit_annotation(delete=true) to remove a trace."""


def nx_bend_table(
    view: str,
    position: list[float],
    table: str | None = None,
    automatic: bool = True,
    columns: list[Literal["BendID", "BendName", "BendAngle", "BendDirection", "BendRadius"]]
    | None = None,
):
    """Create/edit a native associative bend table for an actual flat-pattern drafting view. Position uses sheet units. Select ordered unique native columns and native automatic updating. table edits an existing native bend table. Geometry and bend data remain associated with the flat pattern."""


def nx_refresh_annotations():
    """Refresh persistent managed sheet-metal PMI from current native measurements. These annotations also refresh transactionally after MCP model mutations. Call explicitly after manual NX edits. Missing sources reject the operation rather than retaining silently incorrect values. Rebuilds native bend tables with automatic updating enabled; their flag alone may leave stale rows after reopening."""


READ_ONLY.update({"nx_drawing_view_info", "nx_geometry_anchor", "nx_resolve_geometry_anchor"})


def nx_drawing_view_info(view: str):
    """Inspect actual native view scale, absolute sheet position, view border and sheet containment. Returns each sheet's actual mm/in units. Borders exclude separately placed annotations. Read-only."""


def nx_edit_drawing_view(
    view: str, position: list[float] | None = None, scale: float | None = None
):
    """Assign absolute drawing-view position [x,y] in sheet units and/or positive model-to-sheet scale. Native aligned views may constrain movement; verifies readback and rolls back mismatches. Updates the view, retaining its native associations."""


def nx_add_section_drawing_view(
    parent_view: str,
    cut_object: str,
    position: list[float],
    step_direction: list[float],
    arrow_direction: list[float],
    scale: float = 1.0,
    cut_association: Literal["start", "end", "arc_center"] = "start",
):
    """Create a native simple section drawing view anchored to an owned model edge endpoint (start/end) or arc_center for circular edges. Step and arrow vectors must be perpendicular in the sheet XY plane. position is [x,y] in sheet units. Positive scale is model-to-sheet. Creates a native section line and cut view; requires drafting license."""


def nx_add_detail_drawing_view(
    parent_view: str, center: list[float], radius: float, position: list[float], scale: float = 2.0
):
    """Create a native circular detail view. center=[x,y,z] and positive radius use work-part coordinates/units; choose a circle lying in the parent view plane. position=[x,y] uses sheet units. The native view remains associated with the parent; boundary points retain their explicit model coordinates."""


def nx_drawing_table(
    drawing: str,
    kind: Literal["title_block", "revision"],
    rows: list[list[str]],
    widths: list[float],
    position: list[float],
    table: str | None = None,
    row_height: float = 7.0,
):
    """Create/edit an owned native drawing table with explicit rectangular rows and per-column widths in sheet units. title_block also creates a native NX title-block definition; revision creates an editable tabular history. Editing requires the returned table ID and retains column count; row count may change. Maximum 100 rows/20 columns/1024 characters per cell. No dates, approval, or revision content is inferred."""


def nx_geometry_anchor(object: str):
    """Capture a persistent native handle for an owned body/face/edge in a saved part. Anchor survives save/reopen while the native entity survives. Store the returned anchor rather than session-scoped object IDs. Occurrence geometry must be anchored in its prototype work part."""


def nx_resolve_geometry_anchor(anchor: dict):
    """Resolve an exact native geometry anchor into a current typed ID. Verifies owner path and object kind. Deleted or replaced topology explicitly returns NX_STALE_REFERENCE; never silently substitutes the nearest face."""


def nx_update_assembly_documentation():
    """Explicitly propagate loaded prototype changes in the active assembly. Solve existing mates, refresh managed explosion traces, native BOMs, measured annotations and drafting views. Returns constraint states, evaluated BOM rows, view bounds, retained annotations/dimensions, documentation_complete and assembly health. Retained values require explicit reassociation or recreation. Requires work/display match and no active sketch. Unsatisfied mates or stale managed anchors roll back this update; earlier prototype edits remain separate operations."""


READ_ONLY.add("nx_list_dimensions")


def nx_list_dimensions():
    """List actual computed native dimension values, native retention and measurement_valid flags, typed IDs and annotation origins in the work part. Includes drafting and PMI dimensions, identified by native subtype. Values/origins use native work-part units; inspect view association separately. Read-only, no regeneration."""
