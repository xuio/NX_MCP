# Freeform, documentation and manufacturing

The dev11 integration adds 20 tools (160 total) for NX v2606. These are intent-oriented wrappers around native NX geometry, annotations and rendering. Model mutations run serially on the graphical NX thread with the existing operation-ID deduplication and rollback framework. Coordinates are in the work part unless the tool explicitly uses assembly or drawing-sheet coordinates.

## Curves and surfaces

- `nx_spline`: create/edit associative 3D Studio Splines from interpolation points or control poles, including degree and periodicity.
- `nx_surface_mesh`: native Through Curve Mesh from intersecting primary/cross sections.
- `nx_bridge_surface`: full-edge bridge with G0, G1 or G2 constraints.
- `nx_trim_sheet`, `nx_sew`, `nx_thicken`: associative sheet trimming, sewing and signed face offsets. Incomplete sewing and a sheet fallback when a solid was requested are rejected and rolled back.
- `nx_curve_analysis`: sampled native derivatives, tangent, curvature, radius and spline data.
- `nx_surface_continuity`: bidirectional closest-point gaps, normal angles and orientation-aligned curvature-tensor differences. G2 uses the shape-operator Frobenius norm. Singular samples prevent a pass; sampled results do not certify global continuity.

Native fixtures exercised spline creation/editing, planar meshes, G0/G1/G2 bridge creation, trim, sew, thicken and derivative analysis. Continuity checks distinguished matching planar sheets, separated sheets, and a tangent plane/quadratic-surface join with different curvature. A bridge builder's requested continuity is distinct from independent geometric verification. Periodic splines and all possible network topologies are not covered by these fixtures.

## Imported-face editing

`nx_edit_faces` supports directed face translation, signed normal offset, replacement by another face, and deletion with healing. It creates native NX features and rejects irrelevant arguments. Reacquire face/edge references after topology changes. Tests used controlled solid fixtures with independently calculated volumes; this does not establish reliability on every vendor import or damaged B-rep.

## Assembly documentation

`nx_create_parts_list`, `nx_parts_list_info` and `nx_update_parts_list` expose native BOMs with actual evaluated rows, installed column defaults and assembly traversal scope. `nx_parts_list_balloons` creates NX-associated callout groups in drawing views. Repeated instances aggregate according to the native key columns; native automatic placement still needs visual review.

`nx_explosion_trace` creates a native automatic traceline attached to a named explosion. Its anchors store **native persistent handles** for component occurrences and prototype edges, not transient tags or journal strings. Save/reopen and subsequent placement changes were tested against exact endpoint coordinates. MCP explosion edits, show and animation refresh the endpoints. After manual NX geometry changes, call `nx_show_explosion` to refresh. Missing anchors fail explicitly. Collapsed traces are hidden; expanded managed traces are shown during refresh. This refresh mechanism is managed by MCP rather than an automatic NX callback.

`nx_export_explosion_animation` writes a self-contained HTML player with native PNG frames, a scrubber and per-frame metadata. It uses linear translation and shortest-arc quaternion rotation. Show a modeling view and frame the entire motion first; the camera remains fixed. A temporary undo mark restores poses, view association and model state even when capture fails. This is presentation animation, not a collision-certified disassembly sequence. Retrieve the file through `nx_download_file`. Native drawing PDF export now temporarily prepares all sheet presentations and restores the previous drawing/modeling view, including when invoked after returning to 3D. Single-sheet and two-sheet exports from a modeling view were verified.

## Manufacturing and PMI

- `nx_thread`: explicit manual pitch, diameters, length, start face, handedness and symbolic/detailed representation. Internal and external threads were created natively. These dimensions do not imply a standards-table fit class.
- `nx_pmi_datum` and `nx_pmi_fcf`: native geometry-associated datum symbols and single-frame geometric tolerances, with existing datum references and annotation editing. They cover the published fields, not every modifier or GD&T standard combination.
- `nx_face_analysis`: sampled normal, principal curvature/radius and signed draft angle against a pull direction. Draft is `asin(normal · pull)` in degrees.
- `nx_wall_thickness`: inward-normal rays from sampled face points to the first exit face, with exact native intersections and unresolved samples reported. A 5 mm plate measured 5 mm at every sampled point. It is neither a rolling-ball thickness algorithm nor a certified global minimum.

Native sheet-metal flat patterns and DXF/GEO export remain available from [dev10](sheet-metal.md). That document distinguishes tested feature families from unavailable or unverified options; this release does not claim complete coverage of every licensed NX manufacturing module.

## Repeatable acceptance

Run `examples/validate_freeform_manufacturing.py` with `NX_MCP_URL` and an optional `NX_VALIDATION_OUTPUT`. It uses disposable workspace parts, records operation receipts and downloaded artifact checksums, and restores the original saved session. The graphical bridge and experimental integration profile must be enabled. The ordinary test suite also covers contracts, validation, cleanup, numerical invariance and animation failure recovery; mocked tests are not native NX evidence.
