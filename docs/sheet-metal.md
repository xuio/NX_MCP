# Native sheet metal

The dev10 opt-in integration adds ten tools (140 total). It exposes 34 native
sheet-metal feature families and 412 top-level builder fields, with nested bend,
relief, miter, flange, corner and multi-thickness settings. These are native NX
features, not tessellated substitutes or ordinary solids renamed as sheet metal.

Each family has a successful **NX v2606 creation fixture**. This is broad authoring
coverage, not a claim that every NX sheet-metal workflow or parameter combination
is complete. See [scoped native evidence](sheet-metal-native-validation.json).
Other NX versions, most feature edit combinations, table-driven materials, and
custom bend tables remain unverified. Metaform and manufacturing nesting are not
exposed. Remove Bends was unavailable under the tested installation's feature toggle.

## Workflow

1. Create or activate a work/display part with the existing path-aware part tools.
2. Finish any active sketch, then call `nx_sheet_metal_context`. This selects the
   modern `UG_APP_SBSM` application. It does not enter the retired sheet-metal app.
3. Inspect/set stock defaults with `nx_sheet_metal_defaults` and
   `nx_set_sheet_metal_defaults`. Creation defaults do not override existing features.
4. Call `nx_sheet_metal_schema(operation)` before creating/editing a feature. It
   returns strict schemas, actual enums, native validation scope and example inputs.
5. Call `nx_sheet_metal_feature(operation, parameters, feature?)`. References must
   belong to the work part. A feature ID requests an edit. Unknown fields are errors.
6. Inspect actual thickness and bend data with `nx_sheet_metal_info`, and check
   native feature/body consistency with `nx_model_health`.
7. Create a `flat_pattern` feature; export it with `nx_export_flat_pattern` or place
   its native named view on a drawing with `nx_add_flat_pattern_view`.

All mutation calls run serially on the NX thread under the bridge's existing undo
and operation-receipt handling. Reuse the same operation ID when reconciling a lost
response. After rollback, reacquire object references; deliberately stale IDs are
rejected. Saving follows NX save-boundary semantics: inspect `nx_checkpoint_state`
before relying on an earlier checkpoint. Read-only schema and inspection calls do
not clear recovery history.

## Feature families

| Area | Operations |
|---|---|
| Base and attached material | `tab`, `flange`, `contour_flange`, `lofted_flange` |
| Bending and edge finishing | `bend`, `jog`, `hem`, `break_corner` |
| Cuts and formed details | `normal_cutout`, `bead`, `dimple`, `louver`, `drawn_cutout`, `gusset`, `edge_rip` |
| Corners | `closed_corner`, `three_bend_corner`, `bulge_relief` |
| Conversion and flattening | `convert`, `from_solid`, `flat_solid`, `flat_pattern`, `unbend`, `rebend` |
| Bend modification | `bend_taper`, `resize_bend_angle`, `resize_bend_radius`, `resize_neutral_factor` |
| Advanced construction | `advanced_flange`, `variational_flange`, `bridge_bend`, `joggle`, `lightening_cutout`, `solid_punch` |

Use the schema's real enum names. For example, modern closed corners use
`overlap_type`; the retired `closure_type` property is deliberately excluded.
Flanges use `CreateMultiFlangeBuilder`, and each list entry owns its edge selection,
length, angle and bend overrides. Supplying a list replaces that builder list.
Use returned expression IDs with `nx_set_expression` to edit dimensions without
reselecting the feature's original support geometry.

### Choosing flange and unbend inputs

The operation schema includes `prerequisites` and, where recorded, `example_evidence`
with a repository source and the tested fixture scope. Example coordinates and
dimensions describe that fixture's units; they are not converted for an inch part.
Replace every `$input_N` with a freshly selected typed reference.

- `flange`: the public fixture creates a 100 × 80 × 2 mm XY tab, selects its
  boundary edge nearest `[50, 0, 0]`, then uses
  `{"flanges":[{"edges":["$input_1"],"length":20,"length_reference":"Inside","angle":90}]}`.
  Each entry requires length and angle even with `length_option=Keypoint`; that
  mode also needs its keypoint, and is not validated by this numeric-length
  example. The separate channel fixture verifies `width_option=AtCenter` with
  width 60 on a 100 mm edge. It does not verify every other width-position mode.
- `advanced_flange`: the recorded fixture uses the same tab boundary edge with
  `{"edges":["$input_1"],"length":20,"angle":90}`. It leaves the mode and optional
  references at native defaults. `ToReference`, inferred length, face collectors
  and plane combinations need additional native validation; the exposed fields
  alone do not establish their conditional requirements.
