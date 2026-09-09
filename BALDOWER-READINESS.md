# Baldower thermal/airflow readiness

**NOT READY for coupled Baldower cooling comparisons.** The standalone thermal and
Flow subsets below are usable, but they do not establish the required coupled
heated-solid/air/fan workflow at a verified room-temperature ambient. Do not start
Baldower-specific simulations on the strength of this release.

This report supersedes the broad feature backlog for this handover. No additional
infrastructure features are planned unless they resolve a concrete readiness blocker.

## Source and deployed identity

- Engine checkpoint: `c470bd007ca1a83556b79f910aefbf8b408a697c`, branch
  `simcenter/thermal-flow`, fork `xuio/NX_MCP`.
- Native target: NX/Simcenter 3D 2606, executable build `2606.1700`, bridge protocol 1. Dedicated Simcenter UI
  session `20bc234ffa5249ceb4fb4d82b993c626`.
- Deployed source: `C:\ProgramData\BasementHypervisor\nx-mcp-simcenter\source`.
  Workspace: `D:\CAD\SIMCENTER_MCP_WORKSPACE`.
- [Final engine audit](tests/simcenter/evidence/coupled-bindings-deployment.json): 78 public
  handler signatures matched; every audited Simcenter Python source hash matched
  this checkpoint. [Runtime/helper audit](tests/simcenter/evidence/baldower-readiness-runtime.json)
  verifies the current installed helper hashes against the committed C# source.
  This audits signatures/files and direct property-reader
  bindings, not every in-memory dependency or every API option.
- The regional-temperature change is complete: native/public paging, independent
  two-solid checks, result-file guards and save/close/reopen passed. Latest UI
  displays the fitted isolated coupled fan authoring copy. No product model was edited.
- This report and companion audit are delivery-only additions after the engine
  checkpoint. Their Git commit is obtained with `git log -1 --format=%H -- BALDOWER-READINESS.md`.

## Primary gate and blocker classification

1. **Room-temperature global environment is not verified.** Native readback of
   `Fluid Temperature` is 20 °C but exported XML contains 0 °C. The guard rejects
   export. Specified absolute pressure reads 101325 Pa but exports 0 Pa; that guard
   also rejects export. These are demonstrated request/native/export differences,
   with unresolved native/API semantics. Neither a Siemens defect nor an MCP
   material-authoring defect is established. No equivalent UI-authored comparison
   has established the missing mapping.
2. **The atmospheric density experiment did not isolate atmospheric adjustment.**
   The retained log reports 1.207 kg/m³ × 1.0724 = 1.2943868 kg/m³, consistent with
   its printed adjusted density. Those runs selected altitude-derived pressure,
   global 0 °C and separate 20 °C inlet/opening temperatures. This explains the
   number but not precedence over the assigned material density. It does not prove
   room-temperature effective properties. The explicit-pressure case stopped at
   export; it is not a completed comparison with altitude mode disabled.
3. **Coupled fan authoring now passes; export/execution is unverified.** Public
   `nx_sim_assign_fan` and `nx_sim_head_loss` now support coupled inlet/opening
   bindings. Creation, committed readback, replay, conflict/stale rejection and
   save/close/reopen passed in [the public receipt](tests/simcenter/evidence/coupled-fan-public.json).
   A [native update/failure test](tests/simcenter/evidence/coupled-loss-update-native.json)
   verified coefficient changes and rollback. These are authoring checks, not a
   coupled fan operating-point benchmark. The retained heated finned case used a
   velocity inlet. Coupled fan export and numerical validation remain missing tests,
   not established external limitations.
4. **The required coupled mesh comparison has not passed.** The extended layered
   case has useful convergence/heat-transfer evidence, but the finer case reached
   its iteration limit. Both use global 0 °C. Their similar temperatures do not
   establish an accepted room-temperature, fan-driven mesh comparison.

