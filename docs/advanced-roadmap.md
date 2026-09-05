# Advanced authoring roadmap

These are recommended additions, not claims of implemented or tested APIs.

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
