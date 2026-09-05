# Native exploded views (NX v2606)

The dev9 integration exposes 130 tools, including six named explosion tools.
Explosions are presentation transforms: they do not reposition the assembled
components, change mates or alter prototype geometry.

| Tool | Contract |
| --- | --- |
| `nx_create_explosion(name)` | Create a named native explosion in the active assembly. |
| `nx_list_explosions()` | List explosion IDs and associated model/drawing views. |
| `nx_explosion_info(explosion, offset, limit)` | Read occurrence paths, assembled and exploded poses, suppression and view references. |
| `nx_edit_explosion(explosion, placements, reset_components)` | Assign absolute poses or reset selected occurrence offsets. |
| `nx_show_explosion(explosion, drawing_view, model_view)` | Display an explosion; omit explosion to restore assembled presentation. |
| `nx_delete_explosion(explosion)` | Delete an unused explosion; detach all referencing views first. |

All references are typed opaque IDs. An explosion belongs to the work part;
mutations require matching work/display parts and a finished sketch. Reacquire
references after close/reopen, rollback or manual-control handoff.

## Placement and recovery

Each placement contains `component`, `translation: [x,y,z]`, and optionally
`rotation_matrix: [[...],[...],[...]]`. Translation is in the work assembly's
units and coordinates. Rotation is a right-handed orthonormal row-major matrix:
`p_assembly = R * p_component + translation`. Omitted rotation retains the
current exploded world orientation at request start.

Up to 1000 unique occurrences can be placed/reset in one request. Inputs are
validated before mutation. Parents are processed before children, independently
of input order. Moving a parent carries its descendants; resetting a child
removes its local explosion offset and retains the parent's exploded placement.
Specifying both parent and child absolute placements gives each its requested
world pose. NX stores local post-transforms; the bridge converts and verifies
the actual native result before committing.

Use a stable `operation_id` when retrying after a transport failure and query
`nx_operation_status`. Absolute placement is also repeatable under a new ID.
Checkpoint and rollback use the existing recovery system. Drawing views that
reference an edited explosion are updated before the edit commits.

## 3D and drawings

With no view argument, `nx_show_explosion` returns to modeling, assigns the
explosion to the work view and fits it. Explicit model-view assignment updates
that saved view without activating it. Explicit drawing-view assignment updates
the drawing view. `nx_explosion_info.views` provides both kinds of typed IDs.

`nx_add_base_view(drawing, scope="assembly", explosion=...)` creates an exploded
assembly view. Omit `explosion` for an assembled view. Body scope remains the
default for compatibility. Projected views retain their parent's explosion.
Native screenshot/render and PDF export tools work with these views; check
returned dimensions, warnings and artifact checksums. Datum/reference geometry
visibility affects output and should be configured for the intended drawing.

When saving drawing parts, the bridge temporarily displays a drawing sheet to
preserve NX CGM preview data without a modal Save CGM prompt, then restores the
previous part/presentation. It does not disable global CGM preferences.

Ordinary bounds, mass, clearance and collision queries still measure assembled
geometry. This release does not add exploded-state collision queries, automatic
explode layouts, trace lines, animation, BOMs or balloons.

## Verification

`examples/validate_exploded_views.py` exercises the public MCP surface against
native NX, using an isolated nested assembly and restoring the original saved
session. It covers rotated parents, child absolute placement and reset, safe
retry, 3D capture, assembled/exploded/projected drawing views, update propagation,
PDF transfer, Save As/reopen, rollback, deletion guards and stale references.
Local tests separately cover partial native failure and strict input validation;
mocked failure injection is not evidence of native transport interruption.