The bounded review reused retained native evidence because `coupled_input.py` and
`input_export.py` still exactly match their hashes in the native pressure-guard
receipt. Preparation has since gained mesh guards; that does not alter export
semantics. No further solve, material sweep, input correction, generated-file edit,
licensing change or UI-coordinate workaround was used.

Reproduce the evidence audit from the repo root:

```sh
python examples/simcenter/audit_baldower_readiness.py
```

It checks the current guard hashes and retained mismatches; it does not fabricate
live acceptance. Output: [readiness audit](tests/simcenter/evidence/baldower-readiness-audit.json).
The coupled binding probe initially stopped before mutation because its old fixture
name was no longer loaded ([retained failure](tests/simcenter/evidence/coupled-fan-binding-missing-fixture.json)).
After inspecting the current inventory, the [bounded native probe](tests/simcenter/evidence/coupled-fan-binding-native.json)
verified documented mode 5, scale 1 and coupled Head Loss factory context, then
restored bindings, field/table inventories and all modified flags. The public
fixture is `ui-benchmarks/E-coupled-fan-public-20260909-r1/coupled_fan_public_r1.sim`.
Reproducer: `examples/simcenter/verify_coupled_fan_public.py`; it refuses an existing
receipt and never exports or launches a solver. Its SIM-only copy shares FEM/CAD
and must not be used to edit their geometry.

Minimal native reproducers: [temperature guard](examples/simcenter/verify_coupled_ambient_guard.py)
and [specified pressure](examples/simcenter/probe_finned_specified_pressure.py).
They require their named isolated fixtures and fresh output folders. **Do not rerun
fixed job IDs or overwrite retained directories.** Read the existing
[temperature receipt](tests/simcenter/evidence/coupled-ambient-guard-native.json),
[pressure receipt](tests/simcenter/evidence/coupled-pressure-guard-native.json), and
[density context](tests/simcenter/evidence/density-atmospheric-context.json) first.

Exact next action: establish one documented, native room-temperature global
ambient/pressure configuration whose effective exported property model is understood.
A qualified native/UI-authored reference or authoritative API mapping is needed;
retain both guards. Then verify coupled fan/resistance export and execute only
the bounded gate below. The current evidence does not justify blaming Siemens or
silently treating 0 °C as the requested 20 °C.

## Requirement-by-requirement audit

“Verified” below is limited to the cited fixtures; offline tests are separate.
Evidence paths are under `tests/simcenter/evidence/`.

