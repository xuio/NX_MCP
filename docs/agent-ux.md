# Agent UX and recovery

Three independent agents sampled live discovery, artifacts and recovery. They
used read-only MCP calls while serial native acceptance ran. This was a focused
usability evaluation, not testing every tool or every geometric option.

## Efficient discovery and artifacts

- Start with `nx_workspace_info`. All file arguments name files on the NX host.
- Use `nx_capabilities(tool="nx_revolve")` or `prefix="nx_sheet"` for focused
  native evidence. Full capability discovery remains available without filters.
- Request `nx_sheet_metal_schema(operation="unbend")` before authoring. Top-level
  `status` describes call success; `validation_status` describes native evidence.
  Length conventions are explicit and independent of whichever part is active.
- Use `nx_workspace_list(path="project", prefix="review", limit=100)` and follow
  `next_offset`. `count` is page size; `total_count` is the filtered total.
- Use `nx_download_file(path="project/view.png", delivery="image")` for an inline
  PNG, with size, resolution and checksum in structured metadata. The PNG bytes
  are MCP image content rather than a large base64 text field. Limit: 8 MiB.
- Use `delivery="metadata"` for one file's size and SHA-256. Default `base64`
  delivery remains available for PDFs/CAD and large images. Follow
  `bytes_returned`, `next_offset` and `eof`; chunk length is 1–262144 bytes.

Discovery and inspection no longer request a model viewport refresh. Drawing
mutations do not invoke a model-view refresh while a drawing sheet is active.

## Recovery

Supply an operation ID before a mutation. After a transport failure, query that
ID. `committed` permits replay of the identical request without repeating its
mutation. A changed payload with the same ID is rejected. `unknown` never proves
failure and never authorizes a blind retry. Receipt identities and query identities
are separate. An earlier-session receipt cannot make old object references valid.

Closing an assembly can cause NX to unload unused prototypes. Inspect returned
`closed_parts` and re-list the session between closes. Reacquire references after
close, rollback or manual handoff. Saving expires native checkpoints; durable
operation receipts survive a bridge restart, but native undo marks do not.

## Response contracts and remaining scope

Every integration tool advertises a common structured output schema for status,
warnings, units and optional operation identity/outcome. Tool-specific result
fields remain extensible; this is not a complete typed schema for every feature
builder. Existing structured/text compatibility is retained. Long native calls
still serialize discovery queries that need installed NX API detection. Generic
PDF delivery remains chunked; there is no inline PDF renderer in the MCP server.

Refresh the client's tool catalog after deployment to discover new arguments.
