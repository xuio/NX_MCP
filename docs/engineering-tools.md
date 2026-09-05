# Engineering tools on NX v2606

The dev8 opt-in profile exposes 124 tools. Mutations run serially on the NX thread and use durable operation IDs and NX undo marks. The capability manifest records the specific native fixtures tested; a tested tool is not a claim that every parameter combination or NX version is supported.

## Solid modeling

- `nx_extrude` adds start offsets, symmetric total length, arbitrary work-part direction, through-all and up-to-face ends. A Boolean requires explicit target bodies. `distance` is the end coordinate along the extrusion direction; with `symmetric=true` it is the total length. Unsupported combinations are rejected.
- `nx_shell` uses positive wall thickness and optional removed face IDs. Its default thickness goes inward; `outward=true` reverses it. Native testing caught and corrected the NX flip convention.
- `nx_loft` joins ordered sketch profiles. Solid and sheet options are explicit; the native acceptance fixture covers a solid square-to-square loft.
- `nx_draft` requires faces, a stationary face on the same body, a direction and signed angle in degrees. Explicit native tolerances avoid zero-tolerance failures.
- `nx_transform_bodies` creates or edits an associative move. The mapping is `p_output = R * p_input + translation`; `R` is right-handed, orthonormal and row-major. Editing the returned feature replaces the mapping. Copying uses associative body extraction before the MoveObject feature, because the installed builder's CopyOriginal mode produced a non-associative BREP.
- `nx_blend` and `nx_chamfer` accept typed owned edge IDs from one body. They use native chain/collector APIs. Topology references must be reacquired afterward.
- `nx_hole` makes a cylindrical subtract along an explicit direction, default +Z. This preserves the earlier simple-cut semantics; it is not a threaded or drill-tip HolePackage feature. Specify a body when the part has multiple bodies.
- `nx_sweep` accepts distinct section and guide sketch IDs. Optional Boolean output requires one explicit target body.
- `nx_mirror_body` preserves the source and creates a native mirror feature about an origin XY/XZ/YZ datum plane.

Feature results include all output bodies and result count. Invalid operations roll back; inspect the operation receipt after uncertain transport failure before retrying.

## Sketches

`nx_sketch_primitive` adds editable circles, horizontal slots or rounded rectangles in sketch-local coordinates. `nx_sketch_trim_extend` uses explicit boundary curves and a local pick point. `nx_sketch_angle` creates a driving angular dimension. `nx_sketch_tangent` and `nx_sketch_symmetry` use the modern NX solver builders and verify actual geometric residuals and persistent constraints. Symmetry currently accepts two lines about a third line. Native tests cover line/circle tangency and line-pair symmetry; other curve combinations have narrower validation.

## Assemblies and materials

`nx_component_array` creates native associative rectangular or circular patterns. Counts include the seed, with at most 100 total instances. Rectangular arrays can use two directions. Circular pitch is degrees and cannot wrap to duplicate the seed. `nx_edit_component_pattern` edits count/pitch and existing second-direction parameters; read-back includes native expressions and actual placements.

`nx_assembly_constraint`, `nx_edit_assembly_constraint` and `nx_list_assembly_constraints` expose persistent constraints with typed references, expressions, suppression and native solver status. Creation uses immediate unsuppressed child occurrences and their occurrence faces/edges. Solving can move components. Native acceptance checks actual face separation after editing, because a solved status plus an updated expression initially left a stale pose until the network was rebuilt after the edit. `nx_mate_component` now maps its earlier mate names onto these native operations; touch/offset mating is checked geometrically.

`nx_set_material` assigns a named local density-only physical material in kg/m³. It does not invent elastic, thermal or appearance properties. `nx_material_info` reads native assignments. `nx_mass_properties` returns summed solid mass, area, volume, center of gravity and centroidal inertia in SI, with explicit work-part WCS origin/basis. Overlaps are counted separately. The native fixtures include translated and rotated nested assemblies.

`nx_copy_project` clones a saved loaded assembly into a new workspace directory, preserves relative prototype subfolders and rewrites native dependencies. A required basename prefix avoids loaded-part name conflicts. Source hashes and copied dependencies are checked, and a manifest is written. It copies rather than deletes source files; unsaved parts, existing destinations and unloaded dependencies are rejected.

## Rendering and drafting

`nx_render_view` uses native Studio image capture for exact 128–4096 pixel dimensions. It supports original, white, transparent or custom RGB backgrounds, native lighting presets 1–5, and studio/shaded/edge styles. It restores temporary style and lighting settings and returns camera metadata, checksum, artifact path and an inline MCP image. This is NX rendering, not an AI reconstruction. The native fixtures cover preset 2 and exact 800×600 and 640×480 output; full-VM capture is a separate troubleshooting activity.

Drawing creation uses native metric A0–A4 landscape sheets with first-angle projection. `nx_add_base_view` currently requires a single-body part and accepts sheet placement in mm. `nx_add_projection_view` creates an associative projected view. `nx_add_dimension` supports aligned/horizontal/vertical linear dimensions: one edge measures its endpoints; two edges measure their start vertices. `nx_export_drawing_pdf` exports all sheets at full sheet scale with text and a checksum. Native acceptance produced an A3 PDF with two views and a computed 10 mm dimension, then parsed and visually reviewed it.

These are authoring tools, not a complete manufacturing drawing package: title blocks, GD&T, arbitrary detail/section drawings, radial dimensions and automatic annotation layout are not supplied by this release.

## Reproducible validation

Run `examples/validate_engineering_tools.py` against the deployed public MCP endpoint using `NX_MCP_URL` and `NX_VALIDATION_OUTPUT`. It creates an isolated fixture directory, requires a saved session, verifies analytic geometry, nested material mass, pattern placements, persistence/retry and inline images, and restores the original loaded parts. `NX_VALIDATION_GROUP` selects a focused rerun. Native evidence is kept separate from local mocked API-contract tests.
