# Authoring and review tools (NX v2606)

The dev5 release added 17 tools to the existing 77-tool profile. Dev6 adds ten more; see [advanced authoring](advanced-authoring.md). All native calls run serially on the NX UI thread. Existing operation IDs, deduplication and model rollback envelopes apply. Names remain separate from opaque session/owner-scoped references.

## Select geometry and parameters

`nx_find_geometry` enumerates faces or edges within a body, feature, component or full assembly. Filter planar faces by oriented normal, cylinders and circular edges by radius, and order by exact BREP nearest distance (dev6) or highest/lowest conservative bounding-box center. Coordinates and radii use work-part units. Nearest results include the closest point and native accuracy. Candidate results are paginated; use `nx_highlight_objects` to inspect choices, then `nx_clear_highlights`.

`nx_list_expressions` returns formulas, numeric values, units, editability and stored immediate dependencies. Conditional formulas can have incomplete stored dependencies. `nx_set_expression` creates named Number expressions with mm/inch/degree/radian/unitless units or edits existing local, unlocked Number expressions. Edits preserve units. NX formula errors and failed updates roll back. `nx_bind_parameter` connects an existing expression to EXTRUDE start/end or PATTERN_FEATURE count/spacing. Units and dimensional compatibility are enforced by NX. This is not a general interface to every feature builder.

## Health and local editing

`nx_model_health` reports native feature errors/warnings, suppression, unavailable prototypes and UF body-consistency faults. Assembly scope checks unique loaded unsuppressed prototypes. A sheet body is informational rather than automatically invalid. `healthy` only describes the listed checks; no design-intent, manufacturing, solver-conflict or unloaded-file certification is implied. `nx_rebuild_model` runs native DoUpdate for pending updates; it does not force every current feature to regenerate.

`nx_edit_sketch` reopens an existing sketch, preflights ownership and operation structure, and applies up to 100 edits under one rollback mark. It preserves the prior active/inactive state and returns whole-sketch diagnostics. It supports line endpoints, arc center/radius/angles, adding lines, deleting owned curves/constraints, and adding fixed/horizontal/vertical constraints. Points are local `[x,y]`; arc angles are degrees. Another active sketch is rejected. Constraints are never silently removed to permit an edit. Edit a dimensional constraint through the associated expression reported by diagnostics; more constraint types remain future work.

`nx_component_action` renames, suppresses, unsuppresses, removes or replaces an immediate child occurrence. Activate a nested component's owning assembly before editing it. Replacement targets one occurrence, requests relationship retention and checks placement afterward; native errors roll back. Suppression affects all arrangements. Removing an occurrence does not delete its prototype file. `nx_pattern_components` creates 2–100 total independent occurrences including the seed, with explicit direction and pitch. These are ordinary instances, not a native associative component pattern.

## Presentation and inspection artifacts

`nx_set_camera` sets absolute camera rotation, view-space origin and scale. Rotation is a row-major orthonormal 3×3 matrix whose columns are NX view axes. Work and display parts must match.

`nx_save_presentation` writes a new workspace JSON containing camera, active single-plane section, loaded geometry visibility, and explicit colors/transparency including per-face overrides. `nx_restore_presentation` resolves all saved journal locators before mutation. The owner part must match. Missing geometry rejects restoration; across revisions, verify journal identifiers still refer to intended entities. Datum visibility, materials and inherited-override semantics are outside this format. Display restoration may mark a part modified; it does not save the part.

`nx_inspection_report` produces a workspace ZIP with HTML, structured JSON, SHA-256 manifest, overview screenshot, up to eight flagged-pair close-ups, and up to six section screenshots. Pair results retain native distance/contact/interference distinctions. `max_pairs` is an explicit work limit; exceeding it errors instead of implying unchecked pairs are clear. Temporary camera, visibility and section state is restored. Retrieve the ZIP through `nx_download_file`. Captures are native viewport PNGs, not photorealistic rendering. Files are never silently overwritten.

## LLM review workflow

`nx_model_summary` provides overview counts/bounds/health plus paginated component, feature, expression and sketch sections. It separates owned-body counts from assembly occurrences and does not invent design dimensions.

`nx_preview_change` accepts up to 25 supported expression, parameter, extrusion/pattern edit, sketch edit or placement operations. It applies them temporarily under an invisible checkpoint, captures before/after parameters, volume, bounds, health and optional viewport image, then **rolls back before returning**. Returned geometry references are stale after rollback. The preview token stores a session-scoped plan, not a persistent undo mark.

`nx_finish_preview(action="accept")` re-resolves stored target locators and atomically reapplies the plan only while its owner part and mutation epoch are unchanged. Intervening mutations, failed mutations, saves, lifecycle changes or manual handoff expire acceptance. `action="discard"` removes the plan; the original geometry was already restored. Supply a stable operation ID to avoid applying an accepted plan twice. Accepted edits remain unsaved and undoable. Saves, imports, exports and other filesystem/session operations cannot be included in a preview plan.

## Validation

Local tests use stateful NX seams to check ownership, error cleanup, stale preview rejection, retry behavior, artifact integrity and display restoration. They do not simulate the Siemens kernel.

The native runner exercises eight groups on disposable geometry: expression binding/rollback and health, geometric selection/highlight, sketch reopening/constraints/deletion, assembly maintenance/patterns, saved presentations/camera, inspection ZIPs, preview acceptance/staleness, and summary pagination. The separate eleven-group visualization runner protects the preceding release.

Run `examples/validate_authoring_tools.py` with `NX_MCP_TEST_ENDPOINT` and optionally `NX_AUTHORING_RESULTS`. It creates a unique workspace subdirectory and leaves test parts for inspection. It changes active parts and does not restore an unrelated user's session; use a dedicated validation session or preserve/restore the original session externally. The runner verifies downloaded artifact checksums and ZIP manifests.
