# Integration output contracts

All integration tools advertise an object `outputSchema`. The envelope requires
`status`, `warnings`, and nullable human-readable `units`. Errors additionally
require `code`, `message`, and `retryable`; error details may identify the operation
and mutation outcome. An error does not satisfy a success payload by returning
empty geometry. Success and error requirements are separate conditional branches.

Tool-specific success contracts cover bounds, distance, volume, topology,
components, extrusion/revolve/pattern results, pairwise interference and clearance,
operation receipts, checkpoints/rollback, workspace listings, downloads and the
main image/CAD/document exports. Dev16 expands this to 47 tool-specific payloads, adding part lifecycle, sketch diagnostics, sheet-metal authoring/inspection, drawing inspection and reference-geometry controls. Inspect the live `tools/list` output for the
exact fields. Other tools retain extensible success payloads; this is not a claim
that all 185 payloads are fully typed.

Geometry references keep opaque IDs separate from names and identify owner parts.
Vectors have three coordinates; matrices contain three rows. Measurement fields
state their coordinate frame. `volume_mm3` always uses cubic millimeters and sums
included bodies; it does not represent geometric union. Collision pair
classification distinguishes `clear`, `contact`, `penetration`, and
`below_clearance`. Bounding envelopes are explicitly exact or conservative.

Download success has one of three shapes: metadata, inline PNG metadata with MCP
image content, or a base64 chunk with `bytes_returned`, `next_offset`, and `eof`.
An absent receipt is `state: unknown`, never proof that a mutation failed. A
committed receipt can carry `reverted_by` after subsequent undo; historical commit
is not proof that the geometry is still present. Reacquire references after
rollback, close, or manual handoff.

These schemas permit additive metadata. They are advertised for client validation;
the server does not turn an already committed NX mutation into a retryable failure
by running an additional payload-validation step afterward. Native acceptance and
fresh MCP workflow tests check actual response conformance. After transport or
client validation failure, query the original operation ID before retrying.
