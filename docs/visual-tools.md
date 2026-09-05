# NX MCP visualization tools — 5 September 2026

NX MCP `0.2.0.dev2` adds ten tools to the existing integration, for **77 public tools**. Deployed to the NX v2606 machine using the visible, serialized UI-thread bridge. Journal tools remain disabled.

| Capability | Tools | Behavior |
|---|---|---|
| Collision highlighting | `nx_highlight_collisions`, `nx_clear_highlights` | Highlights native interference pairs, including nested body occurrences; clear pairs remain unhighlighted. Uses NX selection highlighting and leaves persistent colors alone. |
| Section views | `nx_section_view`, `nx_section_control`, `nx_list_sections` | Native single-plane clips with arbitrary origin/normal, caps, edit, enable/disable and delete. Model solids and measurements remain unchanged. |
| Appearance and visibility | `nx_set_display`, `nx_display_info`, `nx_set_visibility`, `nx_restore_display` | Named colors or NX color-table indices, 0–100 transparency, show/hide and nested isolation. Returns restorable snapshots. Shared prototypes are not recolored by occurrence overrides. |
| Sketch diagnostics | `nx_sketch_diagnostics` | Native solver status, remaining DOF, persistent constraints, dimension expressions and constraint-to-geometry links. Supports active and inactive sketches. |

## Examples

```json
{"tool":"nx_highlight_collisions","arguments":{"obj1":"DIRECT_CUBE","obj2":"ROTATED_SUB"}}
{"tool":"nx_set_display","arguments":{"objects":["ROTATED_SUB"],"color":"green","transparency":30}}
{"tool":"nx_set_visibility","arguments":{"objects":["ROTATED_SUB"],"mode":"isolate"}}
{"tool":"nx_section_view","arguments":{"origin":[0,0,5],"normal":[0,0,1],"cap":true}}
{"tool":"nx_sketch_diagnostics","arguments":{"sketch_id":"<returned sketch ID>"}}
```

Use returned opaque IDs where possible. Capture any result with `nx_screenshot`; native viewport PNGs arrive inline through MCP and as checksum-addressed workspace artifacts.

## Semantics and limits

- Origins use display-part units and coordinates. Normals are normalized. **NX v2606 retains `dot(point-origin, normal) <= 0`.** The red lower / blue upper fixture verifies both normal directions in actual viewport images. No internal feature-toggle API is required.
- Work and display parts must match for visual tools. Edit an existing section by ID; an active section is not silently replaced. Sections clip the view and do not create sliced solids or drawing views.
- Restore appearance/visibility snapshots in reverse order. All references are preflighted before restoration. Manual handoff, rollback or part closure can invalidate snapshots. Restoration restores explicit values, not inherited occurrence-override state or the part's modified flag. Display changes may persist when saved.
- Visibility responses report explicit NX blank flags. Parent component, suppression, layer and reference-set state can further affect visible geometry. Isolation covers loaded bodies/components and their ancestors; datum/reference-curve visibility is outside its scope.
- Sketch diagnostics temporarily activate the target and evaluate the entire sketch, then restore native editing/work-region state through an invisible undo mark. Another active sketch is rejected. Persistent constraint counts exclude inferred solver relations; no minimal conflict set is invented. Over/inconsistent status is passed through when NX returns it; those solver states were not separately forced in this release's fixtures.
- Material assignment and photorealistic rendering remain future work. Untested legacy modeling, mates and constraint-authoring tools retain their prior experimental status.

## Verification

The release includes native-probe, public-MCP and local-test evidence separately. Native tests cover active/inactive and fully fixed sketches, appearance/visibility restoration, and section lifecycle. Public tests cover nested collision highlights, instance appearance, isolation restoration, native renders, saved-state preservation, and manual handoff. The original controller session is preserved separately from disposable fixtures.