- `unbend` / `rebend`: the recorded fixture adds a 20 mm, 90-degree flange to
  the tab. `$input_1` is its bend face from
  `nx_sheet_metal_info.items[].bends[].face.id`, and `$input_2` is the original
  largest planar web face from the same body. Use
  `{"face_collector":["$input_1"],"reference_entity":"$input_2"}`.
  After unbend, reacquire the current bend and web references before rebend.
  Keep the original web stationary; selecting the flattened bend strip as the
  stationary reference is not equivalent. Edge stationary references are exposed
  but were not exercised by this fixture.

Secondary contour flanges require an **along-path sketch**, created with
`nx_create_path_sketch`. Use its returned origin/basis/normal to place the profile.
An ordinary planar sketch in the same position is not equivalent. Secondary tabs
require a target body and matching thickness. Both attached workflows were
verified in native NX.

Sections accept either a finished sketch ID or
`{"edges": ["edge ID"], "help_point": [x,y,z]}` /
`{"curves": ["curve ID"], "help_point": [x,y,z]}`. The explicit point controls the
native section selection. Existing sketches remain external inputs; the bridge
does not consume them as internal sketches.

Coordinates and lengths use work-part units; expression angles use degrees and
neutral factors are unitless. Plane inputs use origin/normal; coordinate systems
use orthogonal x/y axes. Direction vectors are normalized. Sections and native
feature prerequisites still matter: a successful schema check is not proof that
selected geometry can be formed.

## Native fixture findings

- Tabs, flanges, default thickness/radius/neutral factor and flange edits were
  measured in native NX. A 100 × 80 × 2 mm base tab has volume 16,000 mm³.
- Lofted flange fixtures use open sections, endpoint points on those sections and
  a positive bending segment count. Closed profiles were not a valid test fixture.
- Bead fixtures need positive angle and punched width; finite normal cutouts need
  a positive depth. Native zero defaults are not necessarily usable.
- Louver sections must be assigned before use. Reading the uninitialized native
  Section property throws. Formed and lanced, unrounded examples passed in both
  depth directions; rounded variants remain unverified.
- Edge rip passed with a short interior slit on a planar sheet face. Ripping
  selected edges of the exploratory tube did not pass and remains unverified.
- Three-bend corner passed on a convex corner with matching adjacent bends.
  Bulge relief passed with an eligible bend-end edge. Arbitrary edge selections
  were rejected; this does not show that the native feature is broken.
- Unbend/rebend use an initialized native face collector and the original web as
  the stationary face. Selecting the newly flattened bend strip is not equivalent.
- Standard `Builder.Validate()` is used. The older `ValidateBuilderData` returned
  inconsistent values on an unchanged valid tab and is not used for acceptance.

## Flat patterns, drawings and artifacts

`nx_export_flat_pattern` exports native DXF or Trumpf GEO to a **new** workspace
file. It reports path, units, options, size and SHA-256. Files are staged beside the
destination, checked and published without overwriting existing artifacts. Retrieve
bytes with `nx_download_file`. Manufacturing format details beyond the tested
fixtures, including downstream machine compatibility, are not certified.

`nx_add_flat_pattern_view` uses the model view generated by the Flat Pattern
feature, preserving the native developed geometry and bend lines. Position is in
sheet millimeters. Existing drawing/PDF tools apply. This does not automatically
create a dimensioned manufacturing drawing, bend table, BOM or balloon layout.

NX may create auxiliary solid bodies for flat-pattern representations. A hidden
source solid can also remain after conversion. Part-wide bounds and summed volume
include such bodies. **Measure the intended folded body by ID** when comparing
physical-part dimensions or volume. Export checks must not use stale DXF header
extents; the acceptance fixture checks actual LINE entity coordinates.

`nx_sheet_metal_annotation` creates native PMI associated with the selected body or
bend faces. Labels contain **measured snapshots**, explicitly identified in their
text. They contain actual thickness or bend angle/radius/neutral factor. Refresh
with the existing annotation ID after geometry changes; automatic numeric text
updates have not been implemented. Material catalog enumeration is not exposed:
`GetMaterialNames()` caused a native memory-access violation on the test host.

## Reproducible acceptance

Run `examples/validate_sheet_metal.py` against an isolated test session using
`NX_MCP_URL` and `NX_VALIDATION_OUTPUT`. It preserves the original saved session,
creates a bracket in a unique folder, checks analytical volume and bend data,
checks same-ID replay, downloads native artifacts with checksum verification,
checks developed DXF dimensions before/after a parameter edit, exercises
save/reopen/stale references, and verifies rejection and checkpoint rollback.

The public acceptance checks a complete bracket workflow. The separate 34-family
fixture evidence reports the broader creation coverage. Neither mocked wrapper
tests nor a builder's mere presence counts as native geometry verification.