| Required capability | Supported result and evidence | Remaining limit / gate |
|---|---|---|
| Isolated CAD/FEM/SIM variants | Native plan/clone/receipt and replay: `native-variant-tools-mcp.json`; standalone saved Flow chain | General assemblies and arbitrary missing-dependency recovery not verified. Save-as alone shares FEM/CAD. |
| Materials and heat sources | Constant material/assignment, body watts and distributed heat: `native-scenario-multi.json`, `native-distributed-heat-mcp.json` | Record provenance, total heat and selections; do not double-count conversion power. |
| Conduction/contact | `contact-explicit-numerical-acceptance.json`: Tmax 294.401486 K vs 294.4 K (0.03 K tolerance); contact drop 0.499074 K vs 0.5 K (0.01 K tolerance); aggregate rejection 1 W | Scoped 200-element two-block benchmark. Not product accuracy or general contact options. |
| Explicit thermal environment | Kelvin face temperatures and specified convection environment; existing external-condition readback/export/reopen | Global coupled temperature/pressure mismatch blocks requested environment. |
| Solid/fluid meshes and wall/local controls | `mesh-plan-public.json`, `local-size-public.json`, `remesh-public.json`; explicit body plans, wall-layer and face-size effects | Fluid/layered remeshing is not verified. Authoring is not mesh convergence. |
| Fixed-speed fan P–Q | Native static-pressure table and Flow inlet assignment; `native-fan-operating-points-mcp.json` | Coupled binding/replay/save-reopen verified in `coupled-fan-public.json`; coupled export/operating point unverified. No total-pressure or acoustics claim. |
| Opening resistance | Native scalar head-loss modes/active coefficients, Flow fixtures | Coupled creation/replay/persistence and native update/rollback verified; coupled pressure-loss response unverified. Not general porous media. |
| Prepare/export/launch/reconnect | `mesh-guard-positive-launch.json`, `mesh-guard-positive-finish.json`; canonical XML identity, persistent observer, terminal gate release | Preserve jobs after transport failure. No rerun because observation expires. |
| Temperatures/regions | `temperature-regions-public.json`, `temperature-regions-lifecycle.json`; native groups, locations, nodal mean; node pages | Group-to-component meaning must be recorded per model; means are not volume/area weighted. |
| Pressure, airflow, fan point | Native pressure/flow field and boundary extraction, `native-fan-operating-points-mcp.json`, existing duct comparison scripts | Conventions and selected surfaces must be explicit; Flow evidence is not coupled fan acceptance. |
| Mass/energy diagnostics | Native log parsers and retained coupled/contact summaries | Rounded aggregates are not boundary integrals. V aggregate sink is 1 W but named sink row is 0.9732 W; unreconciled, retained. |
| Result identity/freshness | `mesh-result-stale-public.json`, `mesh-result-restored-public.json`; changed mesh marks historical result stale; file hash paging guards | Partial material/boundary/mesh coverage only. No whole-model freshness, especially for coupled settings/external dependencies. |
| Contours/artifacts | Temperature/pressure postviews; `native-conduction-screenshot.json`; download checksums | Actual viewport size may differ from request. Image is not numerical evidence. Current capture/retrieval verification is retained, not a new test of every render option. |
| Variant comparisons | Existing bounded duct/refinement scripts plus explicit group/node extraction | General study engine deferred. Required coupled fan mesh comparison remains unaccepted. |
| Cancellation | Pre-launch cancellation and idempotent job state supported | Running cancellation unverified, not a readiness blocker. Never kill a solver as a substitute. |
| Deployment/reconnect | 78 live handlers/source hashes; fresh stdio clients in public tests; native private-helper loading retained | Current NX process was not cold-restarted because it contains unrelated unsaved work. |

See [capability evidence index](src/nx_mcp/simcenter/release_evidence.py) and
[scoped native details](docs/simcenter.md) for exact supported parameters and
additional receipts. Missing tests above remain missing tests, not external defects.

## Compact practical workflow

Use the existing dedicated Simcenter bridge, one mutation at a time. Query actual
schemas before authoring. A small scripted set of 2–3 variants is sufficient.

1. Inspect `nx_sim_documents`, then `nx_sim_variant_plan` and
   `nx_sim_variant_create` with a fresh folder/name and expected plan hash. Preserve
   the plan and `nx_sim_variant_receipt`. For geometry changes, clone/reassociate
   FEM and CAD; `nx_sim_save_as` only isolates the SIM and its output directory.
2. In each analysis copy, assign material/collector IDs, body heat and contacts.
   Inspect actual committed values, field scales and face/body selections. Use
   `nx_sim_scenario_preview` before scenario application and retain the power total.
   For thermal-only verification reuse `prepare_contact_resistance_benchmark.py`
   and `verify_contact_public.py`; do not rerun their existing fixture paths.
3. Create supported wall/local controls before meshing; use `nx_sim_mesh_plan` for
   explicit solid/fluid bodies. Read mesh quality, control settings and
   `nx_sim_mesh_state`. Treat disconnected regions and unmeshed bodies as failures.
4. For **Flow or coupled authoring**, use `nx_sim_fan_table` with SI pairs
   `[m³/s, Pa]`, `pressure_convention="static"`, reference RPM/density, curve range
   and provenance; assign it to an existing inlet with `nx_sim_assign_fan`.
   Inspect inlet orientation/pressure references. Use the native opening resistance
   mode and coefficient via `nx_sim_head_loss`; do not combine free-flow and shutoff
   pressure as one operating point. Motor heat must be explicitly assigned.
