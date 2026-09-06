# Agent workflow evaluations

These are scoped native workflow observations, not general correctness or manufacturing certification.

## Exploded assembly drawing and BOM

A public-MCP workflow on NX v2606 created a rectangular solid prototype, added three occurrences, assigned absolute exploded positions, and produced an A3 drawing with an associative native BOM and grouped callout. The BOM aggregated the repeated prototype to quantity 3. The drawing view referenced the named explosion, and assembled occurrence positions remained unchanged. The exported PDF was downloaded, checksum-verified, rendered and visually inspected. All 27 calls succeeded without schema errors, retries or corrective calls; this count includes initial/final session inventories and fixture cleanup.

An efficient sequence is:

1. Record the current session with `nx_list_open_parts`. Create a uniquely named disposable prototype using `nx_create_part`, `nx_create_sketch`, `nx_sketch_rectangle`, `nx_finish_sketch`, `nx_extrude` and `nx_save_part`.
2. Create the assembly and add occurrences with `nx_add_component`. Retain returned IDs instead of listing them again.
3. Use `nx_create_explosion` and `nx_edit_explosion` for absolute exploded poses. The edit response includes pose readback and whether assembled placements were preserved; a routine workflow can omit a duplicate `nx_explosion_info` query.
4. Create the sheet with `nx_create_drawing`, then call `nx_add_base_view` with `scope="assembly"` and the explosion ID. Direct attachment avoids a separate `nx_show_explosion` or viewport-fit call.
5. Use `nx_create_parts_list` and `nx_parts_list_balloons`. Inspect the returned evaluated rows; no duplicate BOM read is required. Native grouping may produce one balloon for several identical occurrences.
6. Check sheet containment with `nx_drawing_view_info` and assembled placements with `nx_list_components`. Save, export with `nx_export_drawing_pdf`, and retrieve with `nx_download_file`. Verify bytes/checksum and inspect the rendered PDF. Restore the prior work/display part, close only the disposable parts, and verify the session inventory.

**Presentation limitation:** the tested occurrences used the native `Entire Part` reference set, which includes datum geometry. Coordinate/datum arrows appeared beside the blocks in the PDF. No explosion trace lines were requested or created; those arrows must not be interpreted as disassembly instructions. The MCP surface currently exposes no reference-set editing control, so this workflow does not prescribe a geometry-only reference-set switch. Inspect the exported PDF before treating it as a manufacturing document; successful BOM aggregation and sheet containment do not establish presentation readiness.

## Imported-part face editing

An independent fresh-MCP workflow created a synthetic 20 × 15 × 10 mm solid,
exported it to STEP, imported it into a new part and moved its unique upward-facing
planar top face by 2 mm. Native volume changed from 3,000 to 3,600 mm³ and dimensions
from 20 × 15 × 10 to 20 × 15 × 12 mm. Save/close/reopen preserved both measurements;
new object IDs were acquired after reopen. This validates a simple planar face move,
not arbitrary vendor-model healing or topology changes.

The workflow used 34 tool calls plus one fresh catalog read, with no errors or
corrective calls. The original saved session and assembly placements were restored.
For a routine workflow, retain the edited body and health information returned by
`nx_edit_faces`; separate `nx_list_bodies` and `nx_model_health` calls duplicated
those results in this evaluation. An explicit seed save immediately before STEP
export was also redundant because export saves the work part. Account for that
side effect when choosing the disposable part boundary.

Select the face with `nx_find_geometry` using planar type, normal and location,
require an unambiguous match, and use its typed ID in `nx_edit_faces`. Measure native
bounds and volume before/after; reacquire references after reopen. Keep the source
and edited part separate and close only the disposable fixtures during cleanup.

## Four-wall sheet-metal fixture

An independent agent created a 100 × 80 × 2 mm web with four shortened 90-degree
walls, leaving deliberate corner gaps. Native health and thickness checks passed.
Unbend and rebend committed successfully; final formed volume returned to the
original value. Intermediate flattened bounds were not independently asserted.
The exported DXF extents, 115.498230 × 135.498230 mm, matched an independent
bend-allowance calculation within 0.000001 mm; the PNG visibly showed four walls.
This is an open tray fixture, not a sealed or production-qualified enclosure.

The evaluation recorded 49 workflow/recovery calls and four preparation schema
calls. An invalid flat-pattern orientation edge was rejected and its rollback
receipt checked before correction. After forming, use `nx_sheet_metal_info` and
geometry selection to reacquire a current straight boundary/tangent edge of the
stationary web for `x_axis_edge`; the original tab outer-edge location is no longer
reliable. The corrected selection produced a native flat pattern. Two local
response-parsing mistakes were evaluator errors, not NX failures.

Retain typed references under their actual response fields (`part.id`, for
example), distinguish selected feature bends from duplicate historical information,
and reacquire geometry after rollback. Save/export the disposable fixture, restore
the prior work/display part, close the fixture and compare the original inventory.

## Principal-axis revolve recipe

The final dev15 runtime independently verified this millimeter fixture:

1. Create an XY sketch and a rectangle with local corners `[1,0]` and `[3,5]`.
2. Finish the sketch and retain its typed ID.
3. Call `nx_revolve` with `sketch_name` equal to that ID, `axis="Y"`, `angle=360`,
   and `boolean="none"`. The axis passes through the part origin; there is no
   arbitrary-origin argument. `sketch_name` is required in the published schema.
4. Measure the resulting annular cylinder. Expected volume is
   `π × (3² − 1²) × 5 = 125.66370614359172 mm³`; native measurement was
   `125.66370614359175 mm³`. Exact bounds were `[-3,0,-3]` to `[3,5,3]`.
5. Save, close and reopen the disposable part, then measure again. The volume
   persisted. A new load reports `already_loaded=false` and `Opened part`;
   another open of the same loaded file reports `already_loaded=true` and
   `Reused loaded part`. Inspect returned work/display flags for activation state.

The test restored the original saved session and captured a native PNG. It covers
this finished XY profile and principal Y axis, not arbitrary custom-axis geometry.
