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
    """Refresh persistent managed sheet-metal PMI from current native measurements. These annotations also refresh transactionally after MCP model mutations. Call explicitly after manual NX edits. Missing sources reject the operation rather than retaining silently incorrect values. Native automatic bend tables use NX's own update mechanism."""