5. **Stop coupled work at the current readiness gate.** A successful external
   boundary-temperature setting does not override the unresolved global reference.
   Do not bypass export guards. Once unblocked, save each FEM/SIM explicitly and
   prepare into a directory containing only that isolated SIM. Use one fresh job
   ID and stable mutation operation IDs. Export and inspect before launch.
6. `nx_sim_launch` is not completion. Reconnect with `nx_sim_job_status`,
   `nx_sim_observe_job` and bounded log reads. Inspect terminal evidence and
   `nx_sim_release_job`; never recycle an old job/output folder. Existing examples:
   `launch_mesh_guard_positive_public.py` and `audit_contact_numerical_mcp.py`.
7. Get `nx_sim_result_identity(document, job_id=...)`. For each result hash call
   `nx_sim_temperature_regions` with explicit dimension/group index, field iteration
   and budget. Record a mapping such as “3d group 1, bounds [0..10,...] = heated
   block” based on geometry/source evidence, not index order. Inspect extrema
   locations and the stated unweighted mean. Page `nx_sim_temperature_nodes` for
   portable tables. Discard accumulated pages on changed hash.
8. Show `nx_sim_show_temperature` or `nx_sim_show_pressure`, then call
   `nx_screenshot(style="current", background="original", fit=True)`. Retain actual
   resolution/camera and download the returned artifact using `nx_download_file`
   with chunk hashes, or the existing `scripts/download_artifact.py` on an already
   authorized HTTP endpoint. Do not establish a new network endpoint just to export.
9. Store returned structured JSON and CSV node columns
   `result_sha256,loadcase,iteration,index,label,x_mm,y_mm,z_mm,temperature_degC`.
   For two variants compare the same group meaning, workload, ambient and field
   iteration. Keep input/dependency hashes, material/BC/settings readback, fan curve,
   mesh digest/counts, job ID, observer evidence and result-file hash beside every
   table. Do not compare a geometric change against a changed power assumption.

Small reference scripts already in `examples/simcenter/` include
`verify_temperature_regions_public.py`, `verify_temperature_regions_lifecycle.py`,
`audit_fine_duct_comparison.py` and `audit_refinement_comparison.py`. They operate
on named generic fixtures; inspect prerequisites and choose new isolated paths for
new authoring. They are not a Baldower simulation recipe with approved loads.

Portable table example (no NX mutation or solve):

```sh
python examples/simcenter/export_region_receipt.py \
  tests/simcenter/evidence/temperature-regions-public.json /tmp/contact-regions-new \
  --responses first second --region-map '{"sink":0,"heated":1}' \
  --scenario-id contact-explicit-1W-293.15K --job-id contact-explicit-r1
```

The script requires complete group pages from one file revision and writes
`regions.json` plus `regions.csv` into a new directory. Job/scenario labels and
semantic mapping are caller-supplied, not automatically certified. Preserve the
job manifest and verify its input/mesh/result association separately. For a
comparison, use the same scenario ID and verified region meaning, then subtract
maximum temperatures or nodal means only with their stated identical definitions.
Do not treat differences between different discretizations' unweighted nodal means
as volume-weighted thermal changes.

## Coupled gate to declare before any future solve

Use a generic small heated solid/fins and air duct, never Baldower geometry.
Declare 20 °C external ambient/inlet, 101325 Pa absolute reference, the selected
native fluid model and its expected density at those reference conditions, gravity,
0.1 W total heat, interface treatment, and an explicitly assumed fixed-RPM **static**
fan curve with no extrapolation. Record motor heat separately. Verify native state,
export and effective solver representation before launch; any mismatch stops the run.

