# Upstream review package — proposal only

No pull request has been opened. This document prepares the discussion with DreamEnding/NX_MCP; it does not imply maintainer agreement or a supported-version commitment from Siemens.

Comparison base: `179086b6de28a53d340132aca7678fa6ed03b422`, the recorded upstream base of this fork. The fork retains upstream history and the MIT license. Review the actual current diff with:

```sh
git diff --stat 179086b6de28a53d340132aca7678fa6ed03b422...master
git log --reverse --oneline 179086b6de28a53d340132aca7678fa6ed03b422..master
```

The integration has grown beyond a suitable single PR. These are proposed review slices, in dependency order. Existing shared modules span slices; preparing mergeable branches will require extracting cohesive changes, not blindly cherry-picking deployment commits.

| Proposed slice | Concrete change and principal files | Reviewer evidence |
| --- | --- | --- |
| 1. NX 2606 correctness repairs | Sketch local-to-world mapping, default extrusion normal, supported feature lookup/builders, STEP translator, loaded-part activation and multi-body results. `nx_bridge.py`, `hardened.py`, `utils/selection.py`. | Principal/custom plane solids, edited bounds/volume, import round trips, existing workflow regression tests. |
| 2. References and recovery | Owner/session/generation references, stale rejection, durable mutation IDs, deduplication and checkpoint rollback. `runtime.py`, `recovery.py`, executor and bridge boundaries. | Retry/failure/rollback tests; explicit partial/unknown outcomes; save-boundary semantics. |
| 3. Assembly inspection and artifacts | Occurrence-aware bounds/distance/interference/clearance, workspace transfers, structured results and capability metadata. `inspection.py`, `integration_server.py`, `workspace.py`. | Native transformed fixtures, analytic overlap volumes, ZIP/PNG checksums and round-trip receipts. |
| 4. Graphical NX host | Serialized Win32 UI-thread dispatch, manual handoff and view capture. `interactive.py`, graphical startup example, `bridge.py`. | Native thread identity, visible viewport artifacts, handoff and stop tests. Windows-specific scheduler must remain isolated. |
| 5. Authoring and presentation | Display/sections, expressions, atomic sketch edits, report/presentation/preview tools, exact selection and associative component patterns. `visual_tools.py`, `authoring.py`, `advanced_authoring.py`, `review_tools.py`. | Public MCP acceptance runners, editable native patterns, saved/reopened geometry rules, parameter and constraint checks. |
| 6. Reproducible release and documentation | Hash-locked Windows dependencies, offline packaging/install/rollback, CI and scoped validation receipts. `scripts/`, lock files, release workflow, docs. | Hosted OS/Python matrix, coverage gate, Windows release artifact and installed-source hashes. |

## Draft description for the first proposal

**Title:** Correct sketch coordinate mapping and native feature lookup on NX 2606

Sketch profiles requested in XZ could previously be created in XY, and feature lookup used an unsupported collection method. Map sketch-local points through the requested basis, derive extrusion direction from the sketch normal, and use the installed collection API. Return sketch origin/basis/normal so callers can verify the coordinate frame.

Validation should accompany the extracted branch: XY/XZ/YZ and arbitrary-basis curve coordinates, independently expected solid bounds/volumes, a feature edit, and failure rollback. Keep unrelated assembly/UI tools out of this first review so the geometry fix is straightforward to assess.

## Compatibility and decisions for maintainers

- The larger integration is opt-in; keep the upstream default surface stable. Version-specific capability status must mean a documented tested scope, not general certification.
- Keep opaque IDs distinct from names/journals and use consistent structured success/error envelopes. Review that additive metadata is acceptable to existing clients.
- Nearest geometry ordering changes in dev6 from bounds-center distance to actual BREP distance. Independent component patterns retain their tool; native associative patterns use distinct tools.
- NXOpen mutations must remain serialized. The graphical timer is Windows-specific; any alternative host needs equivalent thread and handoff guarantees.
- Journal execution remains separately disabled by default. File transfer remains confined to the configured workspace. Private CAD, deployment credentials and host provisioning are excluded from the public fork.
- Confirm an NX version/CI policy and how maintainers want native evidence supplied. Mock tests cannot establish geometric correctness or SDK availability.
- Decide whether the larger authoring tools belong in core, an optional profile or a separate package before extracting those review branches.

## Evidence and scope

See [fork validation](fork-validation.md), [dev5 acceptance](dev5-validation.json), [advanced authoring](advanced-authoring.md), and the current `nx_capabilities` manifest. Retain historical receipts as historical; do not rewrite old test counts as current results. Deployment commits include documentation-only follow-ups, so cite the runtime source commit recorded in each receipt.

No claim is made that every boolean, blend, chamfer, hole, sweep, mirror, mate, drawing or PDF operation is broken or verified. Controller design clashes and unresolved envelopes are design evidence, not MCP defects. A scoped native pass is evidence for its fixture and API, not a universal NX certificate.
