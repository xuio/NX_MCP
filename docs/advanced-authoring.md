# Advanced authoring on NX 2606

Version `0.2.0.dev6` adds ten tools (104 in the opt-in integration profile). Every native call remains serialized on the NX thread. Model mutations retain operation-ID deduplication, checkpoint rollback, and owner-scoped references. The ordinary-instance `nx_pattern_components` tool is unchanged.

## Geometry selection

`nx_find_geometry` now ranks `nearest` by native `UF.Modeling.AskMinimumDist3` against the trimmed face or edge. Results include distance, closest point and native accuracy; all use work-part coordinates and units. Highest/lowest still rank conservative bounding-box centers. This changes nearest ordering relative to dev5; clients must use `distance`, not `distance_to_bounds_center`, for clearance decisions.

Each query returns a versioned `selector`. Pass that complete object to `nx_resolve_geometry` after a model edit or reopening its original part. The tool re-evaluates the rule and returns a fresh reference only when the best rank is unique within the requested tie tolerance. Owner journals must still resolve. A selector represents a geometric rule, such as “highest upward planar face,” rather than permanent topological identity. If topology changes, a different face can satisfy that rule. Ties and missing owners are explicit errors; refine the query rather than selecting an arbitrary candidate.

`nx_recognize_holes` reports inward cylindrical faces, radius, axis, angular coverage and coaxial groups. Full circumferences and partial faces are distinguished. Coaxial grouping uses 0.001 part-unit radial tolerance and axis dot-product tolerance of 1e-8. These are BREP bore candidates, not inferred manufacturing features: through/blind termination, threads, fits and compound-hole classification are outside this tool.

## Associative assembly patterns

Create a native linear pattern with:

```json
{"component":"<seed occurrence ID>","direction":[1,0,0],"spacing":16.5,"count":16}
```

Send this to `nx_native_component_pattern`. Count includes the seed and is limited to 2–100. The seed must be an unsuppressed immediate child of the work assembly. The native `NXOpen.Assemblies.ComponentPattern` remains editable and survives save/reopen. `nx_edit_component_pattern` changes pitch and/or count; `nx_list_component_patterns` returns native association, parameter expressions and member poses. A 14 mm wide seed with 16 total instances at 16.5 mm pitch spans 261.5 mm.

The installed Python collection requires `GetAllComponentPatterns()`; iterating it raises an NX argument error. The implementation checks the installed API and never substitutes independent occurrences for failed native pattern creation.

## Dimensions and relations

`nx_sketch_dimension` creates line length, horizontal or vertical endpoint distances, or arc radius/diameter dimensions. Values use part units; annotation origin is local `[x,y]`. Reference dimensions measure current geometry and reject a supplied value that differs from the measured value by more than 0.001 part units. Driving dimensions return an editable expression ID; use `nx_set_expression` to change its formula later.

`nx_sketch_relation` creates parallel, perpendicular, equal-length, equal-radius, concentric or coincident persistent relations. Coincident relations require explicit line start/end or arc center choices. Modern sketches use native Make Relation builders with curve1 stationary; curve2 and any connected geometry move through the native solver. A geometric residual check rejects unsatisfied results. Curves must belong to the named sketch. Operations restore its prior activation state and reject another active sketch. They never remove constraints implicitly.

`nx_feature_parameters` exposes the expressions NX associates with a feature. `nx_set_feature_parameters` atomically changes 1–25 owned, editable local Number expressions by ID or exact expression name. It validates every target before editing and retains each expression's units. This broadens editing without guessing semantic labels or builder options. Native acceptance covers extrusion expressions; availability on another feature type is determined by its exposed expressions and editability, not by a blanket correctness claim about that feature.

## Conflict diagnostics

`nx_sketch_conflicts` combines native solver status with bounded single-constraint-removal trials. Each trial and the surrounding activation/work-region changes are restored with NX undo marks. It reports checked/total, trial errors, completeness and constraints whose individual removal relieves the detected conflict. This is a sensitivity check, not a minimal unsatisfiable constraint set; several independent conflicts can yield no single-removal relief.

NX 2606 can report `UnderConstrained` for a nonzero line with both persistent horizontal and vertical relations. The tool reports that directly provable contradiction separately as `explicit_conflict_pairs`. This additional rule covers that pair only; native status and an empty pair list do not prove every legacy relation is consistent. Cleanup failure is an explicit partial mutation outcome.

## Validation

Run `examples/validate_advanced_tools.py` against a disposable NX workspace via `NX_MCP_TEST_ENDPOINT`; optionally set `NX_ADVANCED_RESULTS` for local receipts. It creates fixture parts and does not close or save unrelated user parts. Restore your original active part afterward. The local regression suite distinguishes fake NX boundary tests from native geometry tests. Deployment acceptance and scoped limitations are recorded separately in `dev6-validation.json`.
