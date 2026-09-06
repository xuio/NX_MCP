# Editable documentation and manufacturing validation

The dev12 integration adds ten tools, bringing the integration profile to 170. All modeling calls remain serial on the graphical NX thread. Operation IDs, explicit rollback and stale-reference rejection apply to the new model edits.

## Drawing and assembly documentation

- `nx_list_drawings` enumerates work-part sheets, their sizes, scales and drafting views without activating them. `nx_activate_drawing` opens a sheet; a null drawing returns to modeling. Work/display parts must match and no sketch may be active.
- `nx_list_annotations` paginates notes, PMI, BOMs, balloons, bend tables and explosion traces, returning native subtypes and available text/positions. Drafting positions use sheet coordinates; PMI positions use part coordinates.
- `nx_edit_annotation` moves or renames annotations, or explicitly deletes one. Balloon movement retains native callout associations. Use the dedicated trace tool to change trace geometry.
- `nx_parts_list_column` edits, appends or removes zero-based BOM columns. Inspect existing `columns` first: `field` is the native default expression, such as `<W$=@$PART_NAME>`. An appended general column requires a title, width and field. Callout and quantity columns retain their native types. Widths use sheet units.
- `nx_edit_explosion_trace` changes managed trace endpoint percentages along the anchored edges and native endpoint offsets. Persistent component/edge handles remain attached to the named explosion. Offsets use assembly units. This does not change assembled component placement.

## Threads and GD&T

`nx_thread_catalog` reads the installed NX thread XML **in place**. It lists standards or a bounded page of sizes; selecting an exact standard and size returns the dimensional metadata needed for modeling. It does not transfer the catalog file. `nx_standard_thread` requires an unambiguous catalog row, including method and radial engagement when necessary. It uses the native `ThreadTable` builder, the actual selected cylinder diameter and explicit start face. Symbolic and detailed representations, handedness and direction are supported. Dimensions do not imply an unexposed fit class or a complete standards compliance check.

`nx_pmi_fcf` additionally exposes tolerance and datum MMC/LMC/RFS modifiers, diameter/spherical-diameter/square zone shapes, projected height, tangent-plane and free-state flags. Omitted modifiers reset on editing. Native validation and the published preflight restrictions apply; this is not a full GD&T semantic standards validator.

## Bend tables and measured PMI

`nx_bend_table` creates or edits an NX associative bend table for a native flat-pattern drafting view. Columns include bend ID/name, angle, direction and radius, in caller-selected order. Native automatic updating defaults to enabled. The response includes evaluated rows and settings.

`nx_sheet_metal_annotation(automatic=true)` stores persistent source handles and measured values on the native annotation. Subsequent MCP model mutations refresh changed measurements **inside the same undo transaction**. If a source becomes invalid, the operation fails and rolls back rather than silently retaining obsolete values. Deleting the annotation first removes that dependency. Editing with `automatic=false` disables managed refresh and produces an explicit measured snapshot.

Manual NX edits do not run the MCP transaction hook. Call `nx_refresh_annotations` afterward. Native bend-table updates use NX's own mechanism. Saved source handles are resolved within the owning part, and missing sources are rejected explicitly.

## Validation scope

Run `examples/validate_documentation_manufacturing.py` with `NX_MCP_URL` and optionally `NX_VALIDATION_OUTPUT`. It preserves the existing saved session and creates isolated fixtures: a rounded enclosure and STEP copy, curved surface joins, a thin plate, a drafted block, a sheet-metal bracket and a service assembly. It checks analytic dimensions/volumes, local editing and recovery, stale references after reopen, documentation updates and downloaded native artifacts.

The acceptance script is executable test intent; a successful run and its receipt are required evidence. Local mocked tests check contracts and failure handling, not NX geometry. Sampled curvature, draft and wall-thickness results retain their explicitly sampled scope; no global manufacturing certification is claimed.
