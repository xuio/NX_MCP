# Internal Fan support for Baldower

`nx_sim_internal_fan_schema(document)` inspects an uncommitted native Internal Fan builder in an active NX MULTIPHYSICS Flow or Coupled Thermal-Flow SIM. It reports property defaults and types, selector descriptor strings, and target-set count. Use it in an isolated coupon before implementing face selection, orientation, volume-flow/curve binding and motor heat.

The diagnostic requires the solver-idle guard. It destroys the temporary builder and rolls back to an undo mark, then checks objects, expressions, fields, selected-solution boundaries and the modified flag against the original snapshot. Cleanup or restoration failure reports a partial outcome rather than claiming success. It does not save or solve.

Current validation: fake-NX cleanup, precondition and failure tests plus existing flow-boundary and tool-surface tests pass. Real NX deployment and readback are pending. Neither fan creation nor native/export/numerical acceptance is claimed by this change.

Next: inspect the saved two-region Baldower coupon on the offline NX VM; implement explicit native selection and SI readback; verify a single internal connection in exported solver input; then validate mass/energy conservation, orientation reversal and mesh sensitivity. External inlet/outlet pairs are not substitutes for an internal interface.