Predeclare a bounded pair of meshes and the native convergence limits. Suggested
infrastructure sanity gates (to be justified against the final fixture before use):
all configured residual/temperature criteria satisfied before iteration limit;
flow in intended direction; fan operating point inside the curve range and within
2% of tabulated pressure rise (or a declared absolute tolerance near zero);
reported mass imbalance <0.1%; heat rejection within 1% of applied heat with all
boundary definitions explained; no unexpected negative temperature rise; refining
once changes peak temperature rise and flow by <5%. Incomplete diagnostics or an
unconverged finer mesh fail this gate. These are **not executed acceptance results**
and do not establish Baldower accuracy or acoustic limits.

## Build, deployment and verification

No licensing/configuration changes or new software installations were performed
for this handover. On an approved stopped/clean installation, the existing procedure
is:

```powershell
python -m pip install -e ".[dev]"
powershell -File examples\simcenter\build_evaluator_helper.ps1 -NxRoot '<installed NX root>' -SourceRoot '<checkout>'
```

The helper uses installed NXOpen assemblies and the existing Framework x64 compiler;
its manifest binds source and binary hashes. Native allocation/evaluation/free stay
inside C#. Play `examples/start_simcenter_interactive.py` from the checked-out
source in the approved graphical Simcenter session, then start the external sidecar
with the existing workspace/descriptor and `NX_MCP_ENABLE_SIMCENTER=1`,
`NX_MCP_ENABLE_EXPERIMENTAL=1`, `NX_MCP_SURFACE=full`. See
[README startup](README.md#start-graphical-nx) and [UI lifecycle](INTERACTIVE-NX.md).
Keep journal invocation disabled unless explicitly needed for the versioned adapter.

Private-helper loading passed on this host with its existing .NET Author capability;
other installations may require administrator-provided loading/signing prerequisites.
Do not change licensing or bypass authentication. Read
`evaluator-helper-load-simple-class.json` and `evaluator-helper-geometry.json`.
The simple class name is required by the retained `Session.Execute` loader.

For packaged delivery, `python scripts/build_release.py --output <outside-repo-dir>`
builds from a clean committed checkout. `scripts/install_release.ps1` verifies the
bundle and refuses a live bridge descriptor; it must not be run against the active
session. A fresh packaged install of this checkpoint has not been exercised here.
The current deployment is a verified source update to the existing runtime.

Offline release regression:

```sh
python -m pytest tests/simcenter -q -m 'not real_nx'
```

**703 passed in 7.47 s**, recorded in
[baldower-readiness-regressions.txt](tests/simcenter/evidence/baldower-readiness-regressions.txt).
Two additional readiness/export tests pass (`tests/simcenter/test_readiness_scripts.py`);
[exported JSON](tests/simcenter/evidence/baldower-readiness-regions.json) and
[CSV](tests/simcenter/evidence/baldower-readiness-regions.csv) retain the two native
contact-region summaries and explicit scenario/result identity. After the coupled admission change, 46 focused head-loss, fan-field, public-schema,
readiness and evidence-index tests passed; the two readiness tests passed again
after adding explicit authoring-versus-numerical assertions. Native/public evidence
is separate. `examples/simcenter/verify_deployed_signatures.py`
runs through the existing journal adapter and emits the live handler/hash audit.
Do not restart NX, close unrelated parts, save-all or reuse probe slots concurrently.

## Handover and deferred work

baldower MECH may use the verified standalone extraction/thermal/Flow subsets with
these limitations. It must not represent the full coupled cooling workflow as ready.
The immediate handover action is to retain this NOT READY gate, obtain the missing
native ambient/pressure reference, and resume only the bounded coupled fan gate.
No product geometry, power assumptions, firmware limits or mechanical decisions
are changed by this report.

Advanced radiation/material laws, hot starts, native temperature-controlled fans,
general porous media, generalized studies, comprehensive freshness and unrelated
feature work are deferred. Running cancellation remains an explicit limitation.
No broad-backlog work should resume after the readiness handover.
