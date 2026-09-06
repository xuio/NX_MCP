# NX v2606 integration fork

This fork of [DreamEnding/NX_MCP](https://github.com/DreamEnding/NX_MCP) preserves the upstream history and MIT license. The initial import was deployed against Siemens NX v2606 as `0.2.0.dev2`; subsequent releases extend it through `0.2.0.dev16`. The fork follows upstream base `179086b6de28a53d340132aca7678fa6ed03b422` and retains the deployment history. Machine provisioning, private CAD, credentials and deployment session logs are outside this repository.

See [engineering tools and scoped validation](engineering-tools.md) for the latest solid modeling, sketches, assemblies, materials, project copying, rendering and drafting additions.

See [agent UX](agent-ux.md) for focused discovery, inline artifact retrieval and recovery guidance.

## Included changes

- NX v2606 API repairs, sketch bases, object references and multi-body results.
- Durable operation receipts, retry deduplication, explicit checkpoints and rollback.
- Assembly-aware inspection, workspace artifact transfer and capability reporting.
- Serialized execution in graphical NX with Pause, Resume and Stop controls.
- Native interference and clearance queries, inline viewport PNGs and view metadata.
- Collision highlighting, single-plane capped sections, body/component visibility, colors and transparency with restoration.
- Native sketch solver status, remaining degrees of freedom and persistent constraint-to-geometry links.

The dev16 opt-in integration profile exposes 185 tools, including reference-set/datum controls and compact inventories. Tool status describes scoped validation on NX v2606, not universal certification. Journal execution remains disabled. The default sidecar retains upstream's smaller tool surface unless experimental mode is enabled.

## Start the graphical bridge and sidecar

Use Windows with native Siemens NX v2606 and Python 3.10 or newer. The tested sidecar used Python 3.12, MCP 1.29.1 and Pydantic 2.13.5. Install from this checkout:

```powershell
python -m pip install -e ".[dev]"
```

Before launching NX, set `NX_MCP_WORKSPACE` to a dedicated CAD workspace and optionally set `NX_MCP_UI_DESCRIPTOR` to the desired descriptor file. In graphical NX, play `examples/start_nx_interactive.py`. The journal returns while its retained Win32 callback dispatches commands on the NX UI thread. Stop any batch bridge using the same workspace before attaching it.

In a separate PowerShell window, configure the sidecar to use the same workspace and descriptor:

```powershell
$env:NX_MCP_WORKSPACE = 'D:\NX_MCP_WORKSPACE'
$env:NX_MCP_BRIDGE_DESCRIPTOR = Join-Path $env:LOCALAPPDATA 'nx-mcp\interactive-bridge.json'
$env:NX_MCP_ENABLE_EXPERIMENTAL = '1'
$env:NX_MCP_ENABLE_JOURNAL = '0'
python -m nx_mcp.server
```

Use these same environment values in the MCP client's stdio server configuration. If `NX_MCP_UI_DESCRIPTOR` was customized on the NX side, set `NX_MCP_BRIDGE_DESCRIPTOR` to that exact path. A cross-machine HTTP deployment needs separate transport/authentication and network configuration; no private machine service is bundled here.

See [interactive behavior and viewport capture](../INTERACTIVE-NX.md), [visual tool usage](visual-tools.md), and the runtime `nx_capabilities` result. Long native calls can temporarily block NX. Pause releases model input for manual editing and invalidates agent references/checkpoints; reacquire references on resume. NXOpen mutations are never issued concurrently.

## Verification and upstream proposals

The source matches the deployed runtime. The fork includes local tests and a configurable public MCP visualization regression runner. Historical live-NX results and current upstream-suite gaps are documented in [fork validation](fork-validation.md). Importing the source into this repository does not constitute a new native NX test run.

A series of focused pull requests is preferable to the full integration diff. The [upstream review package](upstream-review.md) maps six proposed slices, supplies a draft first description, and lists compatibility decisions. Current runtime CI and native evidence are recorded in [dev16 acceptance](dev16-validation.json); [dev13 acceptance](dev13-validation.json) retains preceding release-engineering evidence; [dev12 acceptance](dev12-validation.json) retains the preceding documentation results; [dev11 acceptance](dev11-validation.json) retains the earlier freeform/documentation results; [dev10 acceptance](dev10-validation.json) retains sheet-metal results; [dev9 acceptance](dev9-validation.json) retains the exploded-view results; [dev8 acceptance](dev8-validation.json) retains the engineering results; [dev7 acceptance](dev7-validation.json) retains the preceding folder-support results; [dev6 acceptance](dev6-validation.json) retains the preceding authoring results. No pull request has been opened.

Explicit nested and absolute in-workspace file paths, directory creation, and Save As parent creation are described in [project folders](project-folders.md).

See [native exploded views](exploded-views.md) for dev9 presentation and drawing contracts, and the [advanced roadmap](advanced-roadmap.md) for proposed freeform and manufacturing work.

See [native sheet metal](sheet-metal.md) for the dev10 operation catalog, verified scope, flat-pattern exports and measured PMI semantics.

See [freeform, assembly documentation and manufacturing](freeform-manufacturing.md) for the dev11 additions and scoped native verification.

See [editable documentation and manufacturing](documentation-manufacturing.md) for dev12 contracts and acceptance fixtures.

See [release engineering and native acceptance](release-engineering.md) for dev13 drawing authoring, assembly refresh, retained-dimension repair, imported geometry references, mixed units and serial release validation.
