# Release engineering and native acceptance

Dev13 adds nine tools for editable drawing views, assembly refresh and persistent imported geometry, plus a serial native release acceptance runner. The integration profile exposes 179 tools. NX calls remain on the graphical NX thread; model changes use the existing operation IDs and undo transactions.

## Drawings and units

- `nx_drawing_view_info`: actual view scale, sheet position, native border and sheet containment. Borders exclude separately placed annotations.
- `nx_list_dimensions`: computed native values and typed dimension references, including PMI and drawing dimensions, native retention status and whether the computed value remains valid. Linear drafting dimensions can reference assembly occurrence edges.
- `nx_edit_drawing_view`: absolute position and/or positive scale, with native readback. Aligned views can reject incompatible moves, which roll back.
- `nx_add_section_drawing_view`: a simple native section and section line. Select an owned edge and `cut_association` of `start`, `end`, or `arc_center`. Step and arrow directions are perpendicular vectors in the sheet XY plane. The scale is assigned explicitly; NX's creation API may otherwise inherit the parent's scale.
- `nx_add_detail_drawing_view`: a circular native detail. Center and radius use model coordinates/part units; the bridge maps them into the parent view. Managed boundary coordinates refresh with parent-view edits. The center is an explicit model coordinate, not a selected material point that moves with arbitrary geometry edits.
- `nx_drawing_table`: editable revision rows or a native NX title block. Caller supplies content; no approvals, dates or revisions are invented. Revision tables use their native section origin and title blocks their native annotation origin. Inspect the drawing before release. A native title-block definition replaces the original table section; the returned reference identifies the resulting title block.

`nx_create_drawing` supports `units="mm"` or `"in"` independently of the work part. A0–A4 retain their physical dimensions. Drawing inspection reports per-sheet units. NXOpen placement points are converted from sheet to part units; UF drawing moves use sheet coordinates. Legacy `position_mm`, `origin_mm` and `spacing_mm` fields remain millimeter values; the additional sheet-unit fields identify the caller's actual coordinates. Model-unit names remain `mm` and `inch`. Projected-view spacing is verified on its free movement axis; NX maintains native associative alignment on the other axis, whose reference coordinate can differ from the parent. The result reports the actual sheet position.

Native mass measurements require explicitly setting `MeasureBodies.InformationUnit` to `KilogramMillimeter`: supplying millimeter unit objects to `NewMassProperties` alone returns cubic inches in inch parts. Volume and interference volume are explicitly reported in mm³.

## Assembly changes and imported geometry

`nx_update_assembly_documentation` explicitly solves existing mates, refreshes managed explosion traces, BOMs, measured annotations and drafting views in the active assembly. It reports actual constraints, evaluated rows, view borders and health. It temporarily opens drawing sheets for native regeneration and restores the prior view. It does not undo earlier prototype edits. Missing trace anchors or unsatisfied constraints fail the refresh transaction.

Replacing a prototype may retain old drawing dimensions at their former values. Refresh reports `documentation_complete: false`, affected dimensions/annotations and warnings. Native retained balloons are also reported; delete obsolete callouts and recreate them from the updated BOM. Reassociate explicitly with `nx_add_dimension(dimension=existing_id, object1=replacement_edge, ...)`; this preserves the native dimension identity.

Replacing a prototype may invalidate its edge anchors. Explicitly remove obsolete traces and create anchors on replacement geometry; the bridge never guesses correspondence between unrelated faces.

`nx_geometry_anchor` stores a native persistent handle plus owner path and kind. `nx_resolve_geometry_anchor` verifies the owner and that the exact body, face or edge survives. A deleted entity returns `NX_STALE_REFERENCE`; geometric nearest-neighbor fallback is not automatic. Anchors are for owned prototype geometry, not assembly occurrences.

`nx_edit_faces` returns native health with its repair result. Failed native edits include the action, selected face references and NX error code when available. The enclosing transaction rolls back unhealthy results.

## Repeatable release validation

Use trusted source from the release being tested:

```sh
NX_MCP_URL=http://NX-HOST:8765/mcp \
NX_VENDOR_STEP=/path/to/authorized-connector.step \
python scripts/validate_native_release.py --output /new/receipt-directory
```

The runner executes the release-engineering, documentation, annotation-recovery, freeform and sheet-metal suites serially. It stops at the first failure, retains logs and geometry/artifact receipts, hashes outputs, and verifies original open parts, work/display state and component paths/transforms. There is no automatic mutation retry. A fresh output directory prevents stale evidence from being mistaken for a new pass. Native tests require saved existing parts and agent UI mode.

A public connector fixture is available from [KiCad's USB4085 model](https://gitlab.com/kicad/libraries/kicad-packages3D/-/blob/8fb0194639525261cd642ec40d62ee26e1f601de/Connector_USB.3dshapes/USB_C_Receptacle_GCT_USB4085.step), SHA256 `82235f7275d07f720e3c050f781397f4bef47fdc7e15dd507d68ccba861f1a35`. Fetch it separately under its upstream license; vendor CAD is not bundled in this repository. Proprietary NX catalogs are read in place and never copied into release artifacts.

Native acceptance is separate from mock/transport CI. A CI pass alone does not certify a release against NX. Keep the native receipt, package hash and exact source commit together, and run acceptance after every deployment before recording that release as verified.

## Verified dev13 deployment

[Native acceptance](dev13-validation.json) records all five installed suites passing:
11 release-engineering groups, eight protected documentation groups, annotation
recovery, ten freeform groups and four sheet-metal groups. The original 38 saved
parts and 116 component paths/transforms were preserved. All 29 downloaded
artifacts matched their native hashes; PDF layouts were visually reviewed.

The runtime package is pinned to `7942284e0402f54d3ca54a6d6481b58a92a27c9c`.
A separate validation overlay records the final evidence, corrected capability
scope and two test-runner fixes: shared-drive output uses `absolute()` without
unsupported final-path resolution, and STEP uploads obey the 256 KiB chunk limit.
The NX modeling implementation remains the packaged runtime. The overlay's
`validation-release.json` records its commit and individual file checksums.
