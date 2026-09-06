# Consolidated dev14 release

Dev14 packages the dev13 runtime, validation-runner fixes and capability metadata
together. No validation overlay is required. Installation removes obsolete overlay
metadata; rollback restores the prior runtime and its original metadata.

Three failures reproduced during native acceptance are addressed:

- Closing an assembly can unload unused prototypes despite `CloseWholeTree=False`.
  The result now reports `closed_parts`, `closed_count` and `remaining_count`, and
  invalidates references for every unloaded part. Re-list parts between closes.
- Native bridge receipt queries preserve the target operation ID, session and
  mutation outcome. Query identity is separate. HTTP receipt queries already read
  the durable store directly.
- The STEP translator can accept a truncated file and import partial geometry.
  Missing exchange-file opening/closing markers now fail before translation. This
  is a completeness check, not a complete STEP syntax or geometry validator.

`examples/validate_hard_geometry.py` adds truncated vendor STEP, native hole-face
healing, removed anchors, rotated nested mixed-unit assemblies and three adjacent
mitered sheet-metal walls. It is included in the serial native release runner.

`examples/validate_transport_recovery.py` runs on Windows beside the bridge. Set
`NX_BRIDGE_DESCRIPTOR`, `NX_WORKSPACE` and `NX_VALIDATION_OUTPUT`. It disconnects
before receiving a relative-move result, verifies the committed receipt, retries
the same ID, checks rollback and manual handoff, then restores the prior session.
Tokens remain local and are never written to test receipts. Keep the receipt to
verify it after a real bridge restart; an old receipt never restores old IDs.

Native validation results must be recorded against the exact deployed package.
