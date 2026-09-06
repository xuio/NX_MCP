# Agent surface

The full profile remains compatible: 185 tools with existing defaults. The opt-in
agent profile lists 11 tools: eight core tools plus `nx_discover_tools`, `nx_invoke`
and `nx_result`. All 185 underlying tools remain available, subject to their
existing capability status and native prerequisites.

For stdio, set `NX_MCP_SURFACE=agent`, `NX_MCP_ENABLE_EXPERIMENTAL=1` and
`NX_MCP_WORKSPACE`. The dual HTTP entrypoint `python -m nx_mcp.http_surface` serves
full compatibility at `/mcp` and the agent profile at `/agent/mcp` on port 8765.
Both use the same bridge and serial NX main-thread queue. They must not be used
to issue concurrent mutations. The host must restrict network access as before.

## Discover, invoke, inspect

1. `nx_discover_tools(query="nx_extrude", include_schema=true)` returns the exact
   original input/output schemas, description and agent defaults. Broad queries
   return at most ten descriptions by default (maximum twenty); use `next_offset`.
2. `nx_invoke(tool="nx_extrude", arguments={"sketch_id":"...","distance":5,
   "operation_id":"extrude_unique_001"})` validates the original schema and
   calls the existing implementation. Unsupported fields still fail before NX.
3. Compact results retain opaque references, owner-part identity, occurrence
   paths, units, all warnings, mutation outcome and change counts. Long arrays
   contain at most twenty entries with explicit `omitted` metadata. Repeated
   reference metadata is omitted. Unknown change counts remain null.
4. `nx_result(result_id="result_...", field="/bodies", offset=20)` expands an
   immutable response snapshot. `detail="full"` expands selected object metadata;
   selected arrays remain paged. This never repeats the original mutation.

`nx_invoke(detail="full")` selects the legacy defaults and full original result
**when making a new call**. Do not repeat a mutation to obtain detail; use
`nx_result` instead. After uncertain transport delivery, query
`nx_operation_status` with the original operation ID before retrying. Snapshot
IDs are not mutation receipt IDs. Snapshots persist under `.nx-mcp/agent-results`
until explicitly removed during workspace maintenance; they do not keep NX
references alive. Storage failures fall back to the original full response and
never relabel committed geometry as a failed operation.

Part/component inventories default to compact pages of twenty. Component poses
are omitted unless `include_transforms=true`. Existing filters and explicit
arguments override profile defaults. Every inventory page remains explicit about
its returned and total counts. Geometry vectors/scalars are preserved; use full
snapshot detail for omitted nested arrays and metadata.

## Artifacts

Downloads default to metadata; eligible files have an MCP resource link at
`nx-artifact://workspace/...`. Resource reads return binary content up to 8 MiB.
Internal `.nx-mcp` service files and paths outside the workspace are rejected.
PNG captures retain native MCP image content. Resource bytes should be consumed
by the client outside model text; client behavior determines actual image/token
cost. Larger files use existing chunked downloads programmatically:

```sh
python scripts/download_artifact.py project/model.step ./model.step \
  --url http://192.168.52.10:8765/agent/mcp
```

This streams directly to disk and verifies size and SHA-256. Explicit base64
responses are available through `nx_invoke(detail="full")` for such clients;
compact text excludes binary data. Snapshot detail can contain original binary
fields: do not request these into model context.

## Measuring efficiency

Install the `benchmark` extra and run `scripts/benchmark_agent_surface.py` on an
operations JSONL transcript. It measures exact tokens under the named tokenizer,
not character estimates. Full and compact projections use the same recorded
native tasks. Reports explicitly exclude duplicate transport text, image tokens,
discovery and extra expansion calls. They are **not an autonomous-agent A/B
benchmark or a provider bill**. Optional observed usage JSON can be attached;
missing provider input/cache/output usage remains `unavailable`.

For a real agent comparison, run the same exploded drawing, sheet-metal tray and
imported-part edit tasks with fresh sessions on each profile. Record every
model's provider input/cached/output usage, discovery calls, expansions, retries,
artifact handling, and native task assertions. Sum all workers and repairs.
Do not claim total token savings from response projection alone.
