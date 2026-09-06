# Advanced authoring roadmap

This was the pre-dev10 roadmap. Sheet-metal authoring and flat patterns are now described in [sheet metal](sheet-metal.md). Dev11 implements curves/meshes/bridges, trim/sew/thicken, direct face editing, BOMs/balloons/traces/animation, manual threads, native datum/FCF PMI and sampled surface/thickness/draft analysis; see [contracts and verification limits](freeform-manufacturing.md).

The historical list below also contains extensions that remain unimplemented or unverified, including surface extension, zebra inspection and full standards-table manufacturing workflows. It must not be read as a current capability manifest.

1. **Freeform curves and surfaces:** editable 3D splines, through-curve and mesh
   surfaces, bridge surfaces, trim/extend, sew, thicken and offset. Include
   continuity (G0/G1/G2), curvature and gap diagnostics so the agent can verify
   surface quality. NX v2606 builder presence was inspected; each operation still
   needs native license/API and geometry tests. Build on existing loft and sweep.
2. **Service and assembly documentation:** explosion trace lines, BOMs and
   associative balloons, then assembly sequences and animation.
3. **Imported-part direct editing:** move/offset/replace/delete-heal faces with
   geometric selection and before/after validity checks.
4. **Sheet metal:** bends, flanges, reliefs, bend allowance and flat patterns.
5. **Manufacturing detail:** threaded holes and cosmetic threads, GD&T/PMI,
   datum schemes and drawing sections/details.
6. **Design validation:** wall thickness, draft analysis, curvature/zebra
   inspection and tolerance-aware clearance reports.

Realize Shape subdivision is a later freeform stage. It needs separate NXOpen
and license verification; exposing a named builder alone is insufficient.
Keep commands intent-oriented, with typed selections, preview/commit boundaries,
checkpoints, units, actual result counts and native verification evidence.

Siemens references: [freeform surface workflow](https://blogs.sw.siemens.com/nx-design/freeform-modeling-walk-through/)
and [Realize Shape](https://blogs.sw.siemens.com/designcenter/nx-tips-and-tricks-realize-shape/).
