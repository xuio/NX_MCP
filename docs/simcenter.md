# Simcenter extension

Development branch: `simcenter/thermal-flow`. This extension is separate from the
NX CAD integration PR. Enable `NX_MCP_ENABLE_SIMCENTER=1` in both the NX journal
host and MCP sidecar. Without that flag the existing CAD tool surface is unchanged.
NXOpen imports remain inside the NX process.

## Delivery phases (current goal)

Phase 1 has a supported-scope checkpoint: implementation `90b2cc8` and retained
native evidence `c3e1e1d`, pushed to `simcenter/thermal-flow`. CAD evaluators,
field/membership inspection, head-loss export/persistence, scoped freshness,
pre-launch cancellation and deployed handler compatibility have the evidence
listed below. Native step-level load assignment, running-solver cancellation and
ambient-export/density behavior remain explicitly unresolved; no blanket numerical
or whole-model freshness claim is made.

Phase 2 is active. `nx_sim_contact` now authors the documented
`Contact Thermal Coupling` with explicit primary/secondary CAE face sets and total
resistance (K/W) or conductance (W/K). Native tests verify 0.5 K/W and 2 W/K,
selectors, units, both target sets, solution membership and rollback. Public MCP
verifies discovery, overlap rejection, creation, replay, inventory and save/reopen;
resistance properties/provenance and actual per-side geometry persist. Native
opening marks the isolated SIM modified; the warning is retained. Conductance
persistence and both unit-converted exports now pass. A 200-element steady
resistance benchmark now passes scoped physical and explicit-convergence artifact
checks. The earlier Automatic-mode run remains inconclusive on its effective criterion.
The current fixture is `ui-benchmarks/B-contact-authoring-20260909-r1/`.
Evidence: `contact-authoring-native.json`, `contact-public.json`,
`contact-persistence-public.json`, `contact-reopened-targets.json` under
`tests/simcenter/evidence/`. `contact-authoring-r1-failure.json` preserves a
rolled-back direct-expression readback guard error, now corrected and covered by
a regression test. Earlier descriptor failures used incorrect names, not an
unavailable contact module. No new licensing or solve-availability claim is made.

### Contact numerical acceptance (scoped)

The two 10 × 10 × 10 mm blocks use k=200 W/(m K), 1 W uniform generation
in the left block, R=0.5 K/W at the interface and a 293.15 K right end.
Other exterior faces have no applied flux. The mesh has 200 linear tetrahedra
and 90 nodes; setup/meshing/material/boundary/export calls took about 6.3 seconds
in total (per-stage timings are retained).

| Check | Actual | Expected / tolerance |
|---|---|---|
| Maximum temperature | 294.401486 K | 294.4 K ±0.03 K |
| Interface temperature drop | 0.499074 K | 0.5 K ±0.01 K |
| Heat rejection | 1 W from rounded native summary | 1 W ±0.001 W |
| Final temperature change | 1.671e-8 K, two iterations | Explicit 0.001 K limit; 100-iteration cap |

The interface values are arithmetic means of 12 native nodes per side, identified
by adjacent-element connectivity; they are not area-weighted averages. Exported
0.5 K/W appears as 5e-7 and 2 W/K as 2e6 in native mN-mm-second units. Contact XML
`Selection step=1/2` denotes the primary/secondary target sets here, not solution
step membership. The original native files are never rewritten.

Reproduce without NX or another solve:
`python examples/simcenter/audit_contact_acceptance.py`.
Evidence lives under `tests/simcenter/evidence/contact-*`; the exact solved XML,
log, nodal data, predeclared tolerances and input/result hashes are retained.
`contact-resistance-r1` is the permanent job identity; never rerun it. New-client
MCP observation, temperature extraction and native contour display passed.

The original Automatic-mode run remains physically consistent but inconclusive on
its effective stopping criterion. The installed Open CAE reference maps selector
0 to Automatic and 1 to Specify; the temperature-change field is active only for
Specify. `nx_sim_steady_thermal_controls` now sets the associated native
`Thermal Parameters` table, verifies selectors, units and values, and rolls back
unsupported/ignored changes. Native save/close/reopen preserves the controls;
public discovery, invalid arguments, replay and exported settings pass.

A separate immutable job, `contact-explicit-r1`, uses Specify, a 0.001 K maximum
temperature change and a 100-iteration cap. The additional heat-imbalance stopping
criterion is disabled for this numerical test. All eight artifact checks pass,
including convergence, physical values and saved input/result identity. Reproduce:
`python examples/simcenter/audit_contact_acceptance.py --prefix contact-explicit`.
Evidence: `contact-explicit-numerical-acceptance.json`, its hashed inputs,
`steady-controls-native.json` and `steady-controls-public-launch.json`.
Optional relative heat-imbalance authoring and persistence were verified natively
at 0.001 (fraction, not percent); its numerical stopping behavior was not tested.

Whole-live-model acceptance remains unproven: native solving marked the SIM
modified. Saved dependency hashes, canonical input, observed result association
and the supported thermal-state comparison match; current-session whole-model
freshness remains `not_verified`. No mesh convergence, transient contact,
acoustic or product-engineering claim follows from this test.

### Convection temperature dependencies

`nx_sim_convection` now accepts `temperature_source`: `fluid_ambient` (the
compatible default), `radiative_ambient`, or `specified`. The last requires
`temperature_k` in Kelvin; other modes reject it. The implementation sets and
checks the native constant-coefficient/top-side selectors, unit-bearing expressions,
actual CAE face targets and active-solution membership. Flow/coupled solutions
remain rejected to avoid double-counting solved solid/fluid transfer.

A 10 mm cube with 100 tetrahedra verifies all three selectors natively and through
public MCP. Creation/replay, save/close/reopen, stale references and export pass.
Each boundary targets one different geometric face, producing 14 disjoint finite
element faces per selection. The specified 293.15 K value exports as 20 °C using
the recorded -273.15 temperature shift; this is the expected representation.
The 10 W/(m² K) coefficient is preserved. Ambient-mode temperature fields are
inactive and are not interpreted as effective ambient temperatures.

Reproduce the retained export check with
`python examples/simcenter/audit_convection_environment_export.py`.
Evidence: `convection-environment-native.json`, `convection-environment-public.json`,
`convection-environment.xml` and `convection-environment-export-audit.json` under
`tests/simcenter/evidence/`. `convection-environment-recovery.json` verifies actual
face bounds after reopen/SaveAs and native undo after an injected post-commit
readback failure, including removal of new constraints/expressions and preserved
document flags. The initial public invalid-dependency response said `unknown`;
`convection-environment-preflight.json` records the corrected `not_started` outcome
and unchanged boundary inventory. No solver was launched for this structural extension.
Time-dependent fields, shell-side options and resolved ambient dependencies still
need implementation/verification; this is not complete general convection support.

### Simple environment radiation

`nx_sim_environment_radiation` authors the installed `Simple Environment Radiation`
constraint. It explicitly selects top-side effective-emissivity mode, accepts a
constant dimensionless `effective_emissivity` in [0,1], and selects fluid ambient,
radiative ambient (default), or a specified Kelvin environment. This effective
value is not an optical-material assignment or an enclosure view-factor solution.
Unsupported shell-side and time-field options are not exposed.

A 10 mm cube / 100-element fixture verifies all three temperature sources through
native authoring/readback and public MCP. Native trials roll back; public creation,
replay, save/close/reopen, stale-reference rejection and native export pass. The
export retains effective emissivity 0.8, distinct 14-element-face regions, and
293.15 K as 20 °C with the explicit -273.15 shift. Ambient fields are inactive and
are not interpreted as resolved global temperatures. Reproduce the retained check:
`python examples/simcenter/audit_radiation_environment_export.py`.

Evidence: `radiation-environment-native.json`, `radiation-environment-public.json`,
`radiation-environment.xml`, `radiation-environment-export-audit.json` and
`radiation-environment-recovery.json` in
`tests/simcenter/evidence/`. Native failure injection confirms that an invalid
post-commit readback rolls back new constraints and expressions without changing
document flags; face bounds persist through reopen/SaveAs. This is
API/lifecycle/export verification; no radiation
solve or heat-balance acceptance is claimed. The native factory also accepts
`Override Thermal Emissivity` and `Enclosure Radiation` (two target slots), retained
in `radiation-descriptors-native.json`. The follow-up below verifies a committed subset of those objects. Licensing
configuration was not changed.

### Enclosure radiation and emissivity overrides

`nx_sim_emissivity_override` authors the native `Override Thermal Emissivity`
simulation object with a dimensionless constant and explicit both/top/bottom side
selector. `nx_sim_enclosure_radiation` authors `Enclosure Radiation` using the
deterministic calculation method and explicit ambient-inclusion boolean. Both
verify actual CAE faces, selectors, values, provenance and active-solution
membership. The enclosure uses documented primary target set 0 and verifies its
second set remains empty; secondary-region semantics are not exposed.

One 10 mm cube / 100-element fixture covers three emissivity-side selectors and
both ambient-inclusion values under native rollback. Individual authoring/readback
calls took 0.33–0.38 seconds. Public MCP verifies discovery, invalid emissivity
rejection, creation/replay, save/close/reopen, stale-reference rejection and export
for both-side emissivity 0.8 plus deterministic enclosure with ambient inclusion.
Each object exports the same 84 finite-element faces. Inactive Monte Carlo/GPU
properties are retained but excluded from active-setting comparisons.

`radiation-objects-recovery.json` verifies that both injected post-commit failures
roll back objects, expressions and solution membership without changing document
flags. Both six-face geometric regions persist through reopen/SaveAs. Evidence:
`radiation-objects-native.json`, `radiation-objects-public.json`,
`radiation-objects.xml`, `radiation-objects-export-audit.json` and the recovery
receipt under `tests/simcenter/evidence/`. Reproduce the export audit with
`python examples/simcenter/audit_radiation_objects_export.py`.

This verifies native authoring/lifecycle/export, not cavity closure, shell-side
physical interpretation, view-factor accuracy, ambient effective temperature or
numerical heat balance. It does not establish Monte Carlo/GPU support or full
thermo-optical material authoring. Existing conflicting overrides are not removed
or resolved automatically. No solver was launched for these checks.

### Reusable scalar thermal tables

`nx_sim_scalar_table` creates a registered native one-dimensional table in the
active millimeter SIM. Supply `document`, `name`, `axis` (`time` or `temperature`),
`quantity`, `samples` and `provenance`. Samples are 2..1000 finite `[axis,value]`
pairs with a nonnegative, strictly increasing axis. The public axis units are
seconds or Kelvin. Value quantities and units are power (W), temperature (K),
conductivity (W/(m K)), heat capacity (J/(kg K)), density (kg/m³) and convection
coefficient (W/(m² K)). Property-specific physical limits belong to the binding
operation; the generic table does not attach itself to a material or load.

NX normalizes a temperature independent axis to Celsius without converting the
supplied numbers. This adapter explicitly uses native unit conversion from Kelvin
to Celsius before creating the table, then verifies SI readback. Linear 1D
interpolation and undefined values outside the table are stored and checked.
Consumers must validate their required domain; no extrapolation is implied.

Example: `nx_sim_scalar_table(document=sim_id, name="POWER_TIME", axis="time",
quantity="power", samples=[[0,0],[10,1],[20,0]], provenance="Assumed API fixture")`.
`nx_sim_scalar_tables(document=sim_id, limit=20, include_samples=False)` returns
compact, paginated definitions. Set `include_samples=True` for complete native SI
samples. Creation returns a typed field reference and checksummed provenance.
Property inspection reports registered definitions and wrapper scale separately.
It does not evaluate opaque native field pointers.

Native NX v2606 verification covers all twelve axis/quantity combinations and a
heat-load property wrapper with scale 2. Public MCP verification covers three
tables, operation replay, invalid requests, compact/full paging, stale references
and identical samples/metadata after save/close/reopen. Native failure injection
verifies creation rollback and corrupted metadata rejection without changing
unrelated document flags. Reproduction scripts are
`examples/simcenter/verify_scalar_tables_{native,public,recovery}.py`; run the
native fixture through the existing serialized probe harness, then the public
client, then recovery. Retained receipts are
`tests/simcenter/evidence/scalar-tables-{native,public,recovery}.json`.
`scalar-table-unit-probe.json` retains the earlier unconverted Kelvin-axis probe;
its trial fields were rolled back. It is evidence of API unit normalization,
not a physical acceptance case.

These checks establish table authoring/readback and persistence. They do not yet
establish temperature-dependent material assignment, transient load scheduling,
solver interpolation behavior or numerical acceptance. No solver was launched.

### Reconciled Phase 2 backlog

Statuses below refer to the requested general capability, not availability inferred
from installed modules. A missing implementation/test is not an external blocker.

| Requirement | Current state | Reuse / next acceptance work |
|---|---|---|
| Thermal contacts/interface resistance | Partial: native/public total R/G authoring and resistance persistence verified | 200-element explicit-convergence artifact benchmark passes; general contact options and current-session freshness remain |
| Convection and dependencies | Native/public constant coefficient and three temperature-source selectors verified | Explicit Kelvin value, persistence, exported conversion and disjoint face sets pass; time fields, ambient value resolution and shell-side options remain |
| Radiation/emissivity/enclosures | Native/public simple environment radiation, constant emissivity override and deterministic enclosure authoring verified | Persistent/exported primary regions and active settings pass; view factors/numerical balances, Monte Carlo/GPU and secondary-slot authoring remain unverified |
| Temperature-dependent materials | Native/public reusable temperature-axis tables verified; material binding missing | Bind supported property fields and verify solver export/persistence |
| Transient loads/initial conditions/schedules | Partial time controls, constant distributed loads and native/public time-axis tables | `time_controls.py`, `distributed_heat.py`; schedule and initial-condition authoring/readback |
| Forced/natural convection and fluid models | Partial native controls/materials and coupled fixtures | `flow_controls.py`, `fluid_material.py`; selector/gravity/buoyancy scope and exports |
| Fan curves and provenance | Scoped public authoring/readback verified | `fan_field.py`, `fan_boundary.py`; preserve static convention and assignment limits |
| Fan-speed variants/operating points | Scoped scaling and extraction present | `fan_scaling.py`, `fan_summary.py`; retain validity range and per-run identity |
| Native temperature-controlled fans | Missing | Native controller discovery and bounded configuration/readback tests |
| Openings/screens/porous resistance | Partial opening scalar K | `head_loss.py`; do not call this general porous media; add supported model-specific paths |
| Global/local/near-wall mesh controls | Partial public global tetrahedra; internal boundary-layer path | `boundary_layers.py`, `quality.py`; reusable public controls and local associations |
| Mesh refinement comparisons | Partial retained numerical comparisons | Bounded reusable comparison records with exact model/mesh/job identity |
| Parameter studies | Partial isolated variants and scenario import | `variant_clone.py`, `scenario_apply.py`; explicit variables, bounds and resumable execution |
| Job status/recovery/cancellation | Partial public persistent workflow | Native running cancellation unresolved; pre-launch cancellation verified separately |
| Prepare/export/launch/observe/inspect separation | Present public scoped workflow | Preserve distinct API return, solver exit, convergence and engineering acceptance |
| Region temperatures/extrema | Partial result extraction | `results.py`; explicit region selections and scalar location semantics |
| Pressure drop/fan operating point | Partial pressure fields and fan summary | `flow_results.py`, `fan_summary.py`; convention/unit/selection acceptance |
| Mass/energy balance | Partial native-log audits and derived balances | `thermal_balance.py`, `flow_audit.py`; keep native versus derived provenance explicit |
| Data/visualization export | Partial native result/postview and CAD artifact delivery | `postprocessing.py`, `postviews.py`; reusable result exports and dependency packaging |
| Supported model/result freshness | Partial scoped material/boundary/file checks | Extend reliable geometry/mesh/settings/external dependency tracking; no whole-model claim |

Phase 3 requires reproducible deployment (including the private helper), stable
workflow docs/examples, scoped capability/release reports, clean commits and a
requirement-by-requirement evidence audit. Full .NET migration, acoustics and
Baldower-specific engineering are outside the updated goal. Licensing remains
unchanged in every phase.

## Local API reference

The user-installed Help Server now supplies the missing Open CAE reference.
All installed API collections are copied under the gitignored `.local-docs/siemens/`;
see its README and integrity manifest for navigation and provenance. Primary
reference: `.local-docs/siemens/api/PL20251027573834884/en-US/custom_api/opencae/`.
The actual solver index is `Solvers/Solvers.html`. The shipped coupled sample
uses descriptor **`Thermal-Flow Coupled Solution Parameters`**, distinct from the
solution property key `Coupled Solution Parameters`. Native creation, solution association, export and public MCP replay now pass
for this mapping. Explicit `External Conditions` tables also export inlet/opening
temperatures correctly. Coupled acceptance remains outstanding. Vendor contents
must not enter the public PR.

## Current infrastructure scope and capability matrix

The user's infrastructure-boundary direction supersedes the historical coupled
milestone ordering below. Expose native capabilities faithfully; do not compensate
solver results, rewrite generated files, change physical inputs to pass a test, or
require resolution of every solver behavior before completing unrelated APIs.
Detailed Baldower engineering and mesh/convergence studies belong outside this task.
Retain request-to-native-state guards. Export differences need representation and
selector context; an assumed numerical interpretation is not a universal API rule.

Categories: **1** implemented and verified through native NX/MCP; **2** numerically
benchmarked; **3** available with documented limitations; **4** blocked by an MCP
defect; **5** external behavior or unresolved Siemens limitation. Categories apply
to the stated scope, not blanket tool certification.

| Capability | Category and verified scope | Numerical acceptance / remaining work |
|---|---|---|
| Coupled descriptors and External Conditions | 1: native/XML creation, readback, persistence and public replay retained | Complete coupled numerical benchmark remains inconclusive |
| Material authoring | 1 for tested constant-property native assignment; 5 for unresolved effective-density precedence | Atmospheric adjustment not isolated; no proven Siemens or MCP material defect |
| Ambient settings | 3/5: selectors documented; explicit boundary temperatures verified; global export discrepancy retained | Equivalent UI-authored comparison not performed; keep export guard and precise scope |
| Head-loss manual coefficient | 1: selector-negative cases, compare-and-set, safe replay and committed readback verified through native/public MCP | Native XML links the opening to K=2 with active selectors and 718 faces in step 1; reopen and stale-reference checks pass; no new numerical claim |
| Field-backed values | 1 for numeric constants: active heat scale readback/export/reopen/public MCP verified; 3 for broader definitions | Registered fan tables now include native samples/interpolation and scale (native/public verified); arbitrary tables/vector scales remain unverified |
| Effective BC fingerprints | 3: direct solution/ordered-step membership implemented; native remove/add/reopen and public membership readback verified | Unhandled folders/overrides and uninspected values invalidate comparison; native step ordering/reopen/public readback verified; step-level load assignment remains unresolved |
| UF evaluator users | 1: private .NET adapter, native geometry/lifecycle tests and public MCP verified | Requires locally built helper and supported NX loading authorization; Python evaluator ownership remains unverified |
| Public coupled-steady schema | 1: prior public native replay retained; F5 offline schema expectation corrected | Full offline Simcenter suite passes; schema coverage is not numerical evidence |
| Persistent jobs and result identity | 3: accepted/launch/observer/terminal identity path tested | Native cancellation and complete live dependency freshness still open |
| Steady thermal stopping controls | 1: native/public authoring, replay, export and native persistence; optional relative balance selector tested | 2 for temperature-only stopping in the 200-element contact case; relative-balance stopping unbenchmarked |
| Numerical benchmarks | 2 only within separately retained individual benchmark reports | Do not extend those claims to coupled cooling, acoustics or engineering release |

### Manual head-loss export acceptance

`tests/simcenter/evidence/head-loss-export-audit.json` records the SHA-256 of the
retained 18.6 MB native export (kept outside Git), active selectors, coefficient,
opening/table association and step face count. Reproduce its read-only audit with
`python examples/simcenter/audit_head_loss_export.py <native-export.xml>`.
The original export is retained on the NX workspace under
`ui-benchmarks/F3-head-loss-export-20260909-r1/`; no solver file was rewritten.
`verify_head_loss_export.py` created/saved/exported the isolated fixture;
`verify_head_loss_reopen.py` and `evidence/head-loss-reopen.json` verify saved K=2,
selector/association persistence, stale-reference rejection and preservation of
unrelated document flags. Seven negative/positive offline export-audit tests and
the combined 590-test regression run pass. The broader regression run passed
1,408 tests; eight localhost-dependent tests were blocked by the filesystem/network
sandbox, and their six test modules subsequently passed all 39 tests with localhost
access. Native evidence is retained byte-for-byte using scoped Git attributes. This is native API/export verification,
not a new numerical acceptance result. The pre-existing unmeshed-body warning in
the native export report remains relevant to any future solve.

### Visible UI state

The control-window caption now identifies `BaseDisplay` by filename and marks
unsaved changes with `*`; UI status includes the full path and work document.
A different work document is explicitly named in the caption. Historical job
observations are labelled as such. `evidence/ui-document-refreshed.json` records
the native refresh and preservation of document modification flags. It uses BasePart-safe
access for FEM/SIM, never the CAD-only `Parts.Work` getter. Native evidence:
`ui-visible-document-caption.json`; 15 focused UI recovery/caption tests pass.
On 2026-09-09 the latest work/display SIM was correct and refresh succeeded, but an
old Information report obscured it and described an earlier coupled check. The
report was dismissed and the actual current view fitted. Property-only fan changes
do not alter visible geometry. During test batches, keep the intended analysis
copy displayed, identify property-only work, and verify the visible state after
batch completion. Native operations can block repainting until they return.

Temperature and pressure display now fit and refresh the viewport and close the
Information window without clearing its contents. Each response reports these
presentation actions; a failed fit or window operation produces a warning without
rolling back a successfully created result view. This does not refresh solver
results after model changes or establish result freshness. The contact result
was verified in native NX with unchanged document modification flags; the shared
pressure presentation path has offline coverage but was not rerun in this check.

### Supported fan-field definitions

Boundary property readback now reuses the existing registered fan-table inspector.
It includes validated native samples in SI, retained interpolation/provenance
metadata and scalar wrapper scale separately. A fresh isolated native fixture
verified identical raw samples at scales 1 and 2; scale was then restored to 1.
Public `nx_sim_objects(include_properties=true)` returned the same definition.
No solver ran. Arbitrary/unregistered tables and vector-field scales remain
explicitly unverified; no complete model-freshness claim follows from this subset.
Evidence: `fan-definition-readback.json`, `fan-definition-public.json`.
Reproduction: `verify_fan_definition_readback.py` and `verify_fan_definition_public.py`.
Twenty-two focused properties/definition/boundary tests include independent
invalidation for changed table values and changed wrapper scale. Native follow-up now verifies the complete boundary fingerprint for this isolated
fixture: scale 1 → 2 changes its hash; invalid fan metadata removes the hash and
sets comparison_verified=false; undo restores the exact original snapshot and all
loaded-document modified flags. This covers boundary values and selected solution
membership, not all geometry, mesh, material or result dependencies.
The readback retains `NX_SIM_MANIFEST_INVALID` in `inspection_error` while keeping
`inspection_status=read_failed`; consumers must not treat partial inspection as success.
Evidence: `fan-definition-freshness.json`, `fan-definition-freshness-errors.json`;
reproduction: `verify_fan_definition_freshness.py`. No solver ran.
Twenty-three focused offline tests pass after the error-detail regression.

### Boundary fingerprint persistence

Native save/reopen exposed a false freshness change: field runtime tags changed
while all boundary values and associations were preserved. Version 4 excludes only
`field_reference.tag` from semantic hashing. Inspection still returns the tag with
its loaded-document lifetime; live object resolution retains generation checks.
Owner/journal identity, field definition, scale and membership remain in the hash.
Older fingerprints require a fresh audit; they are not silently upgraded.

The repaired native test saves/closes/reopens only the isolated fan SIM, verifies
an identical boundary hash and native values, rejects both stale document and inlet
references, and preserves unrelated document flags. No solver runs. This does not
establish complete model or result freshness. Evidence:
`fan-definition-reopen-tag-mismatch.json` (original failure) and
`fan-definition-reopen-v4.json` (fixed); script `verify_fan_definition_reopen.py`.
Twenty-four focused boundary/property/field tests pass, including sensitivity to
changed journal identity while ignoring changed transient field tags.

### Job consumer snapshot versions and file references

Thermal snapshot adapter 3 includes the boundary comparison scope. Preparation,
launch and result auditing reject older adapters or differing boundary scopes as
`live_thermal_state_scope_mismatch`, even if a digest or saved result file matches.
This means a fresh audit is required; it is not evidence of a physical input change.
The live preparation/launch bindings were refreshed without restarting NX.

Native verification on the saved isolated `volume_solve_r1.sim` confirmed adapter 3,
boundary scope v4, a complete scoped hash, rejection of an older snapshot before
mutation, and preservation of unrelated document modified flags. No job launched.
The native check initially could not inspect the constraint's `Temperature File`.
The documented `BasePropertyTable.GetFileReferencePropertyValue` now reports its
empty string. Nonempty paths, including whitespace, remain explicitly
`unverified_external_file_contents`; path readback alone never certifies contents.

Evidence: `thermal-scope-version.json`; original unsupported-property evidence:
`thermal-scope-empty-file-limitation.json`. Reproduce with
`verify_thermal_scope_version.py`. Earlier attempts used a coupled fixture outside
this thermal-only capture scope and a historical fixture no longer loaded; the
final script opens the exact saved thermal fixture. This scoped check does not
extend material freshness to coupled flow or establish numerical acceptance.

### Cancellation before launch

`nx_sim_cancel(job_id, expected_revision, job_folder="simcenter-jobs")` cancels only
an accepted, unlaunched reservation. The compare-and-append record prevents a launch
from claiming the same revision. The cancelled job identity remains permanently
reserved; files and launch gates are not deleted. Repeating a completed cancellation
returns its recorded state. Inspect revisions with `nx_sim_job_status`.

Once launch intent exists, the tool returns `NX_SIM_CANCELLATION_UNAVAILABLE` with
`not_started`; it never signals or terminates a process. Installed NX Open and Open
CAE reference searches still did not establish a supported job-bound thermal/flow
stop operation. Monitor executables and stop-button resources are not proof of an
automation API. Running-solver cancellation remains an open native capability.

Verification: 34 focused job-store/cancellation/public-surface tests, including a
competing cancellation/launch record race and reconnect persistence. Public MCP
verified discovery, accepted cancellation, replay and rejection after a synthetic
launch-intent record. Evidence `cancel-contract-public.json`; scripts
`prepare_cancellation_contract.py`, `verify_cancellation_public.py`. These isolated
records are explicitly contract fixtures, not prepared or running solver jobs.
No native solver cancellation or numerical acceptance is claimed.

### Native step membership limitation and ordering

A bounded test on an isolated copy of the saved thermal volume fixture created a
second documented `Step - Thermal`. `SimSolutionStep.AddBc` returned without error,
but `GetBcs`/`GetUnfolderedBcs` reported no assigned load. This occurred both after
removing global solution membership and with global membership restored. The
fingerprint correctly did not change for those uncommitted assignments. Do not
claim step-level load moves work for this solution or classify a successful API
return as committed state. The copied API documents AddBc/RemoveBc and their
non-folder restriction; the Thermal step descriptor documents time controls but
did not establish why this assignment was ignored. Native preconditions/support
remain unresolved; this is not demonstrated to be an MCP lookup defect.

Independent `MoveStep` ordering did commit, changed the membership fingerprint,
survived save/close/reopen, and matched public `nx_sim_solutions` readback. The
copy retains its global load membership and remains displayed. Unrelated document
flags were preserved; no solve or mesh operation ran. Evidence:
`step-membership-noop-readback.json`, `step-membership-limit.json`,
`step-order-public.json`; initial failed assertion retained in
`step-membership-attempt.json`. Reproduction scripts:
`verify_step_membership_native.py` (retained unsuccessful load-move attempt),
`inspect_step_membership_limit.py` (bounded continuation and order acceptance),
`verify_step_order_public.py`. No step-level mutation tool is advertised as verified.

### Paged direct step membership

`nx_sim_steps(..., include_membership=true)` now returns direct BC and folder
membership for each returned step, using the same owner checks as solution
fingerprints. The default omits membership. Only returned steps are inspected;
this does not fetch every step for a one-row page. Unsupported folders and failed
ownership/readback checks prevent a verified direct-membership response. The scope
explicitly excludes global solution conditions and inferred inheritance.

Public native verification compared two one-row pages with the persisted native
step-order snapshot and verified default omission. Evidence:
`step-membership-paging-public.json`; reproduce with `verify_step_membership_public.py`
using the retained step fixture context (reacquire references after closing it).
Thirty-nine focused boundary/surface tests pass. This is inspection support, not
verification of the unresolved native step-level load authoring behavior above.

### Combined regression and deployed signature audit

The combined Simcenter offline suite passes **471 tests** after the field,
freshness, cancellation and membership changes. `git diff --check` passes.
The live bridge audit verified public argument compatibility for all **59**
Simcenter tools: 58 exact signatures and one optional private benchmark parameter
(`wall_thickness_mm`) not exposed by the public schema. It is not a public
capability claim. The audit checks required arguments, defaults and parameter
kinds; it does not certify every handler's native behavior.

All deployed Simcenter Python source hashes now match the tested checkout. Three
initial hash differences were formatting-only, confirmed by equivalent parsed
Python ASTs before synchronization. No model edits, solver runs or restarts were
needed. Evidence: `deployed-signatures.json`; reusable native audit script:
`verify_deployed_signatures.py`. Run this after batched schema/handler deployments
to catch stale live bindings separately from offline regression coverage.

### Effective solution and step membership

F2 now fingerprints the selected solution identity, direct BC membership and ordered
steps with their own memberships, separately from the document inventory. Removing
a load from the solution without deleting its SIM object changes the fingerprint.
Foldered membership, conflict overrides, missing owner/readback and effective BCs
without inspected values are explicitly unverified, never silently assumed active.
The property inventory now includes loads, constraints and simulation objects, plus
bounded linked named tables. Unsupported values still prevent a complete boundary hash.
This is a supported-scope limitation, not evidence of whole-model freshness.

Native test on a fresh isolated copy: removing the selected heat load retained the
same document load inventory and changed the membership hash. Adding it back restored
the original hash. Native undo verified restoration. Save/close/reopen preserved the
complete membership snapshot; the closed reference returned `NX_OBJECT_STALE` and
unrelated loaded-part modified flags were unchanged. No solve ran. Evidence:
`effective-membership-native.json` and `membership-reopen-native.json` under
`tests/simcenter/evidence/`. Reproducers: `verify_effective_membership.py` and
`verify_membership_reopen.py`; inspect retained receipts before any replay.

Offline tests cover solution identity changes, condition moves between steps,
step ordering, removal without deletion, unsupported folders/overrides and effective
objects missing from the value inventory. The full Simcenter suite passed 440 tests
before the final two focused additions (all ten boundary-state tests pass afterward).
Public MCP inspection now passes; negative replay and native multi-step moves remain outstanding;
this closes the demonstrated omission for the supported internal path, not every
F2 verification gap. No result is reclassified as numerically accepted.

Public `nx_sim_solutions(document, limit=1, include_membership=true)` returns the
same native membership snapshot without activating a solution. Default responses
omit it. A fresh public MCP client verified discovery, both response forms and
unchanged inventory/work/display/modified flags across all 127 loaded documents.
Evidence: `tests/simcenter/evidence/membership-public-verification.json`;
reproducer: `examples/simcenter/verify_membership_public.py` on the NX host with the
retained `membership-public-context.json` (reacquire its live reference after closing
the fixture). The receipt contains deployed source hashes. The focused offline
surface/boundary suite passes 34 tests; lint passes for changed implementation/tests.
This verifies API inspection, not numerical acceptance or complete result freshness.

Deployment exposed a retained instance-bound handler with the old signature;
refreshing only its class method was insufficient. The public signature failure
was resolved by rebinding the registered handler to the deployed implementation.
Future hot reloads must verify the registered callable as well as disk hashes and
sidecar discovery. Failed launcher and test-comparison attempts remain in the local
receipts; no solve ran. Native multi-step membership moves and unsupported folder/
override semantics remain explicit follow-up work.

### Linked boundary tables

The generic reader now recognizes `CAE.PropertyTable.PropertyType.NamedPropertyTable`
through `GetPropertyType`; native External Conditions reports base type 0 but CAE
type -10. Readback includes the linked table journal/owner identity, descriptor,
properties and evaluated nested expressions. Unassigned links remain explicit nulls.
Expansion is bounded to two named-table levels and 512 properties per property tree;
cycles, truncation and unsupported child values are marked unverified and propagate
to the parent. Public property expansion remains opt-in; prefer small pages.

Boundary state v3 includes the SIM's simulation objects as well as loads/constraints.
The previous effective-inlet/opening omission is resolved for inventory and observed
values. A native isolated test changed the shared External Conditions temperature
from 20 to 21 °C, observed it through both inlet/opening links, then verified exact
undo restoration and unchanged solution/step membership. Public `nx_sim_objects`
subsequently read both restored 20 °C conditions and preserved loaded-document state.
No solve or numerical acceptance was involved.

Evidence: `tests/simcenter/evidence/linked-boundary-state-verification.json` and
`boundary-table-types.json`; reproducers: `verify_linked_boundary_state.py` and
`verify_linked_boundary_public.py` in `examples/simcenter/`. The native script rejects
an existing output folder; inspect the receipt before replay. The full offline
Simcenter suite passes 454 tests, including linked-value changes, replacement identity,
cycles/budgets, unsupported children and simulation-object state changes.

The tested coupled snapshot still returns `comparison_verified=false` and no hash:
velocity/direction/axis values, tracer/mixture arrays and description properties are
not fully inspected. Nested tables inherit that limitation. This is not whole-model
freshness, and this change does not reclassify any solver result as accepted.

Additional property inspection now retains text lines, bounded scalar/integer arrays,
empty linked-table arrays, null directions/axes and vector-expression values. Nonempty
linked-table arrays and field-backed vector scales remain explicitly unverified.
Native arrays containing -777777 retain that sentinel exactly; readback does not
interpret it as a physical input.

A first native vector read changed the SIM modified flag. A fresh per-property test
identified `Velocity Vector`: the getter materializes unset component expressions.
Inspection now wraps that getter in a local invisible undo mark and verifies restored
loaded-document flags. Recovery failure propagates as
`NX_SIM_INSPECTION_ROLLBACK_FAILED` with partial state, rather than successful readback.
Native reinspection preserved flags and produced a complete hash within the observed
boundary/property/membership scope only. It is not full-model freshness or numerical
acceptance. Evidence: `property-getter-side-effect.json` and
`expanded-property-rollback-verified.json`; focused offline coverage passes 24 tests.
Non-null direction/axis geometry and nonempty array assignments still need targeted
native validation beyond the retained default-value fixture.

### Field scale and comparison integrity

F1 is partially addressed. Field-backed property readback now includes the native
wrapper scale, journal/owner/tag identity with an explicit loaded-document lifetime,
and the defining string/units. A numeric constant reports its value times the native
scale; this arithmetic is not a solver result. Nonconstant expressions and field
tables remain explicitly unverified rather than guessed or silently omitted.
Boundary fingerprints are unavailable when any property is unsupported or unreadable;
`comparison_verified=false` and `sha256=null` cannot satisfy the thermal comparison.
This may require re-preparation of previous jobs whose incomplete state was hashed.
It does not establish whole-model freshness or effective solution membership.

Native evidence on an isolated saved SIM copy: the constant field 101325 Pa at
scale 1 was read as 101325 Pa, then scale 2 as 202650 Pa. Native undo restored the
original scale, field identity and readback exactly. The selected pressure property
is inactive in this fixture; this verifies wrapper readback, not applied pressure
or solver behavior. No solve ran. Source: `verify_field_scale_readback.py`, evidence:
`tests/simcenter/evidence/field-scale-readback-native.json`.

Offline regressions cover scale-only changes, replacement field identity, nonconstant
expressions and opaque table edits that must never return a valid comparison hash.
The earlier complete offline Simcenter suite passed 437 tests. Broader field
definitions remain open; F1 is not fully closed. Active constant-field lifecycle
and public inspection now have native evidence below; F2 progress is recorded above.

Active-field lifecycle follow-up: an isolated copy of the generic fixture used a
0.1 W constant field with wrapper scale 2 on the existing active total heat load.
Native readback, save/close/reopen and public `nx_sim_loads` property expansion
preserved the definition, scale, effective 0.2 W and membership. The closed SIM
reference was rejected as stale; unrelated modified flags were unchanged. Field tags
are compared only within their documented loaded lifetime, not across reopen.
The native unit name is `HeatFlow_Metric2`, symbol `W`; field-expression readback now
returns both, consistently with expression-backed properties.

The unchanged native XML contains total heat 200000 in the tested millimeter/second
solver convention (force and length conversion factors both 1000), equivalent to
0.2 W within 1e-9 W. Its nonempty step-1 selection contains 764 elements, with
per-element/per-node and region-override selectors inactive. This verifies export,
not heat rejection or a converged numerical result. No solve ran, and the global
ambient configuration was not changed. Native authoring took about 0.02 s,
save-as 0.43 s, export 1.96 s and save/close/reopen verification 2.67 s; these timings
exclude deployment and client overhead.

Evidence: `tests/simcenter/evidence/active-field-lifecycle-verification.json` includes
native stages, public verification summary, source/XML hashes and the retained
precondition failure (a unit-name assumption). Reproducers:
`verify_active_field_lifecycle.py`, `verify_active_field_public.py` and
`audit_active_field_export.py` in `examples/simcenter/`. The native script rejects
existing exports; inspect receipts before replay. Public readback requires the
current fixture reference. Run the local XML check with:

```sh
python examples/simcenter/audit_active_field_export.py /path/to/active-field-export.xml
```

Focused property, membership and export-audit tests pass (20 tests). Export-negative
coverage rejects wrong heat values, units, per-element mode and wrong step selection;
this offline coverage does not claim those negative cases were authored in native NX.
Arbitrary expressions/tables, temperature-dependent field definitions and complete
result freshness remain unverified.

### Audit corrections and native findings

F3: `Head Loss` descriptor and `Type=0`, `Proportional to=0` are now checked before
coefficient comparison, including no-ops. Creation explicitly selects those modes.
Native testing on an isolated copy rejected both inactive modes for unchanged and
changed requests, preserved coefficients, and updated the supported mode. All test
edits were rolled back. Evidence: `head-loss-mode-audit-native.json`; script:
`verify_head_loss_modes.py`. Public-MCP negative cases are now verified as described below; export remains separate work.


Public F3 audit uses three isolated copies of the retained synthetic duct SIM.
`Type=1, Proportional to=0` and `Type=0, Proportional to=1` each reject both an
unchanged and changed manual coefficient with `NX_SIM_HEAD_LOSS_MODE`. The supported
`0/0` mode accepts 0 → 0.25, returns a cached response for the same operation ID,
rejects an outdated expected value, and restores 0. No solve or mesh ran.
Retries preserve operation identity: successful replay adds `replayed=true`; failed
replay returns `NX_OPERATION_FAILED` with the retained original error, state and
`not_started` outcome. The test now checks those envelopes explicitly instead of
assuming byte-identical responses or an unwrapped original error.
Reproducers in `examples/simcenter/`: `prepare_head_loss_public_audit.py`,
`verify_head_loss_selectors_public.py`, and `audit_head_loss_public_readback.py`.
The preparation and final audit use the serialized native harness; the middle script
uses a fresh public stdio MCP client. These fixtures share read-only FEM dependencies
and change only copied SIM documents. Seven focused offline head-loss tests pass.
Evidence in `tests/simcenter/evidence/`: `head-loss-selectors-public.json` and
`head-loss-public-readback.json`. Earlier test assertions and the work-part-only
activation failure are retained separately. Restoring an unrelated CAD document
requires the established display-then-work sequence. This is authoring/lifecycle
verification, not acceptance of a pressure-loss convention or solver result.

F4: a direct `UF.Eval.Free` fix passed doubles but failed native verification:
NX 2606 Python exposes no such method. The C API requires `UF_EVAL_free`;
the returned Python `PointerWrapper` exposes no release method, but this does not
establish Python ownership or prove a leak. The wrapper guide documents automatic
management for ordinary `UF_free` returns, not specifically evaluator pointers. The
rejected fix and API discovery are preserved in `uf-cleanup-native-failure.json`,
`uf-evaluator-release-api.json`, `uf-evaluator-doc.json`, and `uf-pointer-wrapper.json`.
The temporary capability preflight rejected both evaluator users before allocation
on this binding and preserved loaded-part modified flags. It has now been replaced
by the verified private adapter described below.
One discovery handle is retained on the dedicated executor as `_audit_eval_handles`
without attempting manual release; the initial failed check also allocated a handle
before discovering the missing method. Evaluator-specific Python finalization remains
unverified. Do not claim either a measured leak or automatic evaluator cleanup.
No unsafe pointer extraction, guessed free function, or process restart was used.
A bounded copied-document check found no evaluator-specific Python ownership statement.
The documented .NET `UFEval.Initialize2`/`Free(IntPtr)` route and Python `Session.Execute`
are used by the verified private adapter. It owns only newly allocated .NET
evaluators and does not resolve existing opaque Python-wrapper ownership. No pointer
extraction or licensing configuration changes are authorized or used. The supported
adapter remains infrastructure work, not a solver issue.

The private C# evaluator helper now compiles with the installed .NET Framework
compiler and NXOpen/NXOpen.UF/NXOpen.Utilities assemblies. Native `Session.Execute`
authentication passed with the existing .NET Author licence; no signing/licensing
configuration was changed. The initial qualified class name failed lookup; the
simple class name loaded successfully. This is tested host-specific loading evidence,
not a guarantee for unsigned helpers on other installations.

Native helper sampling of an existing benchmark edge matched its endpoints exactly.
Its allocation/release counters advanced 0/0 → 1/1 after success and 1/1 → 2/2 after
a deliberate exception following allocation, with zero outstanding helper-owned
handles and unchanged loaded-document flags. No Python evaluator pointer crossed
into the helper. This does not establish ownership of existing Python wrappers.
Evidence: `evaluator-ownership-review.json`, `evaluator-helper-geometry.json`,
`evaluator-helper-load-simple-class.json` and loader diagnostics in
`tests/simcenter/evidence/`.

Both CAD operations are now restored on the dedicated NX/Simcenter bridge. Native
DXF acceptance covers exact LINE/ARC/CIRCLE, reversed output normals, mm/inch source
units, and an actual ellipse rejected without writing a file. Curved cylindrical
sheet boundaries pass 42 bidirectional G0/G1/G2 samples: gap 0 mm, maximum normal
angle 1.2074183e-6 degrees, curvature difference 9.8131e-18 1/mm. Tolerances are
0.001 mm, 0.1 degrees and 0.01 1/mm; these are sampled checks, not a global certificate.
Helper allocations/releases increased 24/24 → 27/27 for two boundary inspections
and a deliberate post-allocation exception, with zero outstanding helper handles.
Unrelated loaded-part modified flags were preserved. A fresh public MCP client
verified both continuity and planar-face DXF export after live handler refresh.
No thermal simulation, process restart or licensing change was needed.

Reproduce on isolated files with `verify_planar_evaluator_adapter.py`,
`verify_continuity_evaluator_adapter.py` (serialized native `run(executor)` harness),
and `verify_evaluator_public.py` (fresh stdio client with the retained fixture context)
in `examples/simcenter/`. Fixture directories must be unique; existing runs are
rejected rather than overwritten. Evidence: `planar-evaluator-adapter.json`,
`continuity-evaluator-adapter.json`, `evaluator-public-verification.json`.
The earlier fixture integer/double mismatch and duplicate loaded basename failures
are retained separately; neither is counted as a passing geometry test.
Offline coverage: 66 focused tests in `test_manufacturing_report.py`,
`test_freeform_manufacturing.py`, and `test_evaluator_bridge.py`; doubles do not
establish native ownership or loading behavior.

Build the helper using `examples/simcenter/build_evaluator_helper.ps1` against the
installed NX assemblies, subject to the host's existing execution policy. The tested
host required executing the reviewed compiler commands through its existing command
runner; no execution-policy setting was changed. Source is packaged, but the DLL and
build manifest are local deployment artifacts. The adapter validates source and DLL
SHA-256 hashes, uses a fixed class/method, batches samples, and returns numeric data.
Missing/mismatched builds fail before allocation. Other NX builds and hosts lacking
a supported signed-library or existing Author-license loading route remain unverified.
A release failure is an error, with primary and cleanup NX codes preserved separately;
no opaque Python evaluator is extracted or freed.

F5: the expected action enum includes `coupled_steady`, retaining mutation identity
and annotations. Prior native public replay remains in `coupled-steady-public.json`.
The complete offline Simcenter suite and freeform tests passed together (471 tests)
before the additional head-loss/preflight regressions; subsequent counts are recorded
with their actual test scope. No blanket native acceptance is implied.

### Atmospheric-density lead: scope correction

The retained layered log explicitly prints reference density 1.207 kg/m³, ratio
1.0724 and adjusted density 1.2944 kg/m³. Their product is 1.2943868 kg/m³,
consistent with the disputed value within printed rounding. The authoring script
selects altitude-based pressure, global temperature 0 °C, and separate boundary
temperatures 20 °C. All retained material experiments preserve that configuration;
they did not isolate atmospheric adjustment. The explicit-pressure attempt stopped
at export and supplies no completed altitude-disabled comparison.

This strongly explains the number, but not its precedence over assigned constant
liquid density. Neither a Siemens defect nor an MCP material-authoring defect is
established. Boundary temperatures do not eliminate global reference effects.
The documented HYDENV reference pressure/temperature semantics support keeping
this distinction; they do not prove the coupled translator's precedence rule.
Evidence: `density-atmospheric-context.json` and the retained original log/input
files. No UI-authored equivalent comparison has been performed. Manual UI assistance
was previously declined; no fragile screen-coordinate edit or extra solve was used.
Keep a bounded equivalent-UI export check as a possible follow-up, not a gate on
unrelated infrastructure. Historical substitution language below describes file
observations, not a proven causal defect.

## Historical coupled cooling investigation (2026-09-08)

This table is the working entry point. Historical sections below describe narrower
experiments; they do not establish coupled acceptance. Defer convenience features,
advanced fans/acoustics and Baldower geometry until this milestone passes.

| Capability | Implemented status | Native/public MCP verification | Numerical acceptance | Remaining blocker | Next concrete action |
|---|---|---|---|---|---|
| Coupled solution and controls | Documented coupled factory and explicit external conditions implemented | Native/XML match; 20 °C boundary route survives isolated reopen | Full coupled acceptance open | Global 20→0 °C export mismatch persists | Retain guard; audit explicit 0 °C reference and 20 °C boundaries |
| Solid, air and interfaces | Finned solid, air and 0.1 W assignments implemented | XML density 1.2 kg/m³ becomes 1.294376 in generated solver properties and results | Physics acceptance blocked despite balanced heat | Translation/reference-density mapping; buoyancy switch and stock-template hypotheses rejected | Find documented reference-property control before another refinement solve |
| Mesh and solve | Uniform and layered fixtures; durable bounded jobs | Extended layered job terminal; public MCP input identity/gate release verified | Converged at 883 iterations under unchanged tight criteria | No accepted spatial convergence comparison | Resolve density before further mesh expense; no solver currently running |
| Results and physical checks | Temperature selection, density extrema and boundary quadrature | Native layered maximum 23.911255 °C; static pressure drop 1.116731 Pa | Mass imbalance 1.382e−11%, energy 0.008777%; heat to air 0.09999 W | Density mismatch and spatial sensitivity prevent acceptance | Audit regional properties and conservative heat/mass fluxes |
| Audit applicability and lifecycle | Expanded fixture guard and pressure export guard implemented | Expanded native audit and save/reopen/result equality pass; pressure guard natively verified | No physical acceptance inferred | General F1/F2 hashes remain incomplete; F3 not used here | Preserve explicit backlog; verify active global property export mapping |
| Cancellation | Pre-launch cancellation implemented | Public MCP job-store contract verified | No solver cancellation test | Running native solver cancellation remains unverified | No guessed commands or unsafe termination |

Batch creation, readback, persistence, replay and relevant failure checks in one
reusable fixture. Keep NX mutations serialized. Use local source/schema/test work
while an existing solver runs; never duplicate a job after an observation timeout.
For each uncertain mapping, record its hypothesis, installed API/source, bounded
experiment, outcome and next route. Measure discovery, implementation, deployment,
native setup/mesh, solve and verification separately using timestamps. Turn duration
is not a bottleneck measurement. Verify deployed handlers against discovery after
related changes are deployed together.

UI status prerequisite closed for now: observer snapshots retain job state and UTC
observation time without filesystem work on the UI thread. Observation timeout is
reported as unknown solver state; solver exit does not imply validated results.
Local targeted checks: 17 passed. Live update read back the existing
`monitor-probe-r2` terminal record without restart or model changes; see
`tests/simcenter/evidence/native-ui-job-status.json`. Automatic result display and
further panel convenience work are deferred.

### Siemens API audit reconciliation, 2026-09-08

User-supplied review: Baldower manufacturing reviews directory,
`2026-09-08-siemens-api/REPORT.md`. Current-source hashes were compared with
`reviewed-source-hashes.json`; see `tests/simcenter/evidence/api-audit-reconciliation.json`.
F1–F5 remain present in the reviewed files. The coupled factory descriptor fix
and explicit External Conditions route are already implemented and have separate
native/public evidence above; do not reopen their resolved descriptor hypotheses.
`Ambient Pressure=1` means altitude-derived standard conditions, so the stored
absolute-pressure scalar is inactive. This does not resolve the temperature
export discrepancy; retain the guard.

Before benchmark acceptance, audit actual field representations/scales, selected
solution and step membership, and any head-loss selectors. Script:
`examples/simcenter/audit_coupled_effective_inputs.py`. Its output must be examined;
existence of this script is not verification. Save/reopen/export of the explicit
boundary route subsequently passed; full physical acceptance remains outstanding.

Native applicability check on `coupled-external-diagnostic-r1`:

- F1: the applied 0.1 W heat load, global 0 °C reference and external 20 °C
  temperature are expression-backed wrappers with no referenced field. The
  field-scale omission does not affect these three inputs. Two global fields
  have scale 1: inactive absolute pressure (mode 1) and radiative environment.
  The solver reports no radiative heat loads; full field-definition inspection
  remains outstanding and this is not a general freshness sign-off.
- F2: documented `GetBcs` readback finds exactly the heat load, inlet and opening
  in the selected solution. Its single step has no additional BCs; both lists
  contain no folders and solution conflict-override count is zero. Thus the
  intended conditions are members for this snapshot. The general hash omission
  remains a defect; save/reopen membership comparison subsequently passed on an isolated copy.
- F3: no Head Loss table is present in this velocity-inlet/opening fixture.
  Inactive manual-K updates therefore do not affect this diagnostic. This does
  not close F3 for the earlier fan/restriction workflows.

Evidence: `tests/simcenter/evidence/coupled-effective-input-audit.json`.
These are native observations, not offline-double results. No additional solve
was launched and no benchmark acceptance was declared from this audit.

Next general Simcenter hardening goal backlog (not closed by current diagnostics):

- F1: include field scale, identity, supported definitions and evaluated values in
  readback/state comparison; unsupported field data must invalidate comparison.
  Test scale-only changes, field replacement and changed tables, plus native persistence/export.
- F2: fingerprint selected solution and ordered steps, effective BC membership,
  and supported folder/override semantics; reject uninspectable effective states.
  Test membership changes without deletion, step moves and shared-object solutions natively.
- F3: reject inactive manual head-loss coefficients by checking descriptor,
  `Type=0` and `Proportional to=0`, including no-op paths. Verify exported selectors
  and known-flow pressure loss on an isolated manual-K case.
- F4: restored with a private .NET-owned evaluator lifecycle; native and public MCP
  evidence above closes this implementation gap. Evaluator-specific Python ownership
  and loading on other installations remain unverified.
- F5: update the stale public `coupled_steady` action schema expectation while
  retaining dispatch, operation-identity and mutation-annotation coverage.
- Close remaining native coverage for freshness, external field dependencies,
  contacts/interfaces, fan controllers and input/result identity. Keep numerical
  convergence, solver exit and physical acceptance distinct. No blanket readiness claim.

### Read-only fluid-library comparison

Documented `PhysicalMaterialCollection.GetMaterialsFromLibrary`,
`GetMaterialSpecifiedPropertyNeutralNames`, and
`GetMaterialPropertyValueAndDisplayName` ran natively against the default library.
They returned 86 material names without loading materials into the FEM; loaded-part
inventory and modified flags were unchanged. Stock Air, Water and Helium declare
`SCThermalFlowAppliedViews = ThermalFlowFluid`; Air/Helium subcategory is Gas and
Water is Liquid. The custom material has empty category/subcategory, explicit
1.2 kg/m³ expression-backed density, and an applied-view property of a type that
our current inspector does not support. This is **not** proof that its view is
absent or that the metadata difference causes the density substitution.

The editable stock-template experiment has now run on a fresh 2 mm fixture.
`CopyMaterialFromLibrary("", "Water")` failed with NX 3940027 before solving;
unlike library query methods, copying requires the installed XML library filename.
The subsequent fresh fixture used that explicit path and
`CreatePhysicalMaterialEditBuilder`, replacing density, viscosity, conductivity,
heat capacity, expansion and molar mass with explicit benchmark values. Native
material readback passed. Job `coupled-finned-stock-copy-r1` reached a terminal
state, and public MCP verified its input identity and released the solver gate.

The initialization hypothesis is **rejected**: the generated solver property file
again uses 1.29437616181 kg/m³ and native density results are
1.29437613487 kg/m³, instead of 1.2 kg/m³ (7.86468% error). The other three required
fluid properties match within 1e−6 relative tolerance. Explicit zero thermal
expansion also becomes 0.003/K in the downstream file; gravity is absent and
`BUOYANCY_MODEL=0` here, so this is an inactive stored-property mismatch for this
diagnostic, not a validated general expansion assignment. Do not promote the
stock-copy factory or repeat this experiment unchanged. No production/shared FEM
was edited. No physical acceptance follows from this solver exit.

Reproduction scripts: `assign_stock_fluid.py`,
`build_finned_coupled_fixture.py` with its explicit stock-copy factory,
`run_finned_tight_controls.py` (`variant="stock_copy"`), and
`inspect_finned_density.py`. These create isolated diagnostic artifacts; do not
replay an existing mutation/job. Compact native evidence:
`tests/simcenter/evidence/finned-stock-copy-verification.json`.
The retained solver ZIP is outside Git in the task's `outputs/simcenter/` folder,
SHA-256 `b0d8c560f7252fbdae0656479d88d434bd2348b53c5d6036417a41c597c62c7a`.
The existing downstream audit reports the expected mismatch; this is native input
and result evidence, separate from the four offline parser regressions.

The installed material definitions and MatML property mappings were also copied
under the ignored `.local-docs/siemens/material-definitions/`. They document
material schema and name mapping, but the bounded inspection did not establish a
supported control for this downstream density substitution. The next investigation
needs the solver's reference-property semantics, not another material-name or
setter variation.

Reproduction: `inspect_fluid_library_metadata.py` and
`inspect_fluid_applied_views.py`. Compact evidence: `fluid-library-metadata-summary.json`
and `fluid-applied-views.json` under `tests/simcenter/evidence/`. Full vendor tabular
property strings remain outside Git. No solver was launched during this comparison.

### Distinct-property translation diagnostic

The next bounded experiment tested whether the earlier matching properties were
merely defaults. A fresh 2 mm fixture uses deliberately synthetic fluid values:
2 kg/m³, 1200 J/(kg K), 3e−5 Pa s and 0.05 W/(m K), with provenance explicitly
stating that this is not physical air. Creation and native property readback took
6.532 s; the mesh has 2130 elements and 745 nodes. The existing temperature,
pressure and effective-boundary guards remain enabled. No baseline FEM was edited.

Job `coupled-finned-material-contrast-r1` is terminal with public MCP input-identity
verification and gate release. XML contains the requested density 2 kg/m³, but
`flow.prp` contains 1.29437616181 kg/m³ (35.2812% discrepancy). Specific heat 1200,
viscosity 2.99999989295e−5 and conductivity 0.05 match their requested SI values
within 1e−6 relative tolerance. This rules out the whole material assignment being
ignored. It narrows the unresolved mapping to density among these four properties;
it does not prove the cause, numerical acceptance or a general material fix.

Reproduce with the existing build/author/run scripts using the bounded
`material_contrast` variant, inspecting durable receipts before any replay.
`audit_translated_fluid.inspect_material` accepts an explicit complete four-property
SI manifest for this comparison and rejects incomplete/nonfinite expectations.
Seven offline parser tests pass, including preservation of observed values when
expectations change. Native evidence is separate:
`tests/simcenter/evidence/finned-material-contrast-verification.json` includes the
exported material, package/XML hashes and public terminal state. Large native
artifacts remain in the task's `outputs/simcenter/` folder, outside Git.

Next: establish the documented reference-density/translation semantics before any
further refinement solve. Do not repeat either stock initialization or wholesale
material-assignment hypotheses without new evidence. The current milestone is
still unaccepted; no diagnostic changed Baldower geometry or licensing.

### Diagnostic budget correction

Inspection of the retained contrast `flow.prm` revealed `MAX_TIMESTEPS=500`, not
the intended 100. This was a fixture-script omission: `material_contrast` did not
enter the branch assigning iteration limits and density/mass-flux output flags.
The run finished at 14 iterations; previous descriptions of a 100-iteration cap
for that historical run were incorrect. Its material-translation observations
remain evidence of the recorded run, not an accepted physical solution.

`iteration_limit_for` now gives both small material diagnostics an explicit 100
budget, preserves the extended 1200 budget, and rejects an unknown diagnostic
before native mutation. Four offline regressions cover these preflight rules.
The corrected script is deployed to the shared diagnostic directory. An isolated
SIM copy verifies both native limits at 100 and both output flags enabled, then
verifies those values in XML. It preserves the ambient/pressure export guards.
No replacement solve ran; this is native authoring/export evidence only.
Evidence: `tests/simcenter/evidence/material-contrast-control-export.json`;
reproducer: `examples/simcenter/verify_material_contrast_controls.py`.

### Solver release-note check

The public critical-fix lists for [2606.2](https://help.mayahtt.com/tmg/tmgfixes/topics/critical_fixes/2026_06_critical_fixes.html),
[2606.3](https://help.mayahtt.com/tmg/tmgfixes/topics/critical_fixes/2026_07_critical_fixes.html)
and [2606.4](https://help.mayahtt.com/tmg/tmgfixes/topics/critical_fixes/2026_08_critical_fixes.html)
were reviewed against the retained TMG 2606.1 case. No listed fix identifies either
the density substitution or ambient scalar export discrepancy. These lists cover
critical changes, not every fix: absence is not proof that an update cannot help.
No upgrade is claimed to resolve this and no software was installed.

A read-only search including extensionless files found the installed solver README;
it describes product telemetry and contains no solver change log. No telemetry or
licensing settings were changed. The user has been asked for the full release notes
or vendor guidance through their existing support access; no outreach was sent.
Source hashes and scope: `tests/simcenter/evidence/solver-critical-fix-review.json`.
Vendor pages remain in the ignored `.local-docs/siemens/solver-release-notes/` folder.

The reviewable reproducer is the generic material-contrast case: 2130 elements,
constant liquid density 2 kg/m³; native material, XML and INPF agree, while
`flow.prp` is 1.29437616181 kg/m³. Heat capacity, viscosity and conductivity use
distinct synthetic values and survive translation. The separate stock-copy case
also has native regional density readback at 1.29437613487 kg/m³. Preserve the
original 500-limit/14-iteration contrast history and the subsequent export-only
100-limit correction. Neither case is accepted physical or Baldower simulation.
The relevant existing evidence files are linked in the adjacent sections; complete
native packages remain outside Git. Investigation should use these exact inputs
before proposing another setter, new mesh, licence change or solver patch.

### TMG input localization and alternative-route check

Read-only inspection of the same contrast package finds `MAT 2 PHASE LIQUID` and
`MAT 2 RHO 2.000000E-09` in `INPF`: the requested 2 kg/m³ in verified benchmark
units. The substitution occurs after the XML-to-TMG material-card stage and before
`flow.prp`. This does not resolve the temperature bug. The downstream audit now
reads this separate stage and rejects unknown units, duplicates and field/table
density. Native spacing initially exposed a parser failure; the correction and a
retained native card regression now pass. Evidence:
`tests/simcenter/evidence/finned-tmg-density-localization.json` and
`finned-material-contrast-cards.txt`.

The installed `physicalmaterialdensitydefinition.xml` confirms `MassDensity` is
active for `DensityControl=0`. SHA-256:
`39cab2382146593c47f2852fa432dd38f6f8f3e036d8c013e039c761b0cbe9cb`.
It and referenced type/category schemas remain gitignored. No guessed density
property substitution is justified. The solver vendor documents constant liquid
density in [Equations of state](https://help.mayahtt.com/tmg/topics/flow_ref/equations_of_state.html)
and the intermediate card in [MAT properties](https://help.mayahtt.com/tmg/topics/tmg_ref/card_9_mat.html).
Online help identifies 2606.4; retained INPF identifies TMG 2606.1. These references
establish semantics, not that a patch fixes this case. No patch/licence change.

The installed sample documents `NX THERMAL / FLOW` / `Coupled Thermal-Flow` /
`Advanced Thermal-Flow`, but a fresh 0.031 s native catalog query exposes only
Multiphysics thermal/flow languages in this session. Loaded-part modified flags
were unchanged. The legacy route is not a verified available fallback; no creation,
licence checkout or installation followed. Evidence:
`tests/simcenter/evidence/alternate-solver-catalog-summary.json`.
Next investigate the TMG-to-flow material/reference-density mapping using the
preserved package; do not repeat mesh solves or previously rejected setters.

### Density localization and bounded negative experiment

The retained native solver ZIP for `coupled-finned-layer-extended-r1` has SHA-256
`f36e43cedbaf352cddb475fb98cf5c24d45fa87368faebaffc0ade248d7465bc`.
Its generated `flow.prp` already contains density 1.29437616181 kg/m³, a 7.86468%
difference from the intended 1.2 kg/m³. Specific heat is 1005 J/(kg K), viscosity
1.80999997212e−5 Pa s, and conductivity 0.0257000007629 W/(m K); those three
properties match within 1e−6 relative tolerance. Thus density changes between the
NX XML and the downstream solver property file, before result extraction. The
other matching properties do not make the density override acceptable.

Bounded hypothesis: the generated forced-convection path might be selected by the
documented solution `Buoyancy` flag. Source: installed Open CAE coupled solution
page, plus the generated `ESC_FORCED_CONVECTION` control. Experiment:
`probe_finned_density_path.py` copies the retained 2 mm fixture, enables Buoyancy
with no gravity load, requests density, preserves the existing temperature/pressure
guards and caps both solvers at 100 iterations. Native and XML readback of the flag
passed. Job `coupled-finned-density-path-r1` completed; public MCP verified terminal
input identity and released the gate. Native density remained 1.29437613487 kg/m³.
The switch-only hypothesis is rejected. Do not adopt this as a workaround, repeat
it unchanged, or treat its convergence as physical acceptance.

`audit_translated_fluid.py` makes the downstream check reproducible. It accepts only
one constant-liquid material and verified millimeter/millinewton/second units;
unknown units, missing/duplicate or field-dependent data are rejected. Run:

```sh
python examples/simcenter/audit_translated_fluid.py /path/to/native-solver.zip
```

Exit 1 is the expected audit failure for the retained package; it is not a failed
parser test. Four offline regressions cover the actual density mismatch, matching
other properties, unit rejection and nonconstant-property rejection. Native data:
`finned-translated-flow.prp`, `finned-translated-flow.prm`,
`finned-translated-material-verified.json`, and `finned-density-path-*` under
`tests/simcenter/evidence/`. Large ZIP/native binaries remain outside Git.

Documentation check: the current Help Server collection listing contains
Designcenter user help and NX API collections. Targeted searches of that user-help
collection and the active installation's thermal/solver documentation directories
found no Simcenter fluid-property manual. The user has been asked whether the
Simcenter 3D Thermal/Flow user or solver documentation package is available.
This is a documentation gap, not evidence of a missing solver or licence failure.
No licensing configuration, vendor solver files or production models were changed.

Next: obtain a documented reference-density/material-control route or another
supported discriminating test. Keep the density mismatch as an acceptance blocker;
do not change intended density merely to match the substituted value. No solver is
currently running. The full goal remains active.

### Extended run, persistence and active-pressure export guard

`coupled-finned-layer-extended-r1` completed at iteration 883 in 652 seconds.
All five final flow-equation rows and coupled criteria report OK. Energy residual
is 1.907e−7 (target 1e−6), reported mass imbalance 1.382e−11% and energy imbalance
0.008777% (both targets 0.1%). Coupled heat imbalance is 9.817e−5 (target 1e−4)
and maximum change 5.722e−6 °C (target 0.001 °C). Heat to air is 0.09999 W from
0.1 W applied. Public MCP verified terminal input identity and released the gate.
This closes this run's convergence checks, **not physical or mesh acceptance**.

Native density output is uniformly **1.2943761349 kg/m³**, whereas native material
readback and XML specify **1.2 kg/m³**. Thus the discrepancy is present in the
field, not merely a reference-density log row. Its cause remains unresolved; do
not silently substitute the observed density for the intended property or claim
that other fluid properties were honored. Defer the next refinement solve until
this material-to-solver mapping is understood.

The expanded native fixture audit passes F1/F2 applicability checks: actual heat
and boundary-temperature wrappers are expression-backed, the three intended BCs
belong to the selected solution, the single step is empty, and inlet/opening bind
the explicit 20 °C table. F3 is inapplicable because no Head Loss table exists.
These observations do not repair the general fingerprint defects. On the same
isolated run, save/close/reopen preserved all audited state and all three temperature
result representations. Original XML/BUN hashes and unrelated part flags remained
unchanged. A fresh-copy export preserved both 20 °C bindings. Lifecycle check:
8.531 seconds; no additional solve. See `finned-layer-result-reopen.json`.

A subsequent small 2 mm diagnostic used documented `Ambient Pressure=0` and an
expression-backed 101325 Pa value. Native readback passed, but XML contained an
active pressure of zero. The assertion stopped **before launch**. This is a new,
separate observation from the correctly inactive stored pressure under mode 1.
The never-launched job `coupled-finned-pressure-r1` is now explicitly failed, with
its original input retained. No pressure test solve ran.

`input_export.py` now checks the pressure selector and, for specified pressure,
requires an expression-backed Pa value and matching millimeter XML pressure within
0.001 Pa. Unverified field-backed representations are rejected. Mode 1 checks the
selector without treating stored absolute pressure as active. Native checks of
both branches passed after deployment; loaded source hashes match local files.
The temperature export guard remains unchanged. Neither this pressure finding
nor the density observation resolves the 20 °C → 0 °C global-temperature defect.

Targeted offline coverage: **39 passed**, including the actual exported pressure
fixture, unit/selector mismatch rejection, unsupported field rejection and existing
temperature/external-condition guards. This is not a full-suite claim; F5's stale
public-action test remains in the stated hardening backlog. Public export tool text
now describes actual coupled support and guard limitations; no new action was added.

Reproduction adapters: `probe_finned_specified_pressure.py`,
`inspect_finned_density.py`, `audit_coupled_effective_inputs.py`,
`verify_finned_result_reopen.py`, and `run_finned_tight_controls.py` with
`variant="layer_extended"`. They use isolated folders and reject blind replay.
Native evidence under `tests/simcenter/evidence/`: `finned-layer-extended-*`,
`finned-layer-result-reopen.json`, `finned-pressure-r1.xml`,
`finned-pressure-probe-*` and `coupled-pressure-guard-native.json`.

Next bounded investigation: inspect documented fluid/reference-property controls
and solver subdomain mapping, then test one discriminating change on the smallest
adequate fixture. Keep the verified guards active. Do not run another expensive
layered solve until intended regional density is demonstrably honored.

### Finned wall-layer fixtures and bounded convergence follow-up

The `layer_coarse` fixture used 1 mm bulk sizing, twelve fluid wall faces,
eight layers at 0.05 mm first thickness and growth 1.2. Its 31,769 elements
included 164 reported FaceWarpCoefficient errors. It was **not solved**. Fixture
authoring now stops on native quality errors before adding boundaries.

The independent `layer_fine` fixture uses 0.025 mm first thickness and the same
bulk size, layer count and growth. Its 33,275 elements comprise 11,531 tetrahedra,
160 pyramids, 20,464 wedges and 1,120 hexahedra, with zero reported quality errors
or warnings. Job `coupled-finned-layer-fine-r1` exited after 391 seconds and 500
iterations **without convergence**: energy imbalance 0.5696%, coupled heat imbalance
0.006369, coupled ΔT 0.0002689 °C. A zero process exit did not pass acceptance.
The public MCP client verified terminal input identity and released the gate;
its convergence assertion failed as intended. Preserve its receipt and warning log.

Diagnostic native quadrilateral boundary readback passed the 72 mm² inlet/outlet
area check. Static pressure drop was 1.11673 Pa, but this is a non-converged result.
Recovered field integrals are not conservative solver fluxes. The boundary log
mass/volume ratio is approximately 1.2944 kg/m³ versus assigned 1.2 kg/m³; this is
an investigation trigger, not proof that the region material was ignored.

A separate same-mesh copy, `coupled-finned-layer-extended-r1`, increases the bounded
iteration budget to 1,200 and requests documented `Fluid Densities` and `Mass Fluxes`
outputs. All nine scalar/boolean controls match native readback and exported XML.
Preparation took 3.593 seconds; launch was recorded exactly once. Convergence
criteria and physical inputs remain unchanged. The final error rate of roughly
0.989 per iteration motivates this budget; it does not guarantee convergence.
Do not mutate NX or relaunch while this job runs. No restart/freeze control was
changed without evidence.

The expanded `audit_coupled_effective_inputs.py` includes SimulationObjects and
explicit external-table bindings. Its fixture validator rejects changed solution/
step membership, unaudited fields, missing boundary-temperature bindings and head
loss. Eleven offline rejection/contract tests plus two analytical quadrature tests
pass. The expanded native snapshot check subsequently passed; see the section above. This fixture-specific
guard does not repair or certify the general live-state fingerprint.

Evidence: `tests/simcenter/evidence/finned-layer-fine-r1-final*`,
`finned-layer-fine-r1-terminal-status.json`, `finned-layer-fine-diagnostic-fields.json`
and `finned-layer-extended-launch.json`. Older live snapshots remain historical.

### Three-mesh boundary-field comparison

The 0.5 mm independent fixture contains 77,212 elements with zero reported
mesh-quality errors/warnings. Its tight-control job `coupled-finned-fine-r1`
completed at iteration 29; public MCP verified terminal input identity and
released the gate. Reported mass imbalance is 1.672e−11%, energy imbalance
0.002218%, coupled ΔT 1.717e−5 °C and coupled heat imbalance 1.822e−5.
These small residual/balance values do not establish spatial convergence.

Native boundary-field extraction across the three completed tight-control runs
integrated recovered linear triangular values, verifying exactly 72 mm² at each
inlet/outlet. Extraction took 4.453 s and restored the previously displayed SIM.

| Mesh | Native solid maximum °C | Area-mean static pressure drop Pa |
|---|---:|---:|
| 2 mm | 24.602049 | 0.142320 |
| 1 mm | 23.298220 | 0.304006 |
| 0.5 mm | 22.793631 | 0.573922 |

Temperature rise changes about 15% between the last two meshes, while pressure
drop changes substantially. Neither quantity is mesh converged. Recovered
boundary velocity/temperature integrals are not the solver's conservative face
fluxes; their residual differences must not replace native balance diagnostics.
Input hashes and actual result field/location IDs are retained in the evidence.

The bounded near-wall API review found the existing `boundary_layers.py` adapter
and previously native-tested tetrahedral wall-layer workflow below; reuse it
instead of inventing another meshing API. Installed references are
`nxopen_python_ref/a30725.html` (MeshControlBuilder) and `opencae/RECIPES/HYBRID.html`.
Next use independently copied finned geometry with selected fluid wall layers,
verify generated layer/mesh/assignment readback, then compare two controlled wall
resolutions with identical physics and tight solver criteria. This may reduce
uniform-refinement cost; it is not yet verified for this finned geometry.

Evidence: `tests/simcenter/evidence/finned-fine-*` and
`finned-boundary-comparison.json`. Reproduction:
`examples/simcenter/inspect_finned_boundary_fields.py` and
`inspect_finned_mesh_series.py`. No acceptance E claimed.

### First spatial refinement result

The tight-control 1 mm job `coupled-finned-refined-r1` completed and its terminal
input identity/gate release were verified by a fresh public MCP client. At
iteration 18 the rounded solid maximum is 23.30 °C, fluid maximum 22.83 °C,
heat to air 0.1000 W, mass imbalance 3.031e−7%, energy imbalance 0.001012%,
coupled ΔT 9.537e−6 °C and normalized heat imbalance 4.517e−6.
The temperature rise above the 20 °C inlet changes from 4.60 to 3.30 °C
between 2 and 1 mm meshes, about 28% relative to the coarse rise. This is
**not mesh convergence**, regardless of the small balance errors. Next compare
the independently generated 0.5 mm case with identical physical inputs and
numerical settings, including pressure drop and region-associated temperatures.

Evidence: `tests/simcenter/evidence/finned-refined-{launch,r1-status}.json`.
The source builders are parameterized for bounded independent meshes, avoiding
copies of the authoring workflow. No baseline FEM/CAD was remeshed in place.

### Finned convergence-control study

Before spatial refinement, the same 2 mm mesh was solved with RMS residual
threshold 1e−6, enabled flow/heat imbalance fractions 0.001, coupled temperature
change 0.001 °C and coupled heat imbalance fraction 1e−4. Native readback and
exported XML matched all five scalar controls. The preceding installed defaults
allowed flow imbalance fraction 0.02 (2%). This numerical-control change is
kept separate from physical/geometry changes.

`coupled-finned-tight-r1` completed in 28 s at iteration 11: native reported mass
imbalance 0.005447%, energy imbalance 0.0001144%, heat to air 0.1000 W,
coupled ΔT 1.907e−6 °C, normalized heat imbalance 8.35e−9. Rounded solid maximum
remains 24.60 °C. This supports loose stopping criteria as the main source of the
prior mass imbalance; it does not prove mesh convergence. Public MCP verified
terminal state/input identity and released the gate. Coincident-node warning remains.

The reusable finned builders now accept only three bounded mesh cases: baseline
2 mm, refined 1 mm and fine 0.5 mm, each with independent CAD/FEM/SIM names.
The 1 mm setup completed with 12,468 elements and no reported quality errors or
warnings. It preserves the analytic geometry and physical inputs. Its distinct
job `coupled-finned-refined-r1` uses the same tight numerical controls.
No refinement acceptance is claimed until final results are compared.

Scripts: `build_finned_coupled_fixture.py`, `author_finned_coupled_boundaries.py`,
`run_finned_tight_controls.py` and parameterized `audit_finned_baseline_mcp.py`.
Native evidence: `tests/simcenter/evidence/finned-tight-*` and
`finned-refined-setup.json`. No licensing changes or production models involved.

### Finned baseline execution (acceptance remains open)

Native mesh-quality checks covered 2,130 elements with zero reported errors and
warnings under the recorded installed criteria (not all possible checks).
The fixture has 745 nodes. Solution membership contains the 0.1 W heat load,
velocity inlet and opening, with no step additions. Both boundaries reference
specified 20 °C external conditions. Global reference is explicitly 0 °C;
the general ambient export limitation and guard remain unchanged.

The first preparation failed its native setup check: Opening selected specified
absolute pressure but the value was NX's unset sentinel. The corrected fixture
now authors 101325 Pa explicitly. A separate r2 copy read back selector/value/units
and exported 101.325 mN/mm², 1000 mm/s inlet, 0.1 W heat and assigned material
properties. Failed artifacts are preserved. This was a fixture-authoring error,
not a licence/network failure or resolution of global temperature export.

`coupled-finned-baseline-r2` prepared in 2.359 s and ran 28 s. Rounded final log:
solid maximum 24.60 °C, fluid maximum 22.58 °C, Q=7.2e−5 m³/s,
heat to air 0.09998 W against 0.1 W applied, coupled ΔT=7.267e−4 °C,
normalized heat imbalance 2.168e−4. Reported mass imbalance is **1.388%**,
energy imbalance 0.07882%. No iteration-limit or pressure-anchor warning;
coincident thermal nodes remain. Do not accept this mesh or infer convergence
from solver exit. Refine with identical physics, tighten relevant criteria and
audit interfaces/field identity before accepting the coupled milestone.

Reproduction scripts: `author_finned_coupled_boundaries.py`,
`prepare_finned_pressure_fix.py`, `launch_finned_coupled.py`, and
`audit_finned_baseline_mcp.py` under `examples/simcenter/`. Observe the existing
job rather than rerunning launch scripts. Evidence is under
`tests/simcenter/evidence/finned-*`, including retained failure/setup reports,
corrected XML, preparation/launch receipts and final solver log.

### Finned baseline fixture setup

`examples/simcenter/build_finned_coupled_fixture.py` now creates an independent
CAD/FEM/SIM set under `ui-benchmarks/E-finned-baseline-20260908-r1`. The solid
is a 20×10×2 mm base united with two 20×1×4 mm fins. Fluid occupies the
20×10×8 mm envelope above the base with both fin volumes subtracted. Native
volumes match analytic solid 560 mm³ and fluid 1440 mm³ within 1e−5 mm³.
Both regions have tetrahedral meshes with requested 2 mm sizing and constant
material assignments; five documented coupled tables and a step were created.
This is setup only: boundary authoring, actual mesh-quality/count readback,
interface validation, solve and refinement remain. No physical acceptance yet.

Native geometry/FEM preparation took 1.766 s, meshing 1.141 s, total setup
6.032 s. The first attempt failed because `Point3d` requires floats; its receipt
was retained. The corrected attempt resumed only after verifying the exact
failure and that the current isolated CAD part had no bodies or features.
Evidence: `tests/simcenter/evidence/finned-build-result.json`.

### Coupled boundary persistence verification

`verify_external_conditions_reopen.py` saved an isolated SIM copy, closed only
that unmodified copy, reopened it and compared selected solution membership,
ordered steps, boundary wrapper observations, global wrappers, pressure mode and
tables. All six comparisons matched. Re-export retained specified 20 °C external
conditions referenced by both inlet and opening. The unchanged temperature guard
verified the explicitly declared 0 °C global reference. Elapsed native time:
5.625 s; no solver launch. SaveAs verified the original diagnostic file hash
unchanged; unrelated modified flags did not change on reopen.

Evidence: `tests/simcenter/evidence/coupled-external-reopen.json` and
`coupled-external-reopen-deck.xml`. This closes the narrow input-persistence check,
not result-association persistence or full benchmark acceptance. Source scripts
retain failure/partial receipts and reject blind replay.

### External-temperature diagnostic, 2026-09-08

`coupled-external-diagnostic-r1` used explicitly declared global reference
0 °C and external inlet/opening temperature 20 °C. The ambient export guard
remained enabled. Preparation took 2.094 s and the solver ran 29 s on the
126-element/68-node fixture. Final flow, thermal and coupled rows report `OK`
at iteration 8; the previous iteration-limit failure is absent. This is diagnostic
evidence, not acceptance E or a fix for general ambient export.

Rounded log values: solid maximum 43.20 °C, fluid range 20.03–22.13 °C,
volume flow 5e−5 m³/s, inlet/outlet mass magnitudes 6.472e−5 kg/s,
pressure range 0.7858–0.8344 Pa relative to the native solution reference,
heat transferred to air 0.1000 W against 0.1 W applied. Coupled temperature
change is 7.248e−5 °C and normalized heat imbalance 3.111e−6. Native reported
mass imbalance is 0.4066%, energy imbalance 0.005482%; rounded equal boundary
flows do not establish exact conservation. Coincident-node and pressure-anchor
warnings remain. No refinement or finned acceptance geometry is claimed.

Reproduce observation with `examples/simcenter/audit_coupled_external_diagnostic_mcp.py`
on the authorized host. It observes the existing job, verifies terminal input
identity, releases only its terminal gate, and retrieves the log through public
MCP. It never launches a solve. Launch fixture:
`examples/simcenter/launch_coupled_external_diagnostic.py` (durable receipt;
do not rerun for observation). Evidence:
`tests/simcenter/evidence/coupled-external-diagnostic-{launch,status}.json`
and `coupled-external-diagnostic.log`. The API deliberately retains
`numerical_convergence: not_established` and `results_validated: false` until
all criteria, result identity and mesh acceptance are independently audited.

The deployed `nx_sim_temperature_result` now accepts `location: nodal | elemental |
element_nodal` (nodal default preserved), allowing explicit access to all three
native temperature fields. It does not infer solid/fluid semantic ownership.
On this fixture, native/public MCP extraction gives nodal 43.193336–43.201298 °C,
elemental 43.192856–43.201157 °C, and element-nodal 20.025627–22.133400 °C.
Native pressure extraction gives 0.785822–0.834437 Pa. The existing result inventory
contains no density field; region density remains unverified. Field inspection
ran in 0.219 s without a solve. Modified state was already true and remained true;
this is not proof of result freshness. No automatic save was performed.

Reproduce schema and field readback with
`examples/simcenter/verify_coupled_temperature_fields_mcp.py`; native inventory
with `examples/simcenter/inspect_coupled_external_results.py`. Evidence:
`tests/simcenter/evidence/coupled-temperature-fields-{native,public}.json` and
`coupled-external-native-results.json`. Thirteen focused reader/log regression
checks pass, including missing-field rejection without fallback and invalid
location rejection before loading results. Numerical acceptance still requires
region association, interface validation and a justified refinement comparison.

### Coupled diagnostic and ambient mapping, 2026-09-08

`coupled-diagnostic-r1` executed natively in the visible Simcenter session using
126 elements and 68 nodes. Preparation took 2.11 s; solver elapsed time was 26 s.
A new public MCP client observed `solver_exited` and released the verified gate
without relaunching. This is diagnostic evidence, **not acceptance E**. The flow
iteration limit was reached without convergence. Rounded log values show a
23.13 °C solid maximum, 2.127 °C fluid maximum, 0.09971 W transferred to fluid
against 0.1 W applied, and 0.02541% reported mass imbalance. Coincident-node and
pressure-anchor warnings remain. Coupled temperature change was 1.185 °C.

The solver used 0 °C ambient although native setters read back 20 °C. It also
reported adjusted ambient fluid density 1.2944 kg/m³ versus the requested region
density 1.2 kg/m³. That global altitude-adjustment summary is not proof of a
wrong region assignment: the subdomain explicitly names Development air[2].
Per-region density still requires extraction. The ambient-temperature mismatch
is confirmed by both export and solver log. The next bounded investigation targets
ambient/material export semantics; increasing iteration limits alone cannot fix
these inputs. No Baldower model or refinement solve was started.

A separate export-only copy tested the installed SDK's
`CAE.PropertyTable.SetScalarWithDataPropertyValue` and matching getter, distinct
from the previous base-table setter and field-wrapper routes. Native readback
passed and export completed, but ambient temperature and absolute pressure still
serialized as zero. This route is exhausted; do not repeat it without new evidence.
Source: installed `NXOpen.xml`, CAE PropertyTable scalar-with-data overloads.

Reproduce status/recovery using `examples/simcenter/audit_coupled_diagnostic_mcp.py`;
reproduce the bounded setter experiment using
`examples/simcenter/export_coupled_cae_scalar.py` through the native probe harness.
These fixtures guard exact source paths and preserve existing output directories.
Do not replay the launch fixture to observe a job. Evidence is in
`tests/simcenter/evidence/coupled-diagnostic-{launch,status,summary}.json`,
`coupled-diagnostic.log`, `coupled-cae-scalar-export.json` and
`coupled-cae-scalar-deck.xml`. Targeted export/preparation/launch checks: 20 passed.
Saved-input/dependency hashes protect this launch route; complete live coupled
thermal-state fingerprinting remains unimplemented.

### Coupled ambient guard and override experiment

The installed `BasePropertyTable.SetTablePropertyOverride` API rejected the
ambient property with NX code 3520001. The isolated copy was retained; subsequent
native inspection read back 20 °C. Do not treat the presence of a general override
API as support for this particular property. Evidence:
`tests/simcenter/evidence/coupled-override-export.json`.

`export_flow_input` now compares constant coupled ambient temperature readback
against the emitted XML using the observed Celsius convention. Unknown units or
layout fail verification. A mismatch raises `NX_SIM_EXPORT_FAILED`, retaining
both values and the output directory; new preparation therefore cannot accept
this known bad export. This is a narrow input consistency check, not full model
validation or a fix for the setter/export discrepancy. Existing historical job
records are unchanged.

Deployed without restarting Simcenter. Native verification rejected 20 °C → 0 °C
in 1.953 s (export plus validation), retained artifacts and launched no solver.
Reproduce with `examples/simcenter/verify_coupled_ambient_guard.py` via the existing
native probe harness; receipt:
`tests/simcenter/evidence/coupled-ambient-guard-native.json`. Local checks:
`pytest -q tests/simcenter/test_coupled_input.py tests/simcenter/test_input_export.py tests/simcenter/test_preparation.py tests/simcenter/test_native_launch.py`
— 26 passed. These include the real mismatching XML, unknown-unit rejection and
existing preparation/launch regression cases; they do not establish native coupled
acceptance. Next action remains supported ambient serialization/ownership
investigation before a corrected solve. No refinement or convenience work was added.

### Direct expression binding and coupled log audit

The installed `BasePropertyTable.SetScalarPropertyValue` / `GetScalarPropertyValue`
route rejected the ambient field with NX code 3945002 (“This Property type does
not support this interface”). The copy and failure remain available; no solver
was launched. Evidence: `tests/simcenter/evidence/coupled-expression-export.json`;
fixture: `examples/simcenter/export_coupled_expression.py`. Stop trying setter
variants without new evidence. The saved `coarse_cube_thermal_sim-sol1.xml` sample
has a correct 20 °C ambient, but its header identifies NX 2306 (2023), not a
successful export from the current 2606 installation; it is a comparison lead,
not a verified fix.

The existing `nx_sim_flow_log` reader now recognizes the observed coupled log
layout, includes the fluid energy equation in residual history, and returns a
`coupled_summary` with rounded temperatures, applied power, heat transferred to
fluid, coupled temperature change, normalized heat imbalance and known warnings.
An explicit iteration-limit warning reports coupled non-convergence. Flow residual
criteria are not repurposed as coupled acceptance. Duplicate histories stay
unclassified, and summary rows do not claim region identities or replace native
field extraction. Six targeted reader tests pass, including the actual diagnostic
and the existing standalone flow log. Deployed without restart and verified
through a new public MCP client against `coupled-diagnostic-r1`; receipt:
`tests/simcenter/evidence/coupled-diagnostic-audit-public.json`. Reproduce with
`examples/simcenter/audit_coupled_log_mcp.py`; no solver rerun is required.

### Native representation comparison and property copy

The retained **2606** thermal and standalone flow decks also export 20 °C
correctly (`outputs/simcenter/thermal-input.xml` and the retained cavity-solve01
deck), so the good control is not limited to the older 2306 sample. Native
inspection found the same property type (scalar field wrapper), value and
expression for thermal, flow and coupled ambient temperature. Inspecting field
expression views initialized native objects and marked three isolated copies
modified; do not describe those getters as read-only or save those changes
implicitly. The receipt identifies paths and changed tags:
`tests/simcenter/evidence/ambient-representations.json`. Native inspection took
0.047 s; no solver ran.

The documented `BasePropertyTable.CopyProperty` route copied thermal ambient
properties to a new coupled SIM, with matching native readback. Export completed
in 2.219 s with no setup error, but ambient temperature and pressure still
serialized as zero. This weakens the malformed-expression hypothesis and keeps
coupled solution setup/serialization as the next investigation. It is not proof
of the faulty internal layer. Evidence: `coupled-copy-property-export.json` and
`coupled-copy-property-deck.xml` under `tests/simcenter/evidence`; fixture:
`examples/simcenter/export_coupled_copy_property.py`. No solver or refinement run
was performed, and the ordinary preparation mismatch guard remains active.

### Solver-language documentation availability

The installed NXOpen SDK explicitly refers modeling-object users to
`../opencae/Solvers.html`. A bounded filename search of Designcenter2606 found
no such installed file (3.878 s); receipt:
`tests/simcenter/evidence/solver-language-doc-paths.json`. This documentation is
missing locally; it does not prove the API or solver module is unavailable.
No commercial software or licence settings were changed. Existing native
solution discovery identifies `Thermal-Flow` under
`NX MULTIPHYSICS - Coupled Thermal-Flow`; public tutorial labels such as
“Advanced Thermal-Flow” are not substitutes for native factory identifiers.

### Ambient persistence/reload check

A new disposable coupled SIM was saved, closed with the existing guarded
lifecycle API and reopened. Native ambient readback remained 20 °C; fresh export
again serialized 0 °C and the deployed input guard rejected it. The lifecycle
plus export check took 8.921 s and launched no solver. This weakens a simple stale
in-memory cache explanation; it does not identify the internal faulty layer.
Receipt: `tests/simcenter/evidence/coupled-ambient-reopen.json`; reproducible
fixture: `examples/simcenter/verify_coupled_ambient_reopen.py`. Its per-stage
receipt prevents blind repetition after interruption. Other loaded documents
were not intentionally closed, saved or recreated.

### Solve-manager route and current external blocker

The installed `SimSolveManager.SolveChainOfSolutions` export-only route returned
counts [1, 0, 0] (processed successfully, failed, skipped) with no prerequisites.
It produced the same zero ambient temperature in 2.359 s. These counts describe
input export, not a numerical solve. Evidence:
`tests/simcenter/evidence/coupled-manager-export.json` and
`coupled-manager-deck.xml`; fixture:
`examples/simcenter/export_coupled_manager.py`. No solver was launched.

The confirmed 20 °C native / 0 °C exported discrepancy persists across scalar,
field-wrapper, field-expression and time-table setters; direct expression and
override routes reject the property; copying a working thermal representation,
save/reopen and both solution/solve-manager export paths do not resolve it.
The same installed version exports the thermal/standalone-flow controls correctly.
No new supported factory or setter mapping is established. The installed SDK's
referenced solver-language documentation is absent. Further coupled milestone
progress requires version-matched solver-language documentation or a confirmed
Siemens API mapping/reproducer for coupled solution creation and ambient fields.
This is an unresolved integration/API mapping blocker, not a proven licence
failure or blanket claim that the native product is broken. Do not change
licensing, guess descriptors, patch exported boundary values silently, or accept
a solve using different conditions. All broader goal requirements remain open.

### Documented coupled control mapping resolved

The newly installed Open CAE sample distinguishes the solution property key
`Coupled Solution Parameters` from its modeling-object descriptor
`Thermal-Flow Coupled Solution Parameters`. Native creation and association of
that descriptor succeeded on 2606. Readback: communication frequency 1, maximum
temperature change 0.1 CelsiusDifference, global heat-imbalance fraction 0.01.
Export includes the table; it still emits zero ambient temperature, so these
were separate issues. Native export took 2.203 s; no solver was launched.

The server's `nx_sim_flow_setup(action="attach_defaults")` now attaches all five
coupled tables using the correct descriptor mapping. Deployed without restart.
Seven targeted flow tests passed. A fresh small authoring fixture verified table
creation, same-operation replay and saving through public MCP; no mesh or solve
was needed. Receipts: `tests/simcenter/evidence/coupled-documented-controls.json`,
`coupled-documented-controls-deck.xml`, and `coupled-defaults-public.json`.
Reproduce with `examples/simcenter/export_documented_coupled_controls.py` and
`examples/simcenter/verify_coupled_defaults_mcp.py`. Existing configured tables
remain protected from automatic replacement. Ambient mapping and coupled
numerical acceptance remain open. The first public receipt retains a stale
`unresolved_controls` description; that response metadata was subsequently
corrected, regression-tested and redeployed. Final native reload/readback receipt:
`tests/simcenter/evidence/coupled-controls-reload.json`.

### Explicit inlet/opening temperature: documented route

The new reference identifies `External Conditions` as the modeling-object
descriptor behind the boundary property `Inlet Conditions`. `Temperature Option`
0 means Specify; `Temperature Value` accepts a scalar field wrapper. Native
creation, 20 °C readback and assignment to both the inlet and opening succeeded.
Export includes the explicit 20 °C value and both references to that table.
Evidence: `tests/simcenter/evidence/external-conditions-native.json` and
`coupled-external-conditions-deck.xml`; native fixture:
`examples/simcenter/export_external_conditions.py`. This resolves the previously
unknown external-condition descriptor; it does not fix global ambient export.

`nx_sim_external_temperature(document, boundaries, name, temperature_c)` implements
the verified constant-temperature route with typed boundary IDs, ownership and
existing-binding checks, native readback and rollback. It creates one shared
conditions table for 1..100 inlet/opening objects in the SIM, marks results
for revalidation, and does not save or solve. It is currently restricted to
Coupled Thermal-Flow. Thirteen targeted tests passed across external conditions
and flow setup, including forced readback failure/rollback and input rejection.
Numerical use of these conditions and global ambient semantics still need a
corrected benchmark; no new solve was launched. Deployed without restart and
verified through public MCP: two boundary bindings at 20 °C, identical table ID
on same-operation replay, and save passed. Receipt:
`tests/simcenter/evidence/external-temperature-public.json`; reproduce with
`examples/simcenter/verify_external_temperature_mcp.py`.

### Coupled control discovery: bounded attempt, 2026-09-08

Hypothesis: public metadata or native solution property references identify the
missing table descriptor. Sources: installed `NXOpen.xml` modeling-table factory
signature and `uf_sf.h` solution property count/index functions. Public example and
text metadata scan completed in 8.09 seconds with no matching descriptor. Native
read-only probe took 0.015 seconds: 102 solution properties exceeded
its explicit 100-item bound; 30 solver property tags were returned, but ordinary
UF object name/type queries rejected these descriptor tags (1155001/1105004).
All document modification flags were preserved. No mesh or solve was run.

This route does not resolve the mapping. Do not repeat ordinary object lookups on
these descriptor tags. Next route: inspect documented descriptor-specific property
accessors or a shipped coupled template with populated controls. Evidence:
`tests/simcenter/evidence/coupled-public-metadata.json` and
`coupled-property-references.json`; reproducible native probe:
`examples/simcenter/inspect_coupled_property_references.py` via the existing probe
harness. Timings above measure native discovery only; deployment/transport time
was not instrumented and must not be inferred from the turn duration.

## Current native evidence

The initial adapter was exercised in the open NX UI on Designcenter/Simcenter
2606. Installed CAE libraries report build 2606.2514; the Simcenter launcher
reports 2606.1700. These are individual file versions, not a claim that every
installed component has the same build.

Validated so far:

- Open and close isolated copies of the shipped thermal FEM/SIM templates.
- Create an isolated 100 × 10 × 10 mm block, associate a FEM and create a SIM.
- Create the native `NX MULTIPHYSICS` / `Thermal` / `Thermal` solution.
- Generate a linear tetrahedral mesh: the initial 5 mm test produced 496 elements
  and 196 nodes. Read back native mesher settings and counts.
- Create an isotropic thermal material with explicit SI conductivity, density and
  heat capacity; assign it to solid mesh collectors and read back the assignment.
- Attach an independent bridge to the Simcenter UI and leave benchmark meshes visible.
- Save newly created analysis files and restore the original loaded CAD session.

The isolated conduction benchmark now passes its specified temperature and energy
tolerances, including native result extraction and save/close/reopen consistency
(see `tests/simcenter/evidence/acceptance-A.json`). The transient benchmark also passes its analytical, time/mesh-refinement and
energy checks (see `tests/simcenter/evidence/acceptance-C.json`). Contact, fan/duct
and coupled-cooling benchmarks remain incomplete. Mesh generation alone does not
establish mesh convergence. Thermal execution and result reading worked on this
host; this does not establish coupled-airflow or other licence availability.

Checked input export returns with a library material and, after the constant
representation fix, with a custom material. The custom material section contains
200 W/(m K), 2700 kg/m³ and 900 J/(kg K), with the correct collector assignment.
Constants are created as expression-backed wrappers; inspection preserves existing
wrapper representations. Earlier diagnostic materials retain altered optional
properties and are not repaired automatically.

Earlier complete exports were malformed in the ambient-property section; native
setup checks did not catch this. Restoring four ambient constants as expressions,
with unchanged values and units, produced well-formed XML with one step in export
10. The input validator rejects malformed files; XML validity alone does not
establish solve readiness. Run 02 reached native result postprocessing and produced
a 54,628-byte result bundle. The native log reports 1 W rejected to the sink.
Native extraction gives 20.0–24.999950408935547 °C. The 0.000992% rise error and
0.001942% heat-balance deviation meet benchmark A tolerances, and the values and
result hash are unchanged after save/close/reopen.
No licensing configuration is changed by this extension.

Flow and coupled thermal/flow document creation are also natively tested on this
host. The factory returned `NX MULTIPHYSICS / Flow / Flow` with `Step - Flow`
available, and `NX MULTIPHYSICS / Coupled Thermal-Flow / Thermal-Flow` with
`Step - Thermal Flow` available. A separate Flow fixture was created through real
MCP stdio discovery and the compact agent gateway. Saved-document flags and native
solution identifiers were read back. Evidence is in
`tests/simcenter/evidence/native-flow-documents.json`; reproduce the MCP creation
with `examples/simcenter/verify_flow_creation.py --help`. These are document and
solution tests, not fan/duct or coupled-cooling acceptance, and do not establish
availability of the required solver licences at execution time.

The internal Flow configuration adapter creates the initial `Step - Flow`, then
attaches `Flow Solution Parameters`, `Flow Surface Parameters` and `Flow Output
Requests` using native association readback. The initial step has native Solution
Type 1 and an unset end time; no steady/transient interpretation is claimed yet.
The three attached tables expose 64, 10 and 45 properties respectively. Existing
steps/tables are rejected rather than replaced, and failures roll back; local
failure-injection tests cover partial creation and failed recovery.

These operations passed in the isolated MCP Flow fixture. They do not save or
solve. The public `nx_sim_flow_setup` tool accepts a live document ID and either
`action="create_step"` or `action="attach_defaults"`; its current scope is Flow.
Use `nx_sim_activate` first, reacquire document IDs, then provide a distinct durable
`operation_id` for each setup mutation. Numerical validation remains incomplete.
`Flow Boundary Condition` and `Duct Flow Boundary Conditions`, taken from the
installed command metadata, both failed the simulation-object builder with
NX 1543292. That does not establish missing airflow or a licence failure.
Native follow-up resolved the 3D Flow builder mapping: the specific descriptors
`Inlet`, `Outlet`, `Opening`, and `Internal Fan` all create builders in the
NX MULTIPHYSICS Flow SIM. The group title is not a valid native subtype. Inlet,
outlet and internal-fan builders expose mass/volume flow and fan-curve properties;
opening exposes external pressure. Initial Fluid Pressure and Initial Fluid
Velocity constraint builders also work. This verifies builder/property access,
not configured boundaries, fan interpolation, solver support or numerical results.

Builder creation itself adds SIM boundary objects; `Destroy()` alone did not
remove them. Six temporary probe objects were identified and removed from the
disposable SIM, then a corrected probe verified that per-builder undo checkpoints
leave simulation objects unchanged and zero constraints. Discovery code must
therefore treat builder probes as mutations and perform rollback. Evidence:
`tests/simcenter/evidence/native-flow-subtypes.json` and
`tests/simcenter/evidence/native-flow-probe-cleanup.json`; fixture:
`examples/simcenter/inspect_flow_subtypes.py`.
An isolated Flow authoring fixture also committed an `Inlet` simulation object
using a scalar expression of 1 m/s and one SIM occurrence face at x=0. Native
readback verified the expression, MeterPerSecond unit and exact face tag.
`Mode Option` was left at its native default; its numeric convention and solver
interpretation have not yet been validated. This is an authoring check, not a
solved duct benchmark. It leaves the displayed fixture SIM unsaved and records a
persistent receipt to prevent duplicate assignment. Evidence:
`tests/simcenter/evidence/native-inlet-assignment.json`; fixture:
`examples/simcenter/verify_inlet_assignment.py`.
Evidence: `tests/simcenter/evidence/native-flow-configuration.json`; native table
fixture: `examples/simcenter/verify_flow_tables.py`.

Public activation, step creation and table assignment also passed through real MCP
stdio and the compact agent gateway. Repeating the same step mutation ID returned
an explicit replay receipt without a duplicate step. The first attempt exposed an
incomplete development hot-reload: activation was advertised but its live handler
was absent. Reloading the entire Simcenter handler set fixed that mismatch without
restarting NX. Evidence: `tests/simcenter/evidence/native-mcp-flow-setup.json`.
Reproduce against a loaded, unconfigured isolated Flow fixture with
`examples/simcenter/verify_flow_setup.py --help`. The development-only native-thread
hook `examples/simcenter/reload_simcenter.py` resolves all handlers before updating
the live registry; it does not replace clean-start deployment verification.

The internal fluid-domain adapter has generated one native CAE body from a closed
duct cavity using a 2 mm wrapping resolution and zero gap closing. Committed
settings retain the interior seed at [81, 11, 11] mm in FEM coordinates. The source
enclosure has a measured wall volume of 14,408 mm³ and an analytic cavity volume of
64,000 mm³. Native polygon-body measurement returns 64,000.00000000001 mm³,
bounds [1, 1, 1]–[161, 21, 21] mm and centroid [81, 11, 11] mm. The adapter
returns individual body measurements with explicit units and frame, rejects
non-finite or degenerate measurements, and verifies committed source selections.
These measurements do not certify closure, connectivity or interfaces.

The isolated cavity has a native volume mesh with 3,308 Fluid Linear Tetrahedron
elements and 939 nodes at a requested 5 mm size. The installed Flow FEM offers
fluid linear/parabolic tetrahedra and hexahedra. Boundary assignment,
material assignment and flow solving remain unverified; this is not acceptance D
or E. The mesh fixture has persistent receipt replay and refuses a second mesh
when no receipt exists. It leaves the FEM unsaved. Evidence:
`tests/simcenter/evidence/native-fluid-mesh.json`; reproducible native-thread
fixture: `examples/simcenter/verify_fluid_mesh.py`.

`verify_fluid_mesh_quality.py` runs the native checker without repair and exports
bounded element connectivity. The native checker reports zero errors/warnings for
3,308 elements. The internal `quality.py` adapter now captures the active solver's
enabled/disabled tests, warning/error values with native units, global-versus-
element-specific setting and named test results in the same call. On the Flow
fixture, element-specific values are disabled; aspect-ratio warning/error limits
are 10/100 and the worst measured aspect ratio is 4.0829705687292055. No repairs
are attempted. Native enum values for validator and limit options remain numeric;
element-specific overrides are not yet enumerated. Results without a numeric
test value must not be interpreted as measured CFD quality metrics. This internal
diagnostic is not yet a public pre-solve gate. Evidence:
`tests/simcenter/evidence/native-quality-adapter.json`; fixture:
`examples/simcenter/verify_quality_adapter.py`. The Python result binding uses
`Dispose()`, not the installed .NET documentation's `FreeResource()` method.
`audit_fluid_mesh.py INPUT OUTPUT` independently checks the exported rectangular
cavity mesh: one face-connected region, no degenerate tetrahedra, no nonmanifold
faces or boundary edges, all boundary triangles on the expected six planes, and
64,000 mm³ summed element volume. Coordinate tolerance is 1e-7 mm and relative
volume tolerance is 1e-8. These checks cover this planar fixture, not arbitrary
element intersections or CFD convergence. Evidence is recorded in
`tests/simcenter/evidence/native-fluid-mesh-quality.json` and
`tests/simcenter/evidence/native-fluid-mesh-audit.json`; the latter includes the
SHA-256 of the exported connectivity input.

Native testing corrected three issues: the block-specific boolean API is required
for this cavity fixture (the generic block BooleanOption produced overlapping
solids); `InteriorPoint` requires a native Point object (`SetCavityPoint` left it
unset); and recipe creation must be followed by `FluidDomains.UpdateRecipe` to
generate the body. Empty output is rejected and rolled back. The internal factory
now checks cavity body count and analytic wall volume before creating its FEM.
The optional wall-thickness fixture parameter is not yet part of the public tool.
Evidence: `tests/simcenter/evidence/native-fluid-region.json`; native fixture:
`examples/simcenter/verify_fluid_region.py`. Public region tooling and resource
preflight remain incomplete.

The cavity's automatically generated `Fluid1` physical-property table initially
has an inherited, null material reference. It must not be treated as an explicit
air assignment. The property inspector now reports this as `assignment_status:
unresolved`, including the inheritance flag, rather than an unsupported type.
Native fluid-material builder inspection under rollback confirms fields for
MassDensity, ThermalConductivity, SpecificHeat, DynamicVisc, MolarMass and
GasConstant, with control fields for property dependence. Values and their active
controls require solver validation before an airflow solve.
Evidence: `tests/simcenter/evidence/native-fluid-material-schema.json`; fixture:
`examples/simcenter/inspect_fluid_material.py`.

The internal `fluid_material.py` adapter has since created and explicitly assigned
`Benchmark constant air` to the cavity's fluid collector. Native readback verifies
1.2 kg/m³ density, 1.81e-5 Pa·s dynamic viscosity, 0.0257 W/(m·K) conductivity and
1005 J/(kg·K) heat capacity. These are assumed constant benchmark values near room
temperature, recorded in material provenance. The adapter validates positive finite
inputs, rejects existing explicit assignments, and checks values, units and the
non-inherited collector association after commit. Failures use checkpoint rollback
with material-set and assignment verification. Native solver-control interpretation
remains unverified. The authoring operation leaves the FEM unsaved and does
not modify a material library. Evidence:
`tests/simcenter/evidence/native-fluid-material.json`; fixture:
`examples/simcenter/verify_fluid_material.py`.

The cavity CAD/FEM/SIM set subsequently passed a native save/close/reopen test.
Existing files were backed up before saving; only these three isolated documents
were closed. Reopened fluid geometry, 3,308 elements, 939 nodes, material values,
units and collector assignments exactly matched the pre-save snapshot. The SIM
was then activated and given an initial Flow step and the three native parameter
tables. This latest solution configuration is unsaved and not yet solve-ready.
Evidence: `tests/simcenter/evidence/native-fluid-lifecycle.json` and
`tests/simcenter/evidence/native-cavity-flow-setup.json`; fixtures:
`examples/simcenter/verify_fluid_lifecycle.py` and
`examples/simcenter/prepare_cavity_flow.py`. Boundary, solver and result persistence
are not established by this geometry/mesh/material lifecycle test.

The meshed cavity now contains native Inlet and Opening objects targeting the
fluid body's two end faces. Value/selection readback passes with pressure-specific
`PressurePascals` units. The first input export failed because native `Solution
Type=1` created a single transient step; the setup checker reported no material,
mesh or boundary errors and one unmeshed source-body warning. Setting the step
to 0 allowed XML/map export, with no solver launched.

Export inspection exposes limits that model readback alone misses: the inlet
exports 1,000 mm/s, but the opening's stored 101,325 Pa Pressure Value exports as
zero under the default pressure mode. Do not claim the absolute-pressure request
is effective. The fluid exports as constant-property `LIQUID`; compressible gas
and buoyancy semantics are unverified. Source-body exclusion and pressure-mode
selection still need resolution before solver acceptance. Evidence:
`tests/simcenter/evidence/native-cavity-boundaries.json`,
`tests/simcenter/evidence/native-cavity-input-export.json`, and
`tests/simcenter/evidence/native-cavity-input-audit.json`. Fixtures:
`verify_cavity_boundaries.py`, `set_cavity_steady_step.py`, and
`export_cavity_input.py` under `examples/simcenter/`. The export fixture persists
failures and raises a structured error, including on replay of a failed receipt.

Follow-up export verified that opening `Pressure=1` enables the specified pressure:
101,325 Pa now exports as 101.325 in the native millimeter-based pressure units.
`Pressure=0` exported zero despite retaining the requested value in the model.
Evidence: `tests/simcenter/evidence/native-opening-pressure-mode.json`.

A bounded native CFD precursor solve subsequently completed in 24 seconds using
solver 2606.1. The log reports 0.0004 m³/s inflow and equal outflow, mass imbalance
0.009438% and momentum imbalance 0.02323%. This establishes actual execution of
the installed airflow solver for this case, without modifying licensing. The
default `Turbulence Model=2` is identified in the log as Mixing length. It produced
two near-wall y+ warnings (maximum 12.143695; average 8.636821), so this run is not
accepted as validated flow performance. The next run must verify the laminar
selector and repeat. This constant-density forced-flow precursor has no fan,
thermal load or buoyancy and does not pass acceptance D/E. Evidence with artifact
hashes: `tests/simcenter/evidence/native-cavity-flow-precursor.json`; native launcher:
`examples/simcenter/solve_cavity_flow.py`.

Subsequent native comparisons identify `Turbulence Model=0` as Laminar in the
solver log. `Wall Treatment=2` is unsupported wall-function treatment for laminar
flow and triggers warning 1900 with a no-slip fallback. Selector 1 produces
`SLIPADIABATIC F` boundaries; that run reported residuals OK but 195% momentum
and 39.51% mass imbalance after recovery, so it is rejected. Selector 0 produces
`ADIABATIC FACES` with nonzero wall shear and matches the no-slip fallback results
without warnings: 0.1541% mass and 0.001435% momentum imbalance. This verifies the
control mapping; it does not establish mesh convergence or fan performance.
Evidence: `tests/simcenter/evidence/native-laminar-wall-comparison.json`.
The final run is `cavity-flow-solve-04`; its launch fixture is
`examples/simcenter/solve_cavity_laminar.py`. Every comparison has a separate
durable job ID and preserved input/log/result hashes.

## Workflow

1. Discover `nx_sim_capabilities`. API presence, installed executable presence,
   successful operation tests and numerical acceptance are separate facts.
2. Create an isolated fixture with `nx_sim_create_benchmark`, supplying a durable
   `operation_id` and a new workspace-relative folder. Existing folders are rejected.
   `analysis_type` is `thermal` (default), `flow`, or `coupled_thermal_flow`.
   Generated filenames include a deterministic folder identifier because NX rejects
   duplicate loaded basenames across folders. Use returned paths; do not assume
   `geometry.prt`, `mesh.fem` or `analysis.sim`. The thermal step starts in the
   native steady-state setting verified by benchmark A.
   Flow choices create saved CAD/FEM/SIM documents and native solutions, returning
   actual properties and allowed steps. They require further configuration and
   do not yet create a step, fluid domain, boundary, mesh or solve.
3. Inspect `nx_sim_documents`; select the returned FEM document ID. Use
   `nx_sim_activate` to display a loaded FEM/SIM and activate `UG_APP_SFEM`.
   The adapter verifies the actual application, work part and display part.
4. Run `nx_sim_mesh` with the FEM ID and an explicit size in millimeters. It requires
   an unmeshed millimeter FEM. Read back committed mesh settings and element/node
   counts; it does not automatically save.
5. Use `nx_sim_material` with positive SI thermal properties, a unique name and
   provenance. Set `assign_all_solid_collectors=true` only when intentionally
   replacing every solid collector material in the selected FEM. It returns
   actual properties and typed material/collector references; it does not save.
   Constant material export is verified for the isolated benchmark; full analysis
   readiness still requires a valid input deck and all pre-solve checks.
6. Boundary assignment → validation → solve → result audit → export stages are still
   under implementation. Do not substitute screenshots or an empty solution for
   a numerical benchmark pass.

Document references use the existing session and owning-part lifecycle. Names are
presentation only. Reacquire IDs after close/reopen or manual handoff. Meshing runs
serially on the NX UI thread, with an undo mark. Failure reports rollback status.
Analysis creation saves only its new files; partial files are retained and reported
when creation fails. No implicit deletion or overwriting of production CAD occurs.

The interactive bridge displays modeling and meshing operations in NX and retains
its agent/manual handoff controls. Native operations can still occupy the UI
thread. Asynchronous solver progress remains part of the implementation work. Native
result visualization is verified below; it is not yet exposed as a public tool.

## Inputs and evidence

`examples/simcenter/benchmarks.json` defines analytical references and tolerances;
it is explicitly a specification, not a pass report. The input models preserve
heat provenance and separate internal heat, exported electricity and battery
storage. Duplicate source/accounting identities are rejected. This validation
cannot prove that two differently named source assumptions describe independent
power boundaries; the imported ledger still needs that engineering audit.

Fan curves preserve static/total pressure convention, reference density and RPM.
The initial interpolator rejects extrapolation and reverse-flow requests. Fan-law
scaling requires an explicit RPM range and validity assumptions. This arithmetic
is input preparation, not a CFD fan operating-point result or acoustic prediction.

Keep generator scripts, input manifests and compact acceptance receipts in Git.
Keep native FEM/SIM/CAD files, mesh/result fields, logs and image exports in the
configured NX workspace and retrieve them through existing artifact facilities.
Do not commit raw Siemens documentation, proprietary example binaries or large
result fields to this repository.

## Native lifecycle finding

In the benchmark, meshing a FEM after creating its SIM left the SIM FE-model
occurrence at zero elements while the FEM had 496. `SimSimulation.UpdateFemodel()`
did not synchronize that occurrence. Saving and reopening only the isolated SIM
restored all 496 elements and preserved its thermal step. Pre-solve validation
must compare FEM and SIM occurrence counts and reject stale associations; a
successful FEM mesh call alone is insufficient. Do not silently save or reopen
user documents as a workaround.

The malformed ambient XML preceded the step list. Export 10 is well formed after
repair. Run 02 passed that stage and produced native results; benchmark A
numerical and reopen checks are recorded above.

## Transient benchmark and remaining acceptance

Benchmark C passes its scoped numerical acceptance, recorded in
`tests/simcenter/evidence/acceptance-C.json`. The 10 mm cube uses k = 200 W/(m K),
density 2700 kg/m³, heat capacity 900 J/(kg K), 0.1 W body heat, 20 °C initial and
ambient temperatures, and assumed convection at 10 W/(m² K) on six verified faces.
Convection is solution-level; an empty active-step BC list does not mean it is absent.

Independent refinements were run:

- Time: on the 804-element mesh, the reported integration interval decreased from
  25.3125 to 12.6562 seconds. Worst normalized history error decreased from 1.1296%
  to 0.5768%; the largest change at common times was 0.09216 K.
- Mesh: the separate 1 mm mesh has 5,752 elements and 1,353 nodes. With the same
  41-point schedule, the largest change from the 2 mm mesh was 0.001004 K. Its
  worst analytical-history error was 0.5787%, below the 2% tolerance.
- Energy: 202.5 J was applied. Native cell-temperature extrema bound stored heat,
  avoiding an unweighted nodal average. Including printed-value rounding, the
  worst balance error bound was 0.03884%, below the 0.5% tolerance.

Reproduce the history and energy audit with:

```sh
python examples/simcenter/audit_transient.py <native-receipt.json> \
  --expected-samples 41 --native-run-dir <archive-folder>
```

The audit reports its narrow checks; combined acceptance also requires independent
refinement and artifact identity. Native cube bounds, unchanged saved CAD/FEM/SIM
hashes and the result-bundle hash were verified for the fine-mesh run. Earlier
coarse run 01 failed the temperature criterion and retained only initial/final
fields; it remains preserved as failed numerical evidence.

The internal time-control adapter reads back committed settings, rejects invalid
or excessive time lists, and reports rollback failures. Native testing caught and
fixed integer arguments passed to NX's floating-point scalar setter, then verified
restoration of the original step count. Stored maximum-temperature-change and
minimum-step settings are not claimed as active numerical bounds under the installed
time method. Job exclusion and stale-result tracking still need public integration.

The result reader supports explicit loadcase/iteration selection and paged field/time
metadata. On this solver, physical times occupy separate loadcases; an additional
summary loadcase has no physical time. Generic model/job freshness binding is still
required before exposing a complete engineering-results tool.

NX regenerates input XML during `SimSolution.Solve`. The `solver_manifest` helper
preserves immutable snapshots and compares XML content without comments, retaining
whitespace in property values. Native verification confirmed that the differing
bytes were only the export timestamp comment. Earlier runs without preserved
preflight bytes retain that evidence limitation. This is an isolated job identity
check, not complete cancellation, reconnect recovery or result-freshness enforcement.

Contact benchmark B remains incomplete. The display term “Thermal Coupling” is not
an accepted neutral descriptor in `CreateBcBuilderForSimulationObjectDescriptor`
on this host (NX error 1543292). This lookup failure does not establish that thermal
contact is unavailable. Fan/duct, coupled cooling and complete lifecycle/failure
benchmarks also remain incomplete; no Baldower model is released by these results.

Further native contact inspection tested the shipped command-metadata identifiers
`Interface Resistance`, `Face Contact` and `Thermal Coupling`. All three fail the
current builder with NX 1543292 and the documented legacy creation method with
NX 3520001. Each legacy attempt was rolled back and the simulation-object set was
verified unchanged. The UF solver-language API exposes load/constraint enumeration
but no simulation-object descriptor enumeration in this binding. Discovery reports
this unresolved mapping for v2606; it does not infer licence or module absence.
Evidence: `tests/simcenter/evidence/native-contact-descriptors.json`. A native UI
journal is the next route to identify the actual descriptor and settings.

A subsequent probe used a fresh saved analysis copy, the exact installed solver
label `Simcenter 3D Multiphysics`, and the `Thermal` analysis. The active UF
language and solution language matched. The two command-metadata candidates for
that context, `Thermal Coupling` and `Interface Resistance`, still returned NX
1543292. `Face Contact` is not listed for this plain thermal context. Both builder
attempts rolled back with unchanged simulation-object tags and document modification
flags; the source file hash was preserved. Evidence:
`tests/simcenter/evidence/native-contact-context.json` and reproducible probe
`examples/simcenter/probe_contact_context.py` (requires a fresh destination).
This rules out a mismatched active language in that test. These native descriptor
rejections do not indicate a transport failure. The separate Windows Firewall
prompt for `niece_solver.exe` remains undiagnosed; successful flow runs while it
was present do not establish that all solver communication modes are unaffected.
No firewall or licensing configuration was changed. The updated capability finding
was deployed without restarting NX; the live reload preserved work/display parts
and document modification flags (`native-contact-capability-deployed.json`).

Additional installed command-metadata candidates were probed in that isolated
Thermal SIM. `Advanced Thermal Coupling` and `Convection Coupling` also rejected
their neutral names with NX 1543292. `Radiation Thermal Coupling` initialized
successfully through the same simulation-object builder, exposing two target
sets and view-factor/region-side/overlap controls. It was inspected, destroyed
and rolled back without committing. This demonstrates that the builder path can
resolve at least one coupling descriptor; it does not establish conductive
contact, radiation authoring or numerical correctness. Evidence:
`native-contact-alternative-descriptors.json`; fixture:
`probe_contact_alternative_descriptors.py`. A bounded search of 606 installed
SDK/ThermalFlow source and documentation files found solver help references but
no exact conductive-contact builder example. Benchmark B remains incomplete.

The native journal recorder was then tested: `RecordJournal` and
`StopRecordingJournal` produced a UTF-16 C# journal using the existing language
preference. The manual handoff and return to agent control succeeded, preserving
postview 2 and the active benchmark. However, the visible “Loads and Conditions”
tab exposed no accessibility action, so no contact command was invoked or recorded.
The journal therefore supplies no contact descriptor evidence. No licensing or
journal-language setting was changed. See `tests/simcenter/evidence/native-journal-probe.json`.


## Directional material API groundwork

The installed `PhysicalMaterial.Type.Orthotropic` and `Anisotropic` builders
initialized successfully on an isolated FEM. Native property inspection exposed
three orthotropic conductivity fields and nine anisotropic fields. Builder
availability does not establish solver tensor conventions or orientation.
Evidence: `native-directional-material-builders.json`.

The internal `directional_material.py` adapter creates an orthotropic material
with three positive finite material-axis conductivities, density, heat capacity
and provenance. It uses explicit SI expression units, disables global-library
publication, and checks actual numeric values and units after commit. Failure
rolls back its material transaction. It does not assign collectors, orient
elements or save. This adapter is not yet a public simulation material tool.

Native commit/readback returned conductivities 12, 7 and 0.4 W/(m K), density
1900 kg/m³ and specific heat 900 J/(kg K). The fixture rolled back the temporary
material and verified the material list, modified flags and restored work/display
parts. These are synthetic test properties. Evidence:
`native-orthotropic-material.json`; fixture: `verify_orthotropic_material.py`.
Material-axis assignment, save/reopen persistence, exported tensor interpretation
and directional conduction benchmarks remain required. General anisotropy and
temperature dependence are not implemented by this adapter.

An independent saved clone of the conduction benchmark was then created from
the loaded isolated contact-context SIM. The original conduction SIM had been
renamed in-session; an initial lookup stopped before cloning. The new study's
single solid collector was assigned the synthetic orthotropic material, its
FEM was saved, and a separate SIM copy was exported without solving. Actual XML
contains an `ORTHO` material with X/Y/Z conductivity entries 12000/7000/400 in
the native export representation, and the solid property references its material
ID. Native material readback remains 12/7/0.4 W/(m K); a numerical test must verify
the exporter/solver unit interpretation. Orientation type is 0 with no explicit
coordinate system, so global-axis interpretation is not yet claimed. The export
contains 2658 elements and 756 nodes. Saved backups were retained before material
assignment; other loaded modified flags were preserved. Evidence:
`native-orthotropic-study-prepared.json`, `native-orthotropic-export.json`;
fixtures: `prepare_directional_material_study.py` and
`export_orthotropic_material_study.py`. Solver and save/reopen acceptance remain
pending.

The X-direction orthotropic case subsequently ran through public MCP
prepare/launch, automatic observation after client disconnect, terminal-state
retrieval and verified gate release (`orthotropic-x-thermal-01`). The actual
100 × 10 × 10 mm mesh receives 1 W over all 2658 elements. Native face inspection
verified a connected 100 mm² temperature boundary at X=0, fixed at 20 °C; no
convection or radiation boundary is applied. For uniform internal heating with
the other faces insulated, `ΔTmax = P L / (2 kx A)` gives 41.666667 K at
`kx = 12 W/(m K)`. Native temperatures are 20 to 61.713905 °C: rise error
0.047239 K, or 0.113373%. This supports the X conductivity/unit interpretation
for this benchmark, not arbitrary material frames or Y/Z behavior.

The rounded native energy summary reports 1 W applied and 1 W into sinks; its
separate reported deviation of -0.02027 has no established global/local
interpretation and is not treated as a conservation pass. Input XML content
matched the prepared deck apart from timestamp comments. A native temperature
postview was displayed with document flags preserved. Evidence:
`native-orthotropic-x-comparison.json`, `native-orthotropic-x-cycle.json`,
`native-orthotropic-solve-inputs.json`, `native-orthotropic-visible-result.json`.
Mesh refinement, other directions, explicit rotated frames and save/reopen result
consistency remain required; this is not complete orthotropic acceptance.

The full SIM/FEM unload test exposed a loader defect: with the session's
`FromDirectory` preference, reopening the SIM could not locate its sibling-folder
FEM (native load issue 641044). The SIM remained partially loaded and the error
was reported. `open_document` now temporarily uses the installed `AsSaved` load
method for a fresh native open, restoring the prior preference on success or
failure. Local tests cover restoration in both cases. The verified unmodified
partial SIM was explicitly closed before recovery; no unsaved state was discarded.

After deployment, a full save/close/reopen cycle unloaded both files and restored
all five orthotropic properties, the solid collector assignment, and exactly the
same 20 to 61.713905 °C temperature result. Old SIM/FEM IDs were rejected with
`NX_OBJECT_STALE`; unrelated modified flags were preserved. The reopened contour
is displayed. Evidence: `native-orthotropic-reopen-failure.json`,
`native-orthotropic-saved-path-recovery.json`, `native-orthotropic-reopen.json`.
This completes persistence verification for this specific study; Y/Z, rotated
frames and mesh refinement remain unverified.

An independent rotated-frame study tested the documented Cartesian coordinate
system constructor and solid `material orientation` property. The first attempt
rejected integer Point3d/Vector3d constructor arguments; its frame transaction
rolled back. The existing committed clone was verified and reused with explicit
floating-point arguments, without another clone. Native readback then retained
material X=(0,1,0), Y=(-1,0,0), Z=(0,0,1), and the FEM saved successfully.

However, with the original orientation type 0 retained, the solid-property XML
does not reference this frame. Inspection of orientation/coordinate/transform
records finds only the identity model frame and material-orientation type 0.
This configuration is not accepted as a rotated material case; no solve was
launched. The supported selector semantics and any element-associated alignment
representation still need verification. Evidence: `native-rotated-frame-export.json`
and `native-rotated-orientation-records.json`; fixtures:
`export_rotated_material_study.py`, `continue_rotated_material_study.py`,
`inspect_rotated_deck_orientation.py`. Storing a coordinate-system reference is
insufficient evidence that the solver uses it.

The remaining alignment sections were empty. A bounded native selector probe
then established that value 1 exports `Material Orientation` as Cartesian X/Y
axis vectors plus `Material Orientation Origin`. The exported vectors exactly
match (0,1,0) and (-1,0,0). This is observed v2606 behavior, not an assumed enum
mapping. The internal `material_orientation.py` adapter validates finite,
orthonormal axes, converts native constructor arguments to floats, checks the
current selector/frame before assignment, sets the verified selector and reads
back the committed origin and all three axes. Native replacement/readback/rollback
passed with preserved flags. Evidence: `native-material-orientation-selector-one.json`
and `native-material-frame-adapter.json`.

The rotated study subsequently completed via the public asynchronous solve path
(`orthotropic-rotated-thermal-01`). Its effective conductivity along the bar is
7 W/(m K), giving an analytical rise of 71.428571 K. The result is 20 to
91.474022 °C: rise error 0.045450 K or 0.063631%. The unrotated case rose
41.713905 K. This verifies the tested material-axis swap and exporter/solver
mapping. The rounded native log reports 1 W applied and 1 W rejected. The rotated
temperature view is displayed. Evidence: `native-orthotropic-rotated-comparison.json`,
`native-orthotropic-rotated-cycle.json`, `native-rotated-orthotropic-visible.json`.
Z-axis behavior, rotated save/reopen, mesh convergence and public material/frame
tool registration remain incomplete.

A third independent case uses material X=(0,1,0), Y=(0,0,1), Z=(1,0,0), placing
the 0.4 W/(m K) direction along the bar. The launch fixture verifies the actual
exported frame before calling the solver. With the same 1 W load and dimensions,
the analytical rise is 1250 K; the native result is 1250.049561 K, an error of
0.049561 K or 0.003965%. These high temperatures belong only to an idealized
constant-property numerical test, not a physical PCB or product prediction.
Evidence: `native-orthotropic-z-prepared.json`, `native-orthotropic-z-cycle.json`,
`native-orthotropic-z-comparison.json`.

The third-axis SIM and FEM were then saved and fully unloaded/reopened. All five
material properties, the assignment, selector 1, the explicit three-axis frame
and identical minimum/maximum temperatures survived. Stale IDs were rejected and
unrelated modified flags were preserved. The reopened result is displayed.
Evidence: `native-orthotropic-z-reopen.json`; fixture:
`verify_orthotropic_z_reopen.py`. The three directional checks and this frame
persistence test do not replace mesh refinement, general non-diagonal anisotropy,
temperature dependence or public tool acceptance.

## Interactive result views and images

The `postprocessing` adapter creates a native nodal-temperature postview for an
explicit loadcase/iteration and reads back the field, indices and Celsius unit.
It preserves existing views by rejecting replacement, cleans up a failed creation,
and retains the native result while its view is displayed. A fixed linear Celsius
range is supported; invalid ranges are rejected without changing the legend.

The fine transient benchmark was displayed in the separate Simcenter 3D Pre/Post
window at 2025 s with a 20–40 °C legend. Automatic scaling exaggerated a roughly
0.0055 °C spatial range and produced repeated rounded labels, so fixed scales are
preferable when comparing variants. Numerical values still come from result reads.

Viewport capture and camera inspection now use `Parts.BaseDisplay`, supporting
FEM/SIM documents as well as CAD. A native PNG export from the SIM included the
contour, full legend, time label and axes, without the floating bridge panel.
It returned 2458×1484 pixels for a 1600×1000 request; both sizes and the warning
remain in the receipt. Exact image sizing is not verified on this host. Evidence:
`tests/simcenter/evidence/native-postprocessing.json`.

Contour creation remains an internal adapter. The public `nx_sim_result_inventory`
tool pages native loadcases, iterations, times, units and field names without
unloading the displayed result. It requires an already active SIM and explicitly
reports result freshness as `not_verified`; it does not establish engineering
acceptance or silently activate a document.

The compact agent surface exposes simulation discovery through
`nx_discover_tools(domain="simulation")` and execution through `nx_invoke`.
Native verification used a real MCP stdio session with 13 core tools, followed by
`nx_screenshot` and `nx_download_file(delivery="image")`. The delivered PNG hash
matched the native export. The visible Simcenter contour remained intact after
result inspection. This test used a dedicated Simcenter bridge descriptor and
left the original CAD bridge unchanged.

Reproduce on the NX host with an active SIM containing results and a displayed
contour, using the server's Python environment:

```powershell
python examples/simcenter/verify_stdio.py --workspace <analysis-workspace> `
  --bridge-descriptor <simcenter-bridge.json> --output <new-receipt-folder>
```

The script creates a screenshot and local receipt, not a simulation or solve.
Evidence is in `tests/simcenter/evidence/native-mcp-ui.json`. Public contour
creation, typed view references, result freshness checks and durable view/result
lifetime management remain required for the complete workflow.

The native `select_temperature_iteration` adapter also passed selection readback
at loadcases 0, 20 and 40 in the fine transient benchmark. It retained the existing
result and 20–40 °C legend, rejected index 999 without changing the view, and
restored the original selection. The reproducible native-thread fixture is
`examples/simcenter/verify_view_selection.py`; it requires the explicitly owned
benchmark postview and rejects other documents/views. Evidence is recorded in
`tests/simcenter/evidence/native-view-time-selection.json`. A local failure test
checks restoration after a native setter exception; that failure was injected,
not reproduced in NX. Public exposure still requires ownership and freshness
validation before selecting a result.

Result association inspection now reads `SimResultReference.GetResultFile`, hashes
workspace-scoped files within an explicit byte budget, and reports
`SimSolution.VerifyResults` separately. It does not register results or change
associations. The fine benchmark's 12,542,348-byte bundle was read successfully;
NX reported `ResultsChanged` (2), so current freshness remains unverified despite
the earlier benchmark acceptance. The reason for that native status is unresolved.
Evidence: `tests/simcenter/evidence/native-result-identity.json`; native fixture:
`examples/simcenter/verify_result_identity.py`.

Native testing found that Windows Python reports different `st_ctime` conventions
for path and file-handle metadata. The change-detection guard compares those times
within their respective APIs, while comparing file identity, size and modification
time across both. A regression test covers that distinction. This inspection is
groundwork for model/job revision binding, not a substitute for it.

The saved-revision audit compares an explicit pre-solve dependency snapshot with
both current file hashes and native load/modification flags. Missing or additional
dependencies, unsaved edits, incomplete loading and changed files prevent a match.
It audits the supplied dependency set; full assembly dependency discovery and
durable job binding remain required before claiming complete freshness protection.

Native verification followed `SimPart.FemPart`, `AssociatedCadPart`, `IdealizedPart`
and `MasterCadPart` for the fine benchmark. The three saved CAD/FEM/SIM hashes still
match `fine-solve-01`, but the SIM has unsaved edits, so the audit returns
`revision_mismatch`. It does not save or discard those edits. This finding does
not establish the cause of NX's separate `ResultsChanged` status. Reproduce with
the native-thread fixture `examples/simcenter/verify_revision_audit.py`; evidence
is `tests/simcenter/evidence/native-revision-audit.json`.

### Native fan curve table adapter (NX 2606)

`simcenter/fan_field.py` creates a one-dimensional native field table from the
validated SI fan manifest. `examples/simcenter/verify_fan_field.py` exercised the
deployed adapter in the separate interactive Simcenter session and undid the
probe. Evidence is `tests/simcenter/evidence/native-fan-field.json`.

The installed table API normalized the independent variable to mm³/s without
scaling supplied m³/s values in an initial probe. The adapter explicitly converts
flow to native mm³/s before creation and converts actual readback to SI; it rejects
changed values, cardinality, interpolation or out-of-range settings. The synthetic
0/0.0002/0.0004 m³/s curve read back as 0/200000/400000 mm³/s and reconverted exactly.
Linear interpolation and undefined out-of-range values were verified by property
readback. Interpolator evaluation and solver extrapolation behavior remain untested.

The native runtime has no Pydantic dependency; it revalidates the JSON manifest
before mutation and normalizes numeric values to NX doubles. Pressure convention,
RPM, density, provenance and fan-law limits remain manifest metadata. This adapter
does not attach a fan boundary or establish solver interpretation of that metadata.
The manifest is now retained in indexed native table attributes, with a versioned
header and SHA-256 integrity check. Bounded 200-character ASCII chunks preserve
Unicode provenance through JSON escaping; metadata is limited to 256,000 encoded
bytes. Duplicate field names are rejected case-insensitively before creation.
`verify_fan_manifest.py` verified metadata and unit readback in the interactive
Simcenter session, duplicate rejection, and field-inventory restoration after an
injected post-creation readback failure. Its outer undo also preserved loaded-part
modified flags. Evidence: `tests/simcenter/evidence/native-fan-metadata.json`.
`manifest_persisted=true` means retained on the native object; `saved=false` still
requires saving the SIM for disk persistence.

The table adapter is exposed as `nx_sim_fan_table` and limited to active millimeter
SIM documents. It does not attach a fan boundary or satisfy the fan/duct acceptance
benchmark. `nx_sim_fan_tables` provides read-only, paged inspection of MCP-owned
tables in a loaded SIM. It validates metadata integrity, samples, units and
interpolation; `include_samples=false` keeps responses compact. Both return
`simulation_field` references with session/generation and owner context.

Example creation (IDs and operation IDs must be current/unique):

```json
{"document":"<SIM ID>","name":"Synthetic fan","points":[[0,1],[0.0002,0.5],[0.0004,0]],"pressure_convention":"static","rpm":1000,"reference_density_kg_m3":1.2,"stall_region":"Synthetic; unverified","provenance_kind":"assumed","provenance_source":"Benchmark fixture","operation_id":"<unique operation ID>"}
```

The public creation tool fixes linear interpolation, undefined out-of-range
values and unsupported reverse flow. RPM is curve metadata; it does not set a
boundary speed. Public RPM scaling and boundary assignment remain pending.
`verify_fan_tables_mcp.py` exercised creation, full and compact inventory,
operation replay and duplicate-name rejection through an external MCP client
connected to the dedicated Simcenter UI bridge. Replay returned the same field
reference and the inventory gained exactly one table. Other document modified
flags were preserved and the previous active document restored. Evidence:
`tests/simcenter/evidence/native-fan-tables-mcp.json`. This fixture left the new
table unsaved in its isolated SIM; the separate lifecycle test below covers
native disk persistence.

`verify_fan_reopen.py` created a separate flow benchmark SIM, saved a synthetic
fan table, closed only that saved SIM and reopened it. Its metadata (including
multi-chunk Unicode provenance and scaling limits), three flow samples and three
pressure samples matched the pre-save values exactly. The saved file checksum
was unchanged. NX nevertheless reported the reopened SIM as modified; this test
does not establish result freshness. Existing document modified flags and the
previous work/display documents were preserved. Evidence:
`tests/simcenter/evidence/native-fan-reopen.json`. The test does not establish
persistence of a fan boundary association or solver settings.

### Simulation object inventory

`nx_sim_objects(document, offset=0, limit=20, include_properties=false,
include_targets=false)` pages the active SIM's `SimulationObjects` collection.
It is separate from loads and constraints and returns `simulation_object`
references and native descriptors. Inlet rows include current mode, typed fan
field reference and scale. Expanded properties report actual native values and
units; expanded target sets retain unsupported-target notices and explicitly
truncate beyond 100 members per set. It does not infer physical face orientation
or establish result freshness.

`verify_sim_objects_mcp.py` verified one-row paging, Inlet and Opening descriptors,
mode-5/scale-1 fan binding, expanded properties and nonempty inlet targets on the
isolated native duct SIM. All loaded-document modified flags were preserved and
the previous active document restored. Evidence:
`tests/simcenter/evidence/native-sim-objects-mcp.json`.

### Native static fan assignment adapter

`simcenter/fan_boundary.py` assigns an audited MCP fan table to an existing native
`Inlet` in the active NX MULTIPHYSICS Flow SIM. It requires static-pressure metadata,
sets mode 5 and scale 1, and reads back the field association. It preserves existing
orientation and pressure-reference settings, does not assign motor heat, and marks
results stale. Total-pressure and coupled assignment paths remain unsupported by
this adapter pending tests. It is exposed through `nx_sim_assign_fan(document, inlet, field)`. The adapter
checks the shared solver-idle guard before setting an undo mark.

`verify_fan_assignment.py` checked that no solver/translator processes were running,
then tested assignment in the isolated duct SIM. An injected readback failure after
switching to a different curve restored the preceding binding and field/expression
inventories. An outer undo restored the original duct binding and field inventory;
all loaded-document modified flags were preserved. No files were saved and no
solver was launched. Evidence: `tests/simcenter/evidence/native-static-fan-assignment.json`.
This verifies assignment and recovery, not a new fan/duct numerical acceptance run.

`simcenter/solver_guard.py` provides a conservative host-wide process check shared
by fan assignment and transient-step setup. It uses a bounded, noninteractive
query for known solver/translator process names. Running processes produce
`NX_SIM_SOLVER_BUSY`; failed queries, timeouts and malformed output produce
`NX_SIM_SOLVER_STATE_UNKNOWN`. Both reject mutation and omit raw process output.
No processes are stopped and no licensing information is read or changed.
The check is a point-in-time snapshot, not an atomic lock against a subsequent
manual solver launch. Native idle-path assignment and rollback passed again:
`tests/simcenter/evidence/native-guarded-fan-assignment.json`. Busy/error/timeout
branches have local seam tests; they have not been exercised against a live
running solver in this guard test.

The public `nx_sim_assign_fan` requires current `simulation_object` and
`simulation_field` IDs owned by the selected active SIM. It returns typed
references and the committed mode/scale; raw native tags are not selection handles.
`verify_assign_fan_mcp.py` verified assignment, inventory readback, replay of the
same operation ID and wrong-reference-kind rejection through MCP. Its native outer
checkpoint restored the original duct fan binding, field inventory and all
loaded-document modified flags. Evidence:
`tests/simcenter/evidence/native-assign-fan-mcp.json`. No solve or save was performed;
this proves public authoring and recovery, not a new numerical benchmark.

### Fan inlet export and first native solve

`verify_fan_attachment.py` verified that the inlet's `Fan Curve` wrapper references
the created table at scale 1.0, then undid the probe. Property descriptors and the
string-choice query returned no mode labels. A checkpointed candidate-mode export
and a subsequent bounded solve identified inlet `Mode Option = 5`: the native
translator labels the inlet `Fan Curve`. The exported table preserves linear /
undefined-outside settings, converts 0.0002 m³/s to 200000 mm³/s and 0.5 Pa to
0.0005 mN/mm². These are native export observations, not a claim that all fan
boundary options are supported.

`prepare_cavity_fan.py` and `solve_cavity_fan.py` reproduce the isolated synthetic
configuration and persistent job `cavity-fan-solve-01`. It completed in 25 seconds;
mass imbalance was 0.01818% and momentum imbalance 0.008471%. It reported an inlet
flow of 0.0004 m³/s, the curve's free-flow endpoint, but the fan summary reported
Delta P -0.02586 in native pressure units and zero loss coefficient. This does not
agree with the specified curve and is explicitly rejected pending pressure-reference
and boundary-interpretation investigation. The solution's absolute pressure default
was 101351 Pa while specified inlet/opening pressure was 101325 Pa; causality has
not yet been established. Do not use this run as benchmark D acceptance.

`tests/simcenter/evidence/native-fan-mode.json` records observations and hashes.
Raw log/XML/MAP/result files are retained outside Git under the existing analysis
artifact policy. No heating, restriction comparison, or mesh-sensitivity acceptance
has been demonstrated for this fan model. The saved isolated cavity SIM currently
contains this synthetic fan configuration; the prior velocity runs are retained in
separate evidence directories.

### Controlled pressure-reference comparison

`set_fan_reference_pressure.py` changes only the isolated solution's absolute
pressure from 101351 Pa to 101325 Pa, verifies expression/unit readback and exports
101.325 in solver pressure units. `solve_cavity_fan_equal_pressure.py` launches the
separately identified comparison `cavity-fan-solve-02`. The original run remains
preserved. The second run completed in 24 seconds with reported flow 0.0003497 m³/s
and fan Delta P 0.1258 Pa after native-unit conversion. The supplied curve gives
0.12575 Pa at that flow, a 0.00005 Pa difference (about 0.04%, within printed log
precision). Mass imbalance was 0.08802%; momentum imbalance was 0.02175%.

This controlled comparison resolves the earlier numerical curve mismatch for the
fixture. It does not independently establish static-versus-total pressure meaning,
mesh convergence, or response to increased restriction. Evidence and hashes are in
`tests/simcenter/evidence/native-fan-pressure-reference.json`. The saved fixture now
uses the equalized reference. No production model was changed.

`simcenter/fan_results.py` provides a sidecar consistency audit of SI operating
points against the exact run's fan curve. It requires explicit pressure convention
and tolerances, rejects extrapolation/non-finite values and separates this check
from full engineering acceptance. The evidence includes both a conditional static
comparison and a non-accepted audit with pressure convention unverified. Tolerance
for this printed-log comparison is 0.001 Pa plus 1% of expected pressure, allowing
rounding while rejecting the previous 25.86 Pa discrepancy. Native field extraction
at higher precision and independent pressure convention checks remain required.

### Native restriction comparison and head-loss adapter

The installed `Head Loss` modeling-object table exposes coefficient, pressure-drop /
velocity ratio and orifice properties. `set_duct_head_loss.py` attaches a coefficient
of 2 to the isolated outlet with native defaults `Type = 0` and `Proportional to = 0`;
coefficient and table association are read back and the value is verified in the
export. The original failed unit-name lookup was rolled back without saving; the
working path reuses the native coefficient property's unit object.

`solve_cavity_fan_restricted.py` runs persistent job `cavity-fan-solve-03` with the
same geometry, mesh, air properties, fan curve and pressure reference as run 02.
Flow decreased from 0.0003497 to 0.0002217 m³/s (36.60%). Reported fan pressure rose
from 0.1258 to 0.4458 Pa; the supplied curve predicts 0.44575 Pa. Mass imbalance was
0.03567%, momentum imbalance 0.02177%, runtime 24 seconds. This demonstrates native
restriction response; it is not mesh-converged benchmark D acceptance. The precise
coefficient convention and static/total pressure interpretation remain unverified.

`simcenter/head_loss.py` provides the reusable internal authoring adapter, with
owner/work-document checks, finite nonnegative coefficient validation, duplicate
assignment rejection, native readback and verified table/association rollback.
`verify_head_loss.py` exercised the deployed adapter and duplicate rejection, then
verified restoration of the isolated inlet and table inventory. Native null units
for this coefficient are returned as `dimensionless`. This remains an internal
adapter, not a published generic porous-region or arbitrary pressure-loss API.
Evidence and artifact hashes: `tests/simcenter/evidence/native-fan-restriction.json`.
The saved cavity fixture retains the K=2 outlet restriction; the adapter verification
left no additional inlet restriction. All native result bundles remain outside Git.

### Native fluid mesh refinement

`verify_fluid_remesh.py` edited the existing linear fluid tetrahedral mesh from
5 mm to 3 mm: 3308 elements / 939 nodes became 13397 elements / 3200 nodes. The
probe verified type/size readback and restored the baseline mesh counts with undo.
`refine_fluid_mesh.py` then saved that refinement in the isolated benchmark, after
backing up its native FEM/SIM files, invalidated cached part references, and reopened
the saved SIM. Boundary property readback and target counts matched the snapshot.
This snapshot comparison is not a geometric proof of target identity.

The first export validator incorrectly counted `ElementList/Set` groups as elements.
`verify_refined_export.py` corrected this by counting `ElementList/Set/E` and
`NodeList/N`, verifying 13397 elements / 3200 nodes against the current FEM.
`simcenter/solver_log.py` now exposes these grouped mesh counts with a regression
test for multiple element sets. The original failed receipt remains as evidence;
the subsequent verification is `tests/simcenter/evidence/native-fluid-refinement.json`.

The saved cavity model now has the 3 mm mesh and K=2 outlet restriction. Prior
results belong to the old mesh and must not be reused. No refined solve or
mesh-sensitivity acceptance is established by these operations.

### First fan mesh-sensitivity comparison

`solve_cavity_fan_refined.py` checks current FEM and exported counts before submitting
persistent job `cavity-fan-solve-04`. The 3 mm mesh (13397 elements, 3200 nodes)
completed in 26 seconds. Flow was 0.0002119 m³/s versus 0.0002217 m³/s on the 5 mm
mesh: a 4.42% reduction. Reported fan pressure rose to 0.4703 Pa. Mass imbalance
was 0.07751% and momentum imbalance 0.007027%. This two-mesh comparison does not
establish mesh convergence; finer refinement and pressure-convention checks remain.
Evidence: `tests/simcenter/evidence/native-fan-mesh-comparison.json`.

`parse_native_fan_summary` in `simcenter/fan_results.py` now extracts the observed
2606 fan operating-point and boundary volume/mass flow tables into SI values.
It requires caller-verified pressure units, retains signed inflow/outflow and the
separately printed mass values, rejects duplicate names/multiple summaries and
unsupported layouts, and labels pressure convention unverified. It has been exercised
against both native comparison logs as well as unit/sign/ambiguity regression tests.
These rounded log summaries use display names only; they do not replace stable
native result references, field extraction, or complete numerical acceptance.

### 2 mm fan mesh and native pressure extraction

`refine_fluid_mesh_2mm.py` saves a second refinement with native backups, part-reference
invalidation, SIM reopen and boundary/export readback. Its 44061 elements and 9474
nodes match the exported input. `solve_cavity_fan_2mm.py` launches the separately
identified `cavity-fan-solve-05`. It completed in 32 seconds. Flow was 0.0002016 m³/s,
4.86% below the 3 mm run. Mass imbalance was 0.07659%, momentum imbalance 0.01569%.
The continuing mesh sensitivity does not establish convergence; finer resolution
and near-wall/profile inspection are required before acceptance.

Native inventory exposes `Velocity - Element-Nodal`, `Temperature - Element-Nodal`,
`Pressure - Element-Nodal` and `Total Pressure - Element-Nodal`. The internal
`simcenter/flow_results.py` adapter extracts either pressure field with explicit Pa
units, native unit readback, finite-extrema checks and native location indices.
`verify_flow_pressure.py` exercised the deployed adapter: pressure ranged from
0.27164799 to 0.50690663 Pa; total pressure from 0.37782454 to 0.65229744 Pa. Native
result node count was 9474. These values use the solution pressure reference and
are not absolute atmospheric pressure. Extrema alone do not identify the inlet
fan pressure convention. Native indices apply only to that result revision, and
freshness remains a separate audit. This adapter is not yet exposed as a public tool.
Evidence: `tests/simcenter/evidence/native-fan-2mm-pressure.json`.

### Native pressure convention and boundary diagnostics

`verify_flow_samples.py` reads pressure, total pressure and speed at five nearest
mesh-node locations using one explicitly identified incident element. Actual/requested
coordinates and native indices are retained. All five samples satisfy
p_total - p = rho*v²/2 using the committed 1.2 kg/m³ fluid assumption, within 1e-6 Pa
plus 1e-5 relative tolerance. `audit_pressure_decomposition` implements this narrow
field-consistency check; it does not establish convergence or absolute pressure.

`verify_flow_boundary_integrals.py` maps exported boundary element labels to native
result elements, identifies triangular vertices on each expected end plane, rejects
duplicate facets, and verifies 400 mm² per boundary (248 triangles). Linear integration
of recovered element-nodal fields gives inlet mean pressure 0.49604793 Pa and total
pressure 0.64819513 Pa. The curve at the reported solver flow predicts 0.496 Pa.
This supports a static-pressure-rise interpretation for the tested inlet mode 5,
relative to the equalized ambient reference; it does not establish support for
applying total-pressure fan curves through that mode.

Recovered inlet/outlet volume integrals are 0.00020141255 and 0.00020077840 m³/s;
these differ from the solver's conservative flux summary and must not replace it.
A nearest wall-node sample reports nonzero recovered speed. This is not, by itself,
evidence that the wall condition failed; recovery and boundary-value interpretation
need further inspection. The near-wall requested point selected the same wall node,
which the receipt makes explicit. These diagnostics remain benchmark-specific
scripts, not a public general field-sampling or boundary-integration tool.
Evidence: `tests/simcenter/evidence/native-fan-pressure-convention.json`.

### Native boundary-layer controls

The installed `MeshControlCollection.CreateBuilder` supports `Types.BoundaryLayers`,
first-layer thickness expressions, growth rate and layer count. The internal
`simcenter/boundary_layers.py` adapter was deployed and natively exercised by
`verify_boundary_layers.py`: four longitudinal duct wall faces, eight layers,
0.1 mm first layer, growth rate 1.2. A reopened control builder confirmed these
settings and exactly the requested wall tags; the outer probe verified restoration
of the original control inventory afterward.

Wall faces belong in `MeshControlBuilder.Selection`. Setting them through
`BlTargetSelection` produced a control with empty readback selections in an earlier
probe. With correct primary selection, `BlTargetSelection` contains one inferred
body, not the wall list. The adapter checks primary wall selection explicitly.
`BlDimension` is an integer in the Python binding; assigning the similarly named
BLType enum failed. The adapter preserves the verified native default (0), without
inventing enum semantics. First-layer units are checked as millimeters.

This internal adapter currently requires an active millimeter FEM with no existing
mesh controls, validates bounded layer count and finite dimensions/growth, rejects
duplicate/foreign selections, and verifies rollback on authoring failure. It creates
a control only; no layered mesh has yet been generated or numerically validated.
The hybrid mesher was inspected but not committed. Evidence:
`tests/simcenter/evidence/native-boundary-layer-control.json`. The saved 2 mm cavity
FEM is unchanged by these disposable tests.

### Native layered mesh generation and persistence

`verify_layered_mesh.py` applies the verified wall control and remeshes the existing
2 mm core, checks native element quality/material assignment, then restores the
previous mesh and controls. It generated 97918 elements / 39306 nodes in two meshes.
Native connectivity counted 36222 four-node elements and 61696 six-node elements.
The active quality checks reported no errors or warnings across all 97918 elements;
this is scoped to those checks and their current thresholds. The `Fluid(1)` collector
retained explicit `Benchmark constant air` with the same density, viscosity,
conductivity and specific heat.

`save_layered_mesh.py` persisted that configuration after backing up the isolated
FEM/SIM, invalidated old part references, reopened the SIM and verified boundary
property/target-count snapshots. Exported counts match the FEM; native input labels
the element sets `TET4 Fluid` (36222) and `WEDGE6 Fluid` (61696), both referencing the
same physical property. At this checkpoint the saved fixture contained this layered mesh; previous results
were stale. A later refinement is recorded below. The original receipt's nested `layer_control` values describe initial
control creation, before meshing. The reproducible script now labels that snapshot
explicitly to avoid confusing it with final mesh state.

Evidence: `tests/simcenter/evidence/native-layered-mesh.json`. Layer thickness/shape
distribution and a layered solve were still pending at this checkpoint; subsequent
observations are recorded below.

### First layered fan solve

`solve_cavity_fan_layered.py` verifies current FEM/export counts and both TET4/WEDGE6
sets before persistent job `cavity-fan-solve-06`. It completed in 49 seconds. Reported
flow was 0.0001899 m³/s, 5.80% below the uniform 2 mm result; mass imbalance was
0.1712% and momentum imbalance 0.003234%. The change confirms mesh sensitivity;
a comparison between layered meshes is still required for convergence acceptance.

Independent inspection of exported wedge coordinates in a central wall strip found
levels near the requested progression 0, 0.1, 0.22, 0.364, 0.5368, 0.74416, 0.992992,
1.291590 and 1.649908 mm, with local variation retained in the evidence. This checks
only that sampled strip, not every layer column or corner.

The same native nearest-node sampling fixture returned wall-node speed
0.00037946 m/s at [81,1,11] mm versus 0.47129232 m/s on the uniform mesh. The near-wall
request now selects [81,1.992992,11] mm (0.34615794 m/s), rather than the wall node.
This supports improved near-wall resolution; recovered nodal values are still not
identical to imposed boundary values or conservative face fluxes. Native diagnostics,
layer-coordinate observations, result hashes and job state are in
`tests/simcenter/evidence/native-layered-fan-solve.json`. No manufacturing/acoustic or full benchmark acceptance is implied by this completed
solve. The following refinement supersedes the saved mesh.

### Layered core refinement and result identity

`refine_layered_mesh.py` reduced core size from 2 to 1.5 mm while preserving the
eight wall layers, 0.1 mm first height, 1.2 growth and four selected walls. The
saved/reopened FEM and exported deck contain 186765 elements and 71748 nodes:
77133 TET4 Fluid and 109632 WEDGE6 Fluid. Native active quality checks reported
zero errors and warnings; boundary and material readback remained unchanged.

`solve_cavity_fan_layered_refined.py` submitted persistent job
`cavity-fan-solve-07` once. It completed in 71 seconds with inlet flow
0.0001913 m³/s and fan pressure rise 0.5214 Pa. Flow increased 0.7372% from
the previous layered mesh, but native mass imbalance increased to 0.5464%
(momentum imbalance 0.0278%). This is not mesh-convergence or benchmark D
acceptance. Wall-layer refinement and stronger numerical balance checks remain
necessary. Immutable output hashes and the reconciled job are recorded in
`tests/simcenter/evidence/native-layered-refined-fan-solve.json`; large native
outputs remain outside Git.

The public read-only `nx_sim_result_identity` tool takes an active SIM document
ID and a positive total `maximum_bytes` budget (default 1 GiB). It returns
workspace-scoped associated file paths, byte sizes, SHA256 hashes and NX's
verification status. Missing associations/files, changing files and exceeded
budgets are errors. It neither saves nor changes result associations. File
identity alone cannot prove that results match current model inputs.

A real MCP stdio → descriptor bridge → Simcenter UI test retrieved the
46367644-byte run-07 result bundle with SHA256
`59a84eed4af427c0d85646eb2b9f853f9f1ff34f6804f2f3df8951a00d5d37d4`.
NX reported `ResultsChanged` (2); the tool retains `result_freshness: not_verified`
and `engineering_accepted: false`. A zero budget returned `NX_INVALID_ARGUMENT`
with mutation outcome `not_started`. Evidence:
`tests/simcenter/evidence/native-result-identity-mcp.json`. The host-specific
read-only reproduction is `examples/simcenter/verify_result_identity_mcp.py`.
Use this after `nx_sim_result_inventory` and bind its hashes to a pre-solve
dependency manifest and durable job; that complete public workflow is still pending.

### Flow convergence controls

Native inspection found RMS convergence mode 1 with residual 0.0002, while the
boolean `Global Flow Imbalance Fraction Option` was disabled. The internal
`flow_controls.configure_convergence` adapter now validates finite fractions and
a bounded integer iteration limit, requires the verified RMS mode, reads back
all assignments, and verifies restoration after a failed mutation. It does not
save or solve. It is exposed as `nx_sim_flow_convergence`, requiring an active
SIM document ID and explicit residual, flow-imbalance fraction and iteration limit.
Do not change controls while a solver job is running; automated job-state gating
is still part of the pending job-manager work.

`verify_flow_controls.py` natively assigned residual 1e-6, flow-imbalance fraction
0.001 and iteration limit 1000, verified a repeated assignment made no change,
and restored all parameter-table properties with explicit undo.
`set_duct_convergence.py` then backed up and saved the isolated duct SIM and
verified those values in native solver export. Earlier results now require
revalidation. Evidence: `tests/simcenter/evidence/native-flow-convergence-controls.json`.

`solve_cavity_fan_tight_convergence.py` records job `cavity-fan-solve-08` before
launch and checks both native controls and exported values, in addition to the
existing mesh/fan/restriction checks. It completed in 105 seconds. The native log
confirmed RMS residual limit 1e-6. Reported mass imbalance decreased from 0.5464%
to 0.008865%, and momentum imbalance was 0.0000226%. Inlet flow was
0.0001912 m³/s (0.0523% below run 07) and fan pressure rise 0.5221 Pa. No warning
or error lines were found in that log. This improves numerical balance on the
same mesh; complete mesh convergence and benchmark D acceptance remain pending.
Evidence: `tests/simcenter/evidence/native-tight-convergence-fan-solve.json`.

Real MCP testing of `nx_sim_flow_convergence` verified that repeating current
settings returns `changed: false`, and a zero residual is rejected with
`NX_INVALID_ARGUMENT`. Preflight errors explicitly report `not_started`; an
earlier native receipt reported `unknown` and prompted this correction. Native
assignment/undo tests exercise changed values separately from the no-op transport
check. Evidence: `tests/simcenter/evidence/native-flow-convergence-mcp.json`.

### Persistent job records

The internal `jobs.JobStore` uses an immutable configuration manifest and
append-only, hash-linked state revisions inside a validated workspace folder.
Reservation uses exclusive directory creation; each state revision uses exclusive
file creation and file flush/fsync. Competing transitions require the same expected
revision, so only one writer can claim the next launch intent. A terminal identity
is never reused, and conflicting manifests under one ID are rejected.

The lifecycle is `accepted` → `launch_requested` → `running` → `solver_exited`
→ `completed`, with explicit failed/cancelled paths. These are recorded caller
observations, not automatic process discovery. Even a completed record does not
assert numerical convergence or result validity. Callers must durably record
launch intent before invoking NX and must not replay that call after an uncertain
response. Incomplete or inconsistent records return `unknown`, preserve the
evidence and prohibit further automatic transitions. There is no stale-lock
expiry, implicit deletion, automatic recovery, or power-loss durability claim
for filesystem directory entries.

Local tests exercise competing writers, configuration conflicts, interrupted
request/state writes, broken state chains and reconnect semantics. On the actual
Windows host, `verify_job_store.py` was called through separate bridge clients:
the second call returned the identical launch-intent record, and conflicting
inputs were rejected. `verify_job_interruption.py` retained an intentionally
truncated record in its own disposable folder; inspection returned unknown and
a new launch transition was rejected. These fixtures launch no solver and do
not simulate an actual solver transport interruption. Evidence:
`tests/simcenter/evidence/native-job-store.json`.

The store is deployed but not yet connected to the public solve/status/cancel
workflow. Earlier benchmark jobs use their original receipts; run 09 below uses the new store. Process identity,
log observation, safe cancellation, input/result binding and a real interrupted
solve remain required before full benchmark F acceptance.

### Visible pressure contours

`nx_sim_show_pressure(document, field="pressure", loadcase_index=0,
iteration_index=0, name="MCP pressure")` creates a native Pa contour in the
interactive Simcenter viewport. `total_pressure` selects that field instead.
The adapter reads back field, units and indices, retains results used by views,
and preserves existing views in the selected document. It neither solves nor
certifies freshness. `nx_screenshot` plus image delivery retrieves the viewport.

The public MCP static-pressure test verified creation, replay, invalid-index
rejection and checksum-matched inline PNG delivery. Visual inspection showed the
duct contour and Pa legend; the title overlaps part of the geometry, so framing
is not presentation-ready. NX returned 2458×1484 instead of requested 1600×1000,
which remains explicitly warned. Evidence:
`tests/simcenter/evidence/native-pressure-postview-mcp.json`.

NX reused postview IDs across SIM documents. Retained result handles now have
unique keys rather than overwriting one another by view ID. The adapter returns
`postview_owner` and documents the document-local lifetime of IDs. Native thermal
and pressure creation after this fix preserved previous handles and existing
views, leaving pressure displayed. Evidence:
`tests/simcenter/evidence/native-cross-document-postviews.json`. Total-pressure
contour rendering has now been natively exercised through MCP. Its first test
revealed that `CreatePostviewForResult(..., overlay=false, ...)` replaced existing
views. The preservation check caught this and returned partial failure when the
old main view could not be restored. No CAD or solver data was changed, but the
old views were lost; a static view was subsequently recreated.

A targeted native probe isolated view creation as the cause: result acquisition
kept the original view, while overlay creation retained both old and new IDs.
The adapter now uses overlay mode when views already exist. A new public operation
successfully created the total-pressure contour with views 5 and 6 preserved,
verified Pa/field/index readback, replay and invalid-index handling, and retrieved
a checksum-matched PNG. Visual inspection confirmed the total-pressure legend.
Native evidence: `native-postview-failure-state.json`, `native-postview-overlay-probe.json`
and `native-total-pressure-postview-mcp.json` under `tests/simcenter/evidence`.
`verify_pressure_postview_mcp.py --field total_pressure --revision 02` records the
successful test. The currently visible contour is total pressure; freshness remains
unverified and exact screenshot resolution/framing limitations remain.

A follow-up ownership inspection found three visible postviews with distinct
`SolutionResult` tags and null `Solution` properties. Do not use that property to
infer the active solution or reuse a displayed result. The existing acquisition
path creates a separate result handle and cleans up only that handle.
`verify_result_read_preserves_views.py` verified that successful pressure extraction
and an invalid-loadcase failure preserved all three view IDs, their native result
tags and fields, and the main view. Evidence:
`native-result-ownership-inspection.json` and `native-result-read-preserves-views.json`
under `tests/simcenter/evidence`. This is scoped cleanup evidence, not a proof of
result freshness or every result-sharing scenario.

### Public pressure extrema

`nx_sim_pressure_result(document, field="pressure", loadcase_index=0,
iteration_index=0)` exposes the native element-nodal pressure adapter.
`field="total_pressure"` selects total pressure. Both return Pa extrema,
native location IDs/sub-IDs and the result node count. Location IDs are not
geometry references. Pressure remains relative to the native solution reference;
the tool does not invent an absolute/gauge interpretation or infer result freshness.

`verify_pressure_result_mcp.py` read both fields from the existing isolated duct
result, rejected an invalid loadcase index, preserved loaded-document modified
flags and restored the previous active analysis. Evidence:
`tests/simcenter/evidence/native-pressure-result-mcp.json`. No solve, mesh change or
numerical acceptance claim was made. The selected result may be stale relative
to the live model and is explicitly returned as `result_freshness=not_verified`.

### Bounded log reader

`simcenter/log_reader.py` reads 256..65536 bytes per request using raw byte
cursors aligned to newlines. Partial trailing lines are held until completed;
replacement identity, truncation and unaligned cursors are checked. Lines matching
licensing/credential keywords are omitted before return. This is limited keyword
redaction, not a comprehensive secret scanner. UTF-8 decoding uses replacement
for invalid bytes. A line larger than the requested budget is rejected explicitly.
File IDs detect replacement, not every in-place rewrite; excerpts do not establish
immutable results or convergence.

`verify_log_reader.py` read consecutive 1024-byte-budget pages from the existing
Windows flow solver log, returning byte ranges 0..963 and 963..1899 and preserving
all loaded-document modified flags. Evidence:
`tests/simcenter/evidence/native-log-pages.json`. Local tests cover append/partial
line behavior, credential-line omission, stale cursors and workspace escape.
The public `nx_sim_job_log` now restricts selection to a simple `.log` basename
inside the selected job's isolated output directory. It verifies the permanent
output owner against the job ID, job directory and immutable request checksum.
Unbound/conflicting output ownership, unknown history and resolved paths outside
the owned directory are rejected. The caller supplies `job_id`, `log_name` and,
where needed, `job_folder`; continue with the returned `next_offset` and
`file_identity`. Missing logs produce an explicit availability error.

`verify_job_log_mcp.py` verified two consecutive pages against the existing native
flow job, traversal rejection, incorrect file-identity rejection, and unchanged
persisted job fields and document flags. Evidence:
`tests/simcenter/evidence/native-job-log-mcp.json`. Output-owner conflict/corruption
checks have local filesystem tests. This tool still requires a responsive bridge;
it does not provide independent monitoring while a native call blocks the UI.

`nx_sim_job_logs(job_id, job_folder, offset=0, limit=20)` discovers log basenames
before reading. It uses the same verified output-owner check and returns sizes,
modification times and file identities. Direct ASCII log files only are listed;
symlinks and Windows device names are excluded. Reads also reject device names.
The scan rejects directories exceeding 4096 entries. Listing pages reflect a live
rescan, not an immutable snapshot; refresh if files change between pages.

The extended `verify_job_log_mcp.py` successfully discovered the existing Windows
flow log and used its returned identity for bounded reads. Job records and
loaded-document modified flags remained unchanged. Evidence:
`tests/simcenter/evidence/native-job-log-catalog-mcp.json`. Local tests additionally
cover pagination, uppercase extensions, symlink exclusion and device rejection.

### Process bindings across job history

Job inspection now derives `process_binding_evidence` and its source revision
from the verified state chain. An update without process-binding fields preserves
the preceding binding for later observation. An explicit malformed replacement
is retained and rejected by the observer; it never silently revives an older
identity. Full PID/creation-time/executable identity validation still applies.
The observer does not change job state or infer numerical success from process exit.

Local tests cover reconnect after an unrelated record and malformed replacement.
`verify_job_binding_history.py` read the existing `isolated-flow-01` history on
Windows, observed its recorded process identities and verified that job records
and loaded-document modified flags were unchanged. Evidence:
`tests/simcenter/evidence/native-job-binding-history.json`. No solver was launched.

### Persistent native launch verification

`launch.launch_once` claims a durable `launch_requested` revision before invoking
the native callback. A callback return produces `launch_returned`, which does not
claim a running process. Exceptions produce `launch_uncertain`, since a solver
may already have started. Reconnects return either state without invoking the
callback again. Failed intent persistence prevents the callback entirely. These
additional states can transition to observed running/exit/failure states; neither
allows another launch under the same identity. Cross-job output/session gating
is not implemented by this wrapper.

If the callback returns but writing its observation fails (including an invalid
readback payload), the wrapper raises `NX_SIM_LAUNCH_UNCERTAIN` with the job ID,
`api_returned=true` and `observation_persisted=false`. The earlier intent remains
reserved; a reconnect must inspect it instead of invoking the callback again.
`verify_launch_observation_failure.py` verified that behavior using a real Windows
job directory and an injected observation-write failure. Its synthetic callback
ran once, and reopening the job store returned `launch_requested` without a second
callback. Evidence: `tests/simcenter/evidence/host-launch-observation-failure.json`.
This is a persistence fault test, not a live solver-interruption acceptance test.

`solve_cavity_fan_persistent.py` exercised the wrapper in the actual Simcenter UI
with job `cavity-fan-solve-09`, preserving the pre-launch XML. Two separate bridge
client reconnects returned the identical revision-2 launch record; the second
followed observation of a live native solver process. No second launch claim was
created. The solve completed in 108 seconds with inlet flow 0.0001912 m³/s, mass
imbalance 0.008865% and momentum imbalance 0.0000226%, reproducing run 08.

Fixture-specific reconciliation verified disappearance of the observed PID,
fresh log/result timestamps, the completion footer, and unchanged canonical XML
input content before recording `solver_exited` at revision 3. The result SHA256
is `6f076a9cdd65a6a25a4ebe5a3a4b97312f20041957f108adfa0edb14a46a95d8`,
identical to run 08. Raw export bytes differ because export metadata changed;
canonical content identity remains
`83d3c9b323ff8ac9cf0a4723e833ec9f1dba1b59ce02c704ca8b2c9649ee55da`.
Evidence: `tests/simcenter/evidence/native-persistent-launch.json`.

This validates native launch/reconnect behavior in an isolated fixture, not a
forced transport interruption, bridge restart, cancellation, general process
monitor or full benchmark F. The public solve/status/cancel workflow remains
under implementation.

### Public job inspection

`nx_sim_job_status(job_id, job_folder="simcenter-jobs")` reads the durable job
record. Its compact default returns state, revision, request hash, observation
time and retry prohibition. `include_manifest=true` and `include_evidence=true`
opt into the larger configuration and terminal evidence. The result explicitly
reports `observation_kind: persisted_record` and `live_process_state: not_checked`;
it must not be presented as a fresh process observation. It does not launch,
retry, save, cancel or modify the job. This bridge-routed inspection still needs
a responsive bridge; independent background status delivery remains pending.

The native MCP verification (`verify_job_status_mcp.py`) checked run 09 in
`ui-benchmarks/D-cavity-documents-20260908-r2/jobs`: compact status returned
`solver_exited`, revision 3, while expanded evidence returned the verified result
hash. The interrupted fixture returned `unknown` with relaunch prohibited. A
missing job returned `NX_SIM_JOB_NOT_FOUND`; an out-of-workspace folder was
rejected without mutation (currently through the common `NX_API_ERROR` wrapper).
Evidence: `tests/simcenter/evidence/native-job-status-mcp.json`.

Older benchmark receipts are not automatically imported into this store. Use
the job folder associated with the launch; the optional folder parameter is
workspace scoped and does not search arbitrary directories. Public launch,
process monitoring, cancellation and validated result binding remain unfinished.

### Windows process identity

The internal `process_identity` observer opens a Windows process handle with
limited query/synchronization rights and reads creation FILETIME, executable
path and handle liveness. It does not read command lines/environment, adjust
privileges, or terminate anything. A PID alone is insufficient: correlation
requires the previously observed creation time and executable path. Creation
times are decimal strings to preserve the full 100 ns FILETIME value. Missing
PIDs, unavailable observations and changed identities are distinct outcomes;
none establishes solver success.

Native testing identified the running Simcenter UI as
`Designcenter2606/NXBIN/simcenter3d.exe`, PID 6584. Repeated observations matched
a disposable Python child. A synthetic changed creation time was rejected.
The initial post-exit test exposed Windows error 31 from image-path lookup on
a terminated process whose handle remained retained. The corrected observer
uses the same handle's signaled state, creation time and exit code. When the
image path is unavailable after confirmed exit, correlation can use the already
recorded PID and creation time; a running process without a readable image path
stays unknown. The corrected native test returned `same_process_exited` with
exit code zero while retaining `solver_success: not_established`.

Reproduce with `examples/simcenter/verify_process_identity.py`; it releases only
its own child via stdin EOF and invokes no termination API. Evidence, including
the initial failed observation, is in
`tests/simcenter/evidence/native-process-identity.json`. This does not test actual
OS PID reuse or cancellation of a solver. The observer is deployed but still
needs secure job-to-process binding and connection to live job status/cancellation.

### Solver-to-job correlation discovery

Run 10 exercised the persistent launch while a sanitized Windows process
observer checked whether command metadata contained the analysis directory or
input basename. Both `niece_solver.exe` and its `mpiexec.exe` launcher matched
the input basename, but neither matched the full analysis directory. Raw command
lines and environment values were not retained. Basename matching alone is not
a safe cancellation target or proof of unique job ownership.

The installed `tmgnx.cmd` describes the executive launcher, not a documented
per-job cancellation operation. It was read, not executed or changed. A broad
installed API search also did not identify a general SimSolution cancellation
method; this is a discovery result, not proof that no supported mechanism exists.
The next requirement is a verified unique per-job output name/directory, plus
process creation identity and exclusion of concurrent jobs sharing outputs.

The detached observation process ended before producing evidence. A direct
bounded observer captured the matches; after its client observation timeout,
the same PID was polled and confirmed exited with code zero. Its shared staging
file contained partially overwritten JSON frames. The final complete frame was
retained separately, with that limitation recorded.
`verify_process_observation_write.ps1` then verified complete snapshot publication
by temporary-file rename inside the native workspace; its post-solve observation
window correctly contained no solver processes.

Run 10 reached `solver_exited` after fixture-specific PID, timestamp, input and
output checks, with the same result hash as runs 08/09. Artifacts are preserved
outside Git; curated evidence is
`tests/simcenter/evidence/native-solver-binding-discovery.json`. No cancellation
was attempted, no licence settings changed, and safe generic process/job binding
remains incomplete.

### Native SIM Save As and separate export names

`nx_sim_save_as(document, path)` copies the active SIM to a new workspace `.sim`
path and creates its parent folders. Existing targets and already-loaded
basenames are rejected. It copies current live edits, verifies that the original
disk file is unchanged, and returns the new document reference plus actual
work/display paths. References for the renamed live document are invalidated;
failed preflight leaves those references intact. Native save errors retain
partial files and report their existence and current document path.

This is SIM-only copying. The response explicitly reports `shared_fem_path`,
`independent_geometry_variant: false` and unverified result freshness. FEM/CAD
must be duplicated and reassociated before modifying geometry or mesh as an
independent design variant. SaveAs may update result associations to the new
basename; an association alone does not establish existing or current results.

Native verification copied the disposable duct SIM to
`F-sim-copy-20260908-r1/unique_job_copy.sim`, with zero unsaved parts/objects and
an unchanged source-file hash. Its native input export was written as
`unique_job_copy-Flow_benchmark.xml` in the new directory, containing the same
186765 elements / 71748 nodes. The original SIM, XML and result bundle hashes
were unchanged. No solve was launched by this export test.

Real MCP testing then created `mcp_saved_copy.sim`, verified source preservation,
replayed the identical operation ID without another copy, and rejected the old
reference with `NX_OBJECT_STALE`. The active Simcenter window displays that copy.
An existing-target rejection returned `NX_INVALID_ARGUMENT` / `not_started`.
Reproduce with `verify_sim_save_as.py`, `verify_sim_copy_export.py`, and
`verify_sim_save_as_mcp.py` in `examples/simcenter`; these are ordered, isolated
fixtures, and their existing-target guards intentionally reject destructive reruns.
Evidence: `tests/simcenter/evidence/native-sim-save-as.json`.

A development deployment helper still contained an old probe invocation and
stopped before updating tool files. It was replaced with file-only deployment;
registration of all 12 opt-in tools and the real MCP checks were verified afterward.

### Direct document dependency inspection

`nx_sim_dependencies(document, offset=0, limit=50)` inspects direct associations
from a standalone SIM through its FEM to associated, idealized and master CAD.
It returns paged typed references, paths, merged ownership roles, readable units,
work/display flags, unsaved state and file availability. It does not load or save
parts. Unloaded associations and unenumerated CAD assembly children are explicit.
Assembly FEMs are currently unsupported. Recursive components, external property
or field files and solver/result dependencies remain outside this scope; this
is not a complete analysis package manifest.

The real MCP check returned the copied SIM and its shared FEM/CAD across three
pages, then an empty page, rejected a zero page size and preserved work/display
selection and unsaved flags. Evidence:
`tests/simcenter/evidence/native-dependencies-mcp.json`; reproduction:
`examples/simcenter/verify_dependencies_mcp.py`. There are now 13 opt-in tools.

The local regression run completed 1054 tests successfully; eight transport tests
were blocked at localhost socket binding by the sandbox. Re-running the affected
transport selections with socket access passed all 13 selected tests. These are
local regression checks, not additional native solver acceptance.

### Isolated solver output ownership

The internal `launch_isolated` adapter reserves an immutable job and claims its
output directory before recording launch intent. Directory ownership includes
the job store, job ID and request hash. Exclusive record creation rejects
competing jobs; incomplete records fail closed and remain available for
inspection. Ownership persists after failure or completion, so subsequent runs
must use new directories rather than overwrite previous results. Workspace
boundaries and resolved path aliases apply; Windows comparisons normalize case.

This does not redirect native solver output. The caller must verify the actual
NX export directory and separately establish model/session/resource concurrency
and process identity. The earlier `launch_once` adapter remains an internal
fixture primitive without cross-job output exclusion; neither adapter is a
public general solve tool yet. Claiming an existing directory does not establish
that its old artifacts belong to this job. Freshness still requires independent
prelaunch and postlaunch evidence.

Local tests exercise competing stores, terminal ownership, reconnects, broken
records and path aliases. The Windows fixture verified repeated ownership,
case-insensitive aliases, cross-store conflict and retained interrupted records
through two separate bridge clients in `UG_APP_SFEM`. It launched no solver and
changed no analysis geometry. Reproduce with
`examples/simcenter/verify_output_claims.py`; evidence is
`tests/simcenter/evidence/native-output-claims.json`. All 143 local Simcenter tests
passed after this change. Generic safe cancellation remains incomplete.

### Native flow input export through MCP

`nx_sim_export_input(document)` invokes the installed
`WriteSolverInputFile` operation with native setup checking for an active
NX MULTIPHYSICS Flow SIM. It requires a workspace subfolder containing only the
saved SIM; `nx_sim_save_as` can create that copy. This protects existing solver
artifacts without guessing vendor output filenames. The response identifies
actual XML and auxiliary paths, byte/content hashes, mesh counts and recognized
translator failures. Failed verification retains partial files. No solver is
launched, and a well-formed export does not establish numerical readiness.
Thermal/coupled export remains outside this public adapter's tested scope.

The first real MCP call revealed a deployment reload defect: the on-disk parser
was current, but the loaded Python function lacked mesh-count readback. It
rejected a valid 186765-element / 71748-node export. Retained XML and runtime
inspection established this was stale loaded code, not missing mesh geometry.
The development reload hook now reloads the export parser, input fingerprinting
and export adapter in dependency order before native tool registration.

A fresh SIM copy in `F-input-export-20260908-r2` then exported the expected mesh
through MCP. Replaying the operation ID returned the same input identity; a
new operation targeting the populated folder was rejected before export.
The active Simcenter document is `flow_input_r2.sim`; its FEM is still shared.
Evidence includes the initial failure, runtime diagnosis, corrected readback and
full MCP receipts in `tests/simcenter/evidence/native-input-export-mcp.json`.
Reproduction: `examples/simcenter/verify_input_export_mcp.py` accepts explicit
`--revision` and `--source-name` for a fresh isolated fixture folder and currently
active benchmark SIM. It refuses existing targets. There are now 14 opt-in
Simcenter tools; all 147 local Simcenter tests passed after this addition.

### Prepared revisions and an isolated native job

The internal `prepared_input` adapter binds exported input bytes to an explicit
set of saved analysis-file hashes. Preparation requires fully loaded documents
with no unsaved edits. Prelaunch validation rejects changed input, dependency
contents, dependency membership or live modification flags. Reads have a total
byte budget. This is the supplied dependency set, not a complete manifest of
external fields, materials and referenced assemblies.

`solve_cavity_isolated.py` exercised this guard with permanent output ownership
and durable launch intent in `F-input-export-20260908-r2`. The job
`isolated-flow-01` advanced through accepted, launch_requested, launch_returned,
running and solver_exited. Native same-handle observations recorded solver PID
6836 and MPI launcher PID 16012 with creation times and executable paths. The
early observation window preceded process creation; the existing job was
observed again without relaunch. Later both recorded PIDs were absent, fresh
outputs contained a completion footer, and canonical input matched the manifest.

The result bundle SHA256 is
`6f076a9cdd65a6a25a4ebe5a3a4b97312f20041957f108adfa0edb14a46a95d8`,
identical to the earlier tight-convergence case. Its log reports mass imbalance
0.008865% and momentum imbalance 0.0000226%. The post-solve SIM has an unsaved
flag despite matching saved dependency hashes. The revision guard correctly
rejects reuse of that preparation; current-model freshness remains unverified.
No automatic save or geometry change was used to hide the mismatch.

Evidence: `tests/simcenter/evidence/native-isolated-flow-job.json`. Native/result
files and the complete job history are retained outside Git in
`outputs/simcenter/isolated-flow01`. Reconciliation and stale-state checks are
`reconcile_isolated_flow.py` and `verify_prepared_guard.py`. These remain
fixture-specific process bindings; they do not establish generic launch,
cancellation, licence-concurrency management or full benchmark F acceptance.
All 151 local Simcenter tests passed with the preparation adapter; focused
preparation tests also passed after bounded-read hardening.

### Live inspection of recorded solver processes

`nx_sim_job_status(..., check_processes=true)` now rechecks recorded Windows
process identities. It compares PID, creation time and executable path; it can
report the same process running/exited, an absent original process, a different
identity or unavailable observation. Bare PIDs, duplicate references and missing
bindings return `unbound`. The default remains compact persisted-state inspection.
Live observations do not change the job revision, authorize another launch or
establish solver success. The tool still requires a responsive NX bridge and
does not discover child processes or perform cancellation.

Real MCP testing on `isolated-flow-01` verified both recorded processes absent
and preserved terminal revision 4. The compact default, evidence expansion,
unknown records, missing jobs and workspace rejection also passed. Evidence:
`tests/simcenter/evidence/native-job-process-status.json`; reproducible client:
`examples/simcenter/verify_job_status_mcp.py`. Local checks for PID reuse use
simulated observations; they are not an assertion that OS PID reuse occurred in
this native test. All 154 local Simcenter tests passed.

Cancellation discovery remains inconclusive. The installed thermal-flow folder
contains `MapMonitor.exe`, `MayaMonitor.exe` and a stop-button resource. The
inspected NX Open references did not expose a matching thermal/flow cancel
operation. Those observations establish neither a supported automation command
nor module absence. No guessed stop files, process termination or licensing
changes were attempted.

### SIM face inventory for boundary selection

`nx_sim_faces(document, offset=0, limit=50)` exposes typed SIM occurrence faces
and their prototype FEM bodies for an active SIM with one direct standalone FEM
occurrence. Each row includes a native face bounding box in explicitly labeled
FEM part-absolute coordinates and readable units. These boxes are not transformed
assembly bounds or exact surface geometry. Nested assembly FEMs are rejected.
The tool does not select faces onscreen, save or modify the model. References
use the existing session/owner lifecycle; reacquire them after geometry, mesh or
manual-session changes. This test does not establish remeshing/stale-face
acceptance or nested transforms.

Native MCP verification returned 18 faces over 4 pages, with
unique face references owned by the active SIM, explicit mm/FEM coordinates and
unchanged work/display/modified flags. Invalid page size was rejected. Evidence:
`tests/simcenter/evidence/native-sim-faces-mcp.json`; reproducible client:
`examples/simcenter/verify_faces_mcp.py`. All 157 local Simcenter tests passed.
There are now 15 opt-in public tools. Thermal convection creation remains an
internal natively exercised adapter and is not yet a public authoring tool.

### Thermal convection authoring through MCP

`nx_sim_convection(document, faces, coefficient_w_m2_k, name, provenance)`
creates assumed convection on explicit SIM occurrence face IDs. It is limited
to active NX MULTIPHYSICS Thermal solutions; Flow and coupled thermal/flow are
rejected before mutation. The positive coefficient is in W/(m² K), and the
boundary uses solution ambient temperature. Returned native properties expose
its defaults. This is an assumed boundary, not a CFD-derived coefficient.

The response includes a typed constraint reference and committed face readback.
Provenance and the `assumed` basis are stored as native constraint attributes.
Names are checked case-insensitively. Creation uses the existing visible undo
and rollback path; the tool does not save or solve. This native test covers
success, retry and preflight rejection, not injected rollback failure.

Real MCP testing created a new 10 mm thermal cube, assigned h=10 to all six
faces, verified identical-operation replay and duplicate-name rejection, and
saved a SIM copy. A separate native close/reopen check verified all six targets,
the coefficient and both provenance attributes. Other loaded documents'
modified flags were unchanged. NX marked the reopened SIM modified; no result
freshness or solve acceptance is inferred from reopen. The current displayed
SIM is `F-convection-mcp-20260908-r1/saved_convection.sim`.

Evidence: `tests/simcenter/evidence/native-convection-mcp.json`. Reproduce with
`verify_convection_mcp.py` followed by `verify_convection_reopen.py` in
`examples/simcenter`; their fixture guards prevent overwriting prior runs.
There are now 16 opt-in public tools and all 160 local Simcenter tests passed.
Convection remains restricted to the documented thermal-only route; automatic
interface-overlap diagnostics and broader boundary authoring are incomplete.

### Constraint inspection after reopen

`nx_sim_constraints(document, offset=0, limit=20)` pages the active SIM's
Constraints collection and reacquires typed references. Compact rows report
native type, target-set count and stored MCP provenance/basis. Optional
`include_properties` exposes native values, units and explicit unsupported or
failed property reads. `include_targets` returns up to 100 members per set with
truncation flags; supported SIM faces receive typed references, while other
target kinds remain explicitly unsupported. Loads and simulation objects are
separate collections and are not included.

Real MCP testing against the reopened saved convection SIM recovered the
10 W/(m² K) coefficient, provenance, assumed basis and all six face references.
Compact and expanded responses, an empty page and unchanged loaded-document
state were verified. Evidence:
`tests/simcenter/evidence/native-constraint-inventory-mcp.json`; reproduction:
`examples/simcenter/verify_constraints_mcp.py`. There are now 17 opt-in public
tools; all 161 local Simcenter tests passed. This inspection test is not broader
constraint-authoring, heat-load or solve acceptance.

### Total internal heat on a body

`nx_sim_heat_power(document, body, power_w, name, provenance)` assigns total
internal heat to one prototype FEM body selected from `nx_sim_faces`. The
adapter resolves its direct SIM occurrence and uses an expression-backed Watt
field. It requires an active NX MULTIPHYSICS Thermal solution, finite
nonnegative watts and nonempty provenance. Duplicate names and another heat
load on the same body are rejected. Multi-body, time-dependent and coupled
assignments remain outside this exposed route.

The response includes a `simulation_load` reference, committed SIM body, power
and native property readback. Provenance and `internal_heat` accounting are
stored on the load. The caller must supply actual heat rather than exported
electrical energy or battery storage; this single-value operation does not
perform scenario-level energy accounting. It does not save or solve.

Real MCP verification assigned 0.1 W to the isolated convection cube, rejected
negative power, reused the same load on identical-operation replay and rejected
a second source name on that body. Save/reopen preserved the 0.1 expression,
native heat-flow units, single body target and provenance. Other loaded
documents were unchanged. An initial fixture path guard rejected before close;
the corrected fixture then passed without recreating the load.

Evidence: `tests/simcenter/evidence/native-heat-power-mcp.json`. Reproduce with
`verify_heat_power_mcp.py` and `verify_heat_power_reopen.py` in
`examples/simcenter`. The displayed document is now
`F-convection-mcp-20260908-r1/saved_power.sim`. There are 18 opt-in public tools.
All 165 local Simcenter tests and 36 shared reference/import/authoring-contract
checks passed. This is authoring/persistence evidence, not an additional solve
or zero-power numerical acceptance benchmark.

### Load inspection and unused target slots

`nx_sim_loads` provides compact paginated load references and optional native
properties/target sets, including stored provenance and energy-accounting
labels. Supported SIM bodies and faces receive typed references. It does not
sum unlike loads or infer a scenario's total applied heat. Property readback now
includes human-readable unit symbols when available, alongside native names.

The first real test exposed `None` slots in unused native load target sets.
Shared load/constraint inspection now reports assigned count, native slot count
and empty slot count separately. Duplicate heat-source checking also tolerates
unused slots. The latter second-body case has local seam coverage, not a new
native multi-body authoring claim.

Final real MCP checks recovered the saved 0.1 W load, its body/provenance and
`HeatFlow_Metric2` symbol `W`, plus the existing six-face convection constraint.
Document state was unchanged. Evidence:
`tests/simcenter/evidence/native-load-inventory-mcp.json`; reproduction:
`examples/simcenter/verify_loads_mcp.py`. All 167 local Simcenter tests passed.
There are now 19 opt-in public tools.

### Verified thermal creation rollback

Thermal load/convection recovery now attempts undo even if builder destruction
fails. It verifies the original load, constraint and expression identities after
undo. A clean restoration reports `rolled_back`; cleanup errors, failed undo or
readback mismatch report `partial` with `NX_SIM_RECOVERY_INCOMPLETE`. A checkpoint
is retained when restoration cannot be verified. This helper is limited to
creation-only operations and is not a general geometry rollback verifier.

Native fault injection raised after committing a temporary convection boundary.
Counts changed from 1 load / 1 constraint / 56 expressions to 1 / 2 / 57, then
returned to the original identities after undo. No solve ran. Evidence:
`tests/simcenter/evidence/native-thermal-rollback.json`; reproduction:
`examples/simcenter/verify_thermal_rollback.py`. Builder-destroy and undo-failure
paths have local seam tests only. All 170 local Simcenter tests passed.

### Prescribed absolute temperature

`nx_sim_temperature(document, faces, temperature_k, name, provenance)` assigns
a constant absolute temperature to explicit SIM face IDs in an active
NX MULTIPHYSICS Thermal solution. Input is finite nonnegative Kelvin, not
Celsius. It returns committed Kelvin value, native properties and typed
constraint/face references, stores provenance and uses verified creation
rollback. It does not save, solve or perform automatic overconstraint analysis.
Time-varying temperatures remain outside this operation.

Real MCP testing created an isolated 100 × 10 × 10 mm block and prescribed
293.15 K on its x=0 face. Invalid negative Kelvin input was rejected and an
identical-operation retry reused the constraint. Save/reopen preserved the
293.15 expression, Kelvin unit / K symbol, one face target and provenance.
Other loaded documents were unchanged; NX marked the reopened test SIM modified.
This is boundary authoring/persistence evidence, not a new conduction solve.

Evidence: `tests/simcenter/evidence/native-temperature-mcp.json`; reproduce with
`verify_temperature_mcp.py` and `verify_temperature_reopen.py` in
`examples/simcenter`. The displayed model is
`A-temperature-mcp-20260908-r1/saved_temperature.sim`. There are now 20 opt-in
public tools, and all 174 local Simcenter tests passed.

### Existing FEM/SIM save and public conduction setup

`nx_sim_save(document)` saves only the explicitly selected, fully loaded FEM or
SIM at its existing workspace path. It verifies a backup of the prior disk file
in `.nx-mcp-save-backups/<unique-id>/` before calling native Save with component
saving and closing disabled. It checks unsaved-object counts, the selected
document's modified flag and other loaded document flags, and returns file
hashes and the backup path. Dependencies require explicit separate saves; save
the FEM before its SIM. The operation neither deletes backups nor establishes
result freshness. Files above the 1 GiB hashing budget are rejected. Supply an
operation ID; replay returns the original receipt. Partial native failures retain
the backup for inspection and do not claim rollback of disk writes.

Native public-MCP verification on the isolated 100 × 10 × 10 mm conduction block
created a 3 mm linear tetrahedral mesh, assigned k=200 W/(m K), density=2700 kg/m³
and heat capacity=900 J/(kg K), and applied 1 W total internal heat with one end
prescribed at 293.15 K. This uniformly heated case has an analytical maximum rise
of 2.5 K, distinct from the earlier end-flux benchmark. Both FEM and SIM saved
with verified backup hashes; repeated operation IDs returned the same backup
paths. This evidence covers authoring and saving, not numerical acceptance of
the new model. The saved SIM still requires mesh-association refresh verification
and a solve. See `tests/simcenter/evidence/native-conduction-setup-save.json` and
the two referenced reproducible fixtures. Local Simcenter suite: 176 passed.

### Native thermal input export

`nx_sim_export_input` now supports the installed NX MULTIPHYSICS **Thermal**
analysis as well as Flow. Coupled export remains untested and rejected. The
same fresh-folder restriction and retained-failure-artifact behavior apply.
The isolated uniform-heating conduction benchmark exported through public MCP
with 2,658 elements and 756 nodes after its saved SIM was reopened to refresh
the FEM association. Export replay retained its identity; a different operation
ID targeting the populated directory was rejected before export.

`examples/simcenter/verify_thermal_input.py` checks the actual XML's known fixture
values in the declared native export units: material conductivity/density/heat
capacity, total heat load with per-element/per-node options disabled, all 2,658
selected elements, and 22 element faces at the prescribed temperature. The XML
uses a −273.15 temperature shift, so the 293.15 K constraint exports as 20.
This is a fixture check, not a general XML physics validator or proof of the
geometric face mapping. No solver was launched. Evidence and hashes are in
`tests/simcenter/evidence/native-thermal-export-mcp.json`; reproduction uses
`verify_thermal_export_mcp.py` with a fresh revision and the expected source SIM.
The local Simcenter suite passes 179 tests.

### Uniform-heating conduction solve through the visible session

The publicly authored thermal fixture was solved once through the versioned
`solve_conduction_isolated.py` native test adapter, with durable job ID
`isolated-thermal-01`, a claimed output directory, a prelaunch saved-dependency
manifest and matching canonical input identity. This adapter is not a public
generic solve tool. The solver log reports 26 seconds and a completion footer;
no solver processes remained at the subsequent host inspection. Process identity
was not captured during the short solve, so the persistent job deliberately
remains `launch_returned`, not a verified process-terminal state.

Native nodal temperatures were 20 to 22.5004635 °C. The 2.5004635 K maximum rise
differs from PL/(2 k A)=2.5 K by 0.01854%, within the initial 1% discretization
check. Mesh refinement remains required. The log's aggregate heat input/output
are both 1e6 mN-mm/s (1 W), but its named sink summary is 9.981e5, a 0.19%
difference that remains to be reconciled. Energy acceptance is not claimed.
The saved CAD/FEM/SIM hashes still match preparation; the live SIM has unsaved
changes after solving, so the revision audit correctly rejects blanket result
freshness. Evidence: `tests/simcenter/evidence/native-uniform-conduction-solve.json`.
The read-only native audit is `audit_conduction_isolated.py`.

### Public nodal temperature results

`nx_sim_temperature_result(document, loadcase_index=0, iteration_index=0)`
exposes the existing native result reader through public MCP. Select indices
using `nx_sim_result_inventory`. The active SIM is required; negative or
out-of-range indices return structured errors. Results include degC extrema,
node count, owner document and native result-location IDs. These IDs apply only
to the selected result revision; they are not stable geometric references or
coordinates. The operation preserves existing postviews and does not save,
activate or solve. Region averages, junction interpretation and coordinates
remain outside this tool. `result_freshness` remains `not_verified`.

Native MCP verification on the uniform-heating fixture returned 20 to
22.5004634857 °C across 756 nodes, rejected negative and out-of-range loadcases,
and preserved all loaded document modified flags. Evidence:
`tests/simcenter/evidence/native-temperature-result-mcp.json`; reproduction:
`examples/simcenter/verify_temperature_result_mcp.py`. Local suite: 180 passed.

### Thermal energy-summary diagnostics

The internal `thermal_balance.inspect_thermal_balances` adapter now reads the
observed TMG aggregate thermal summary with a required verified power unit. It
retains each repeated summary separately, reports missing/duplicate/nonfinite
values, and limits input to 8 MiB. It does not infer time indices, SI conversion,
the meaning of the reported deviation, or conservation acceptance. This is
used by the native conduction audit; no additional public tool is claimed.

Native inspection found one complete summary with 1e6 mN-mm/s input and sink
flow and a reported deviation of 0.0499. The detailed report repeats these
values but does not explain the 9.981e5 named-sink summary. The discrepancy
remains unresolved. Evidence: `tests/simcenter/evidence/native-thermal-balance.json`.

### Visible temperature result views

`nx_sim_show_temperature(document, loadcase_index=0, iteration_index=0, name=...)`
creates and activates a temperature postview in the interactive Simcenter window.
The selected SIM must be work and display part. The tool verifies native field,
indices and Celsius units, retains result handles for visible views, and returns
a session-local postview ID. Existing views are retained; failed creation attempts
remove only their new view and report cleanup failures as partial state. Supply
an operation ID for retry deduplication. This does not save, solve, fit the camera,
export screenshots or certify freshness.

Native public-MCP testing created the uniform-heating contour, read back the
requested field and units, reused the same view ID on replay, and rejected an
out-of-range loadcase. A VM screenshot shows the temperature gradient and Celsius
legend, but an existing Windows Security prompt obscures part of the viewport.
Clean screenshot acceptance remains pending. Multiple preexisting views and
cleanup-failure injection are not covered by this native test. Evidence:
`tests/simcenter/evidence/native-temperature-postview.json`. Local suite: 188 passed.

### Clean contour image delivery and native resolution limitation

The existing agent-surface `nx_screenshot(style="current", fit=false)` followed
by `nx_download_file(delivery="image")` was verified against the new visible
conduction postview. The MCP image bytes match the exported SHA256. The PNG
contains the contour, Celsius legend and extrema without desktop dialogs, even
while the VM desktop has an overlapping security prompt. Current framing places
part of the legend/title over the geometry; presentation-quality framing remains
to be improved.

Exact output sizing remains unresolved. The installed NXOpen documentation states
that DeviceWidth/DeviceHeight set full-device capture dimensions when RegionMode
is false. In a native reproduction, both 800×500 and 1600×1000 remain set before
and after Commit, but each PNG is 2458×1484. The MCP response correctly reports
actual versus requested dimensions and a warning; do not advertise exact sizing.
`probe_postview_resolution.py` reproduces this without changing model/camera state.
Evidence: `tests/simcenter/evidence/native-conduction-screenshot.json`.

### Public native mesh-quality checks

`nx_sim_mesh_quality(document, include_settings=false)` checks all meshes in an
explicit standalone FEM without activating, saving, repairing or remeshing it.
The response includes element count, per-test summaries and summed error/warning
occurrences. These totals are not unique failed-element counts. Optional settings
expose current solver criteria; element-specific overrides remain flagged but
not enumerated. Native checks may highlight elements, so the tool is not marked
read-only. Empty meshes or empty check results are errors; solve readiness remains
unverified even with zero reported errors.

Native MCP checks on the 2,658-element conduction FEM reported zero error and
warning occurrences. Expanded and compact calls returned identical test results,
and all loaded document modified flags were preserved. Some native summaries
have no numerical worst value; these remain null. This does not prove CFD
connectivity, adequate boundary-layer resolution or mesh convergence. Evidence:
`tests/simcenter/evidence/native-mesh-quality-mcp.json`; reproduction:
`examples/simcenter/verify_mesh_quality_mcp.py`.

### Discoverable public-tool evidence

`nx_sim_capabilities.public_tool_evidence` indexes eighteen recent public-tool native
regressions with tested version, narrow scope and repository evidence path.
Other NX versions do not inherit tested status. This additive index is explicitly
incomplete and returns exposed/indexed counts plus the explicit unindexed tool
list. Unindexed means unassessed by this index, not unavailable or broken. The
existing API-presence and solver catalog remain separate. It
does not perform a current-session operation test or licence checkout. Major
unresolved workflows are returned alongside evidence, including generic solve/
cancellation, coupled cooling acceptance, thermal contacts, detailed fans and
acoustics, freshness and exact screenshot resolution. Native discovery on v2606
returned the expected evidence and preserved loaded document modified flags.
See `tests/simcenter/evidence/native-release-discovery-fan-tools.json` (18 indexed
of 32 exposed tools). The original ten-tool discovery receipt remains historical
evidence in `native-release-discovery.json`.

### Cancellation SDK investigation

The vendor documents [StopRun](https://help.mayahtt.com/tmg/topics/thermalapi/StopRun.html)
as an abort from inside a thermal plugin function. This is not an external
job-control API. A read-only search of the installed v2606 thermal solver include
files found no StopRun declaration. The bundled ExpressionsShell build script
also references `ugstructures/evalplugin/src`; that directory exists, but a
search of its headers and C++ sources likewise found no declaration. A follow-up
corrected the initial omission of `.hxx` headers: these are the actual installed
SDK header format. The expanded search still found no StopRun declaration, and
inspection of `CaeUtils_Exp_IContext.hxx` found field/time/material accessors but
no stop or abort method. The online plugin example therefore cannot yet be
compiled directly against the inspected interface. No plugin
was compiled or installed, no solve was cancelled, and no licensing configuration
was changed. This candidate remains unverified, not classified as universally
unsupported. The next investigation must establish the installed plugin service
interface or another documented monitor-control route before exposing cancellation.
Evidence: `tests/simcenter/evidence/cancellation-api-investigation.json`; the
read-only PowerShell probes are retained under `examples/simcenter/`.

### Solution inventory and selection

`nx_sim_solutions` pages a loaded SIM's solutions with typed owner-scoped
`simulation_solution` references, active flag, solver/analysis identifiers and
step count. Optional properties return committed native values.
`nx_sim_select_solution` requires the active SIM and a solution owned by it,
assigns ActiveSolution and verifies readback; on failure it attempts to restore
the prior selection. It does not save, solve or refresh results. Subsequent
load/result tools use the selected solution.

Native MCP verification covered inventory, property readback, already-active
selection, invalid paging and preservation of loaded document modified flags.
Switching between distinct solutions was subsequently verified through public MCP
in the isolated conduction SIM, including active-flag readback, rejection of a
solution owned by another SIM, and restoration of the original Conduction
selection. The second unsolved probe solution remains only in the unsaved test
SIM; no solve or save was performed. Forced API-failure rollback and stale
generation rejection remain natively untested. Switching evidence:
`tests/simcenter/evidence/native-solution-switch-mcp.json`. Initial inventory evidence: `tests/simcenter/evidence/native-solutions-mcp.json`.

### Public transient thermal output scheduling

`nx_sim_transient_setup` exposes the native transient-step adapter for an active
NX MULTIPHYSICS Thermal solution. It accepts 2..200 strictly increasing absolute
output times beginning at zero, configures transient/output flags, and returns
all committed step properties. Existing extra steps are rejected rather than
deleted. A conservative host-wide solver/translator process check precedes
mutation; this is not a per-job lock and cannot exclude manual launches racing
after the check. Failures attempt native undo; previous results are stale.

Temperature-change and minimum-step controls are stored with SI units, but the
installed time-method default is retained and their numerical effect may be
inactive. The response explicitly warns; actual integration requires a solver
log audit. Do not treat requested values as enforced bounds.

Native public MCP testing configured [0,10,20] seconds on the disposable unsolved
probe solution, read back three steps, replayed without duplication and rejected
a request that would require removing an existing step. Conduction was restored
as the active solution. No solve or save was performed. Native step creation
can change the active solution; the preparation fixture now restores it explicitly.
Evidence: `tests/simcenter/evidence/native-transient-setup-mcp.json`.

### Step/subcase inspection

`nx_sim_steps(document, solution, offset=0, limit=20, include_properties=false)`
pages a solution's steps with owner-scoped `simulation_step` references, native
step type, ordinal and active flag. Optional properties include actual stored
values and units. Inactive solutions can be inspected without selection changes.
Ordinals must be reacquired after steps are added, removed or reordered; result
freshness and actual integration intervals are not inferred.

Native public MCP testing paged the inactive probe across two calls, returned
three distinct typed step references and stored End Time values [0,10,20] seconds,
and preserved Conduction as active plus all loaded document modified flags.
Evidence: `tests/simcenter/evidence/native-steps-mcp.json`; reproduction:
`examples/simcenter/verify_steps_mcp.py`.


### Preparing an immutable solve request

`nx_sim_prepare_solve(document, job_id, job_folder="simcenter-jobs")` exports
native input from the active standalone Thermal/Flow SIM and reserves a durable
`accepted` job. It does **not** launch the solver. First use `nx_sim_save_as` to
save an analysis copy in a fresh output folder; the FEM/CAD remain shared,
explicit dependencies. Save all direct dependencies before preparing. The output
folder must contain only the saved SIM and the job store must be outside it.

Preparation checks known solver processes, fully loaded/saved dependencies and a
unique active solution name, performs native input export with setup checks,
compares dependency hashes before/after export, and records input/dependency
hashes plus an immutable output claim. Failed preparation retains partial files;
it never deletes artifacts or silently exports over them. The dependency scope
still excludes external fields/material files and recursive assembly content.
Input identity is not physical validity, convergence, or complete solve readiness.

Inspect the retained configuration with
`nx_sim_job_status(job_id, include_manifest=true)`. Repeating preparation for the
same accepted job revalidates its files without re-exporting. A job with existing
launch intent only reports its persisted state; it cannot be prepared again.
Native asynchronous launch is described below; cancellation remains pending.

Native public MCP verification prepared `public-prepared-flow-01` from
`F-prepare-20260908-r1/prepared_flow_r1.sim`: 186,765 elements, 71,748 nodes, three
saved dependencies, stable request SHA256 on replay, and unrelated document
modified flags preserved. No solver launched. Evidence:
`tests/simcenter/evidence/native-preparation-mcp.json`; reproduction:
`examples/simcenter/verify_preparation_mcp.py` (creates a fresh named fixture once).


### Native asynchronous launch

`nx_sim_launch(document, job_id, job_folder="simcenter-jobs")` consumes a prepared
job. It requires the selected SIM as work/display document, the same unique
solution, matching saved dependencies/input and the original output claim.
Native `Foreground=false` is read back before `SimSolution.Solve(Solve,
CompleteCheckAndOutputErrors)` and the prior setting is restored afterwards.
The tool preserves the prepared XML and persists launch intent before invocation.
API errors leave an uncertain job, never an automatically retried solve.

The response distinguishes `launch_returned` from solver execution, exit and
numerical acceptance. Native dispatch can be delayed: the public flow test's
first process snapshot was empty; a later observation found MPI and solver
processes. A durable workspace launch gate now prevents a different job from
entering that dispatch interval. It has no timeout or automatic release.
Explicit verified release is available through `nx_sim_release_job` after a
successful-output terminal observation; failed/cancelled recovery remains pending. The
same reserved job is never launched again. Process-name checks alone are not
sufficient concurrency protection; manually launched work outside this gate
remains an external race.

Native evidence `native-public-launch-mcp.json` records public launch and replay
of `public-prepared-flow-01`. The solver later exited, emitted a completion marker,
and produced a 46,367,644-byte BUN. Canonical XML content matched preparation,
although raw bytes changed. The BUN SHA256 matched the prior identical benchmark.
This does not establish mesh convergence, complete dependency identity, or the
full A–F acceptance suite. The post-test gate addition has local concurrency
regression coverage but has not yet been exercised by another native solve.

Remaining lifecycle work: an independent durable observer, process/job binding,
terminal-state/result audit, failed/cancelled gate recovery, supported cancellation and
reconnection tests. Job status remains `launch_returned` until later observations
are committed; do not interpret that persisted state as a running or finished
solver. The launch does not alter licensing or save source models.


### Flow residual and balance audit

`nx_sim_flow_log(job_id, log_name, job_folder="simcenter-jobs", offset=0, limit=50)`
reads a directly owned job log, up to 8 MiB, without updating the job or model.
Use a basename returned by `nx_sim_job_logs`. It reports equation residuals and
native status messages, the final residual criterion, percent imbalances and
boundary volume/mass flows in m³/s and kg/s (positive into the domain). Each page
includes a hash of the bytes read; compare hashes across pages because a running
log can grow. Overflow rates are null with an explicit overflow flag.

Only the observed Simcenter 2606 single steady-history format is supported.
Missing final equations, truncated final tables and concatenated histories cannot
establish final residual criteria. All configured convergence conditions, field
validity and mesh sensitivity still need separate verification. A completion
footer is reported without accepting the solve. A zero rounded boundary sum is
not zero native imbalance; the native imbalance denominator is not independently
established by this parser.

The public native job test returned 60 equation rows over 15 iterations, final
residuals below 1e-6, reported mass imbalance 0.008865%, and inlet/outlet volume
flows ±0.0001912 m³/s. Both native pages had the same log hash; outside-path access
was rejected and document modified/work/display flags were preserved. Evidence:
`tests/simcenter/evidence/native-flow-log-audit-mcp.json`. Reproduce with
`examples/simcenter/verify_flow_audit_mcp.py`; the numerical log excerpt used for
parser regression is `tests/simcenter/fixtures/flow-steady-excerpt.log`.


### Independent terminal observer

The deployed module `nx_mcp.simcenter.job_observer` runs under the existing
external Windows Python runtime, outside NX. For example:

```powershell
python -m nx_mcp.simcenter.job_observer --workspace D:\CAD\SIMCENTER_MCP_WORKSPACE --job-id public-prepared-flow-01 --maximum-seconds 300 --interval-seconds 5
```

Set `PYTHONPATH` to the deployed server's `src` directory. Observation is bounded
(1..86400 seconds; polling interval 1..60 seconds). A timeout leaves the job
reserved and does not authorize another launch. Each observation emits JSON;
terminal evidence is appended to the durable job history and survives client
reconnection. Re-observing a terminal state does not append another transition.
Automatic worker startup from `nx_sim_launch` is now implemented as described below.

This observer currently recognizes the successful-output terminal path only:
a fresh owned `.log` with one completion footer near its end, a fresh nonempty
`.bun`, the preserved pre-launch XML matching the manifest, canonical regenerated
XML equality, and no known host solver processes. It records `solver_exited`,
with explicit artifact-based evidence. It cannot recover the process exit code
or prove exact process-to-job binding retrospectively, and it does not infer
numerical convergence or result freshness against live unsaved NX edits.
Missing, stale, ambiguous or failed-output evidence leaves the prior state intact.

Native testing advanced `public-prepared-flow-01` from revision 2
`launch_returned` to revision 3 `solver_exited`. Public MCP `nx_sim_job_status`
then returned the same observer evidence. The observer did not use NX APIs,
modify models, release the launch gate or launch a solver. Evidence:
`tests/simcenter/evidence/native-independent-observer-mcp.json`; readback fixture:
`examples/simcenter/verify_job_observer_mcp.py`.

Remaining lifecycle work includes running-state and
failure observation with stronger process binding, failed/cancelled gate recovery,
and supported cancellation. This module is not the complete asynchronous solve
lifecycle or the lifecycle/failure acceptance benchmark.


### Verified launch-gate release

`nx_sim_release_job(job_id, job_folder="simcenter-jobs")` releases only the
workspace launch gate. It requires `solver_exited` from the independent terminal
observer, rechecks the exact log/result hashes and canonical input, and confirms
known solver inactivity. An OS file lock serializes gate claims/releases across
processes. The guard file stays in place permanently; the receipt is persisted
before the owner record is removed, so interrupted release can be retried.

CAD, solver inputs/results, job history and permanent output ownership are never
removed. An old released job cannot acquire the gate again or be launched again.
A repeated release leaves any newer job's gate untouched. Failure, missing data,
changed artifacts and foreign ownership retain the gate. This is execution
housekeeping, not numerical acceptance or result-freshness verification.

Native public MCP verification claimed a test gate **after** the existing flow
job had been independently verified terminal, then released it and checked retry,
receipt readback and unchanged document flags. This verifies the Windows locking
and release path with real artifacts, not an automatically monitored full solve.
Evidence: `tests/simcenter/evidence/native-gate-release-mcp.json`; setup:
`examples/simcenter/prepare_gate_release_test.py`; public readback:
`examples/simcenter/verify_gate_release_mcp.py`. Failed/cancelled release and a full
automatic launch/observe/release cycle remain untested/unimplemented as applicable.


### Automatic observation across MCP client reconnects

`nx_sim_launch` now starts a bounded background observer after native dispatch,
including an uncertain native launch when a durable job exists. The worker runs
inside the NX process but outside its UI thread, uses no NXOpen calls, and cannot
launch/cancel a solver or release its gate. It continues when the MCP client or
sidecar disconnects. Durable job records survive observer exit; an NX process
exit stops this daemon worker, so observation must be resumed after restart.

`nx_sim_observe_job(job_id, job_folder="simcenter-jobs", maximum_seconds=3600)`
starts or resumes observation without a document selection or solver launch.
A live worker is reused without resetting its deadline; the maximum duration
applies when starting a new worker. The default is one hour, with a 1..86400-second
bound and five-second polling interval. Timeout only stops observation. Per-worker
logs are bounded to 64 KiB and exclude arbitrary exception messages.
`nx_sim_job_status` reports worker thread liveness and its downloadable log path.
No active-worker/file marker alone is treated as proof that a solver is running.

The isolated `auto-observed-flow-01` native test exercised prepare → launch →
automatic observer → launching MCP client disconnect → a separate client observing
revision 3 `solver_exited` → verified gate release → flow-log audit. The observer
finished, canonical input matched, and the 46,367,644-byte native result matched
the previous benchmark hash. The final residual criterion was met. A VM command
observation timeout occurred; the persisted client receipt confirmed completion,
and no launch was repeated. This is successful-path reconnect coverage, not
transport interruption during mutation or an NX process restart test.

Evidence: `tests/simcenter/evidence/native-auto-observer-cycle.json`. Fixtures:
`examples/simcenter/verify_auto_observer_launch_mcp.py` then
`examples/simcenter/verify_auto_observer_finish_mcp.py`. Remaining work includes
running/failure classification, exact process-to-job binding, cancellation,
NX-restart recovery acceptance, and the remaining numerical benchmarks.


### Installed load/constraint descriptor discovery

`nx_sim_descriptors(document, kind="load", offset=0, limit=50,
name_contains=null)` reads native names through documented `UF.Sfl` enumeration
for the selected solution in a loaded SIM. It does not activate that SIM, create
builders, mutate geometry or check out a solver licence. `kind` is `load` or
`constraint`; filtering is case-insensitive and precedes paging. Names describe
installed definitions, not stable model-object IDs or tested authoring support.

Installed v2606 native testing returned 5 load/9 boundary definitions for Flow
and 17 load/11 boundary definitions for Thermal. Public MCP testing inspected the
inactive Thermal SIM, paged Heat Load/Heat Flux, filtered convection definitions,
and preserved all document modified/work/display flags. Evidence:
`tests/simcenter/evidence/native-descriptors-mcp.json`; fixtures:
`examples/simcenter/inspect_native_descriptors.py` and
`examples/simcenter/verify_descriptors_mcp.py`.

This resolves native-name discovery for these categories only. Thermal contact
is a simulation-object category and was absent from both lists. Its mapping and
benchmark remain unresolved; these enumeration results do not establish that a
contact module is missing or that the prior rejected UI labels are valid neutral
builder names. A recorded native contact command or supported simulation-object
catalog is still needed.


## Heat scenario preview

`nx_sim_scenario_preview(document, path, region_targets, format, metadata)` reads
UTF-8 JSON or CSV inside the NX workspace (1 MiB, 1000 source limit). JSON uses the
version 1 heat-scenario schema. CSV uses exactly these columns:

```csv
name,region,watts,category,accounting_id,provenance_kind,provenance_source
CPU,SOC,8,internal_heat,processor,assumed,benchmark
USB,,10,exported_electrical,usb,assumed,benchmark
```

For CSV supply metadata such as `{"name":"full-load","workload_revision":"assumed-r1","ambient_K":298.15}`.
Map `SOC` to a current FEM body reference from `nx_sim_faces`. Every internal heat
region needs an exact mapping; missing/unused mappings, duplicate targets, duplicate
source/accounting identities, malformed rows and non-finite power are rejected.
Multiple contributions to one body must be consolidated explicitly before assignment.
The native parser uses only the Python standard library because NX's embedded
interpreter has no Pydantic installation.

The preview returns canonical scenario and source-file hashes, provenance, resolved
body references and separate totals for internal heat, exported electrical power and
battery storage. It does not apply ambient temperature or loads, check existing load
conflicts, or establish that the scenario is ready to solve. Distinct accounting IDs
cannot prove physical independence: the caller must still exclude converter input/output
subtotals that would double-count the same energy. `nx_sim_scenario_apply` repeats parsing and selection checks at application time;
its initial support is the creation-only thermal workflow below.

Real MCP verification on NX 2606 resolved the inactive thermal SIM's FEM body,
reported 8 W internal heat separately from 10 W exported electrical power, rejected
missing mappings and an invalid object ID, and preserved document state.
Evidence: `tests/simcenter/evidence/native-scenario-preview-mcp.json`.
Fixture: `examples/simcenter/verify_scenario_preview_mcp.py`.


## Applying internal heat scenarios

`nx_sim_scenario_apply` accepts the same file and mapping as the preview, plus
required `expected_preview_sha256`. Pass the preview response’s `preview_sha256`;
it binds file bytes, scenario metadata, the SIM ID and exact region-to-body IDs.
Changes are rejected with `NX_SIM_SCENARIO_CHANGED` and `not_started`, before load
creation. A new preview is needed after reopening/rebinding selections. The digest
is a consistency check, not a substitute for native selection validation. It requires
an active standalone NX MULTIPHYSICS Thermal SIM, no existing loads, and no known
solver process. It creates every internal-heat source under one outer undo mark,
verifies each committed watt value and their total, and stores source provenance,
accounting identity and scenario hash on each load. Exported electrical power and
battery storage remain excluded. Ambient temperature is returned but not applied;
convection, prescribed temperatures and other boundaries remain separate explicit
operations. Existing load replacement and coupled-flow scenario application are not
implemented. Do not interpret successful heat assignment as a solve-ready model.

Use an operation ID for transport retry. Native public MCP verification created an
isolated thermal benchmark, applied 8 W from CSV, replayed the operation without a
second load, rejected another application with a new operation ID, inspected the
load and saved the SIM. Evidence: `native-scenario-apply-mcp.json`. A separate native
fixture forced a readback mismatch after actual load creation and verified rollback
of load, constraint and expression identities before successful reapplication
(`native-scenario-apply-rollback.json`). The later native two-source and reopen checks are recorded below. Field-wrapper
inventory during rollback remains outstanding. Fixtures: `probe_scenario_apply.py` and `verify_scenario_apply_mcp.py`
in `examples/simcenter/`; both require their documented fresh benchmark folders.


Native scenario consistency regression (NX 2606): changing ambient metadata or
adding a newline to a separate test CSV both returned `NX_SIM_SCENARIO_CHANGED`.
Native inventory still contained zero loads. The original preview then authorized
8 W creation, operation replay, conflict rejection and save in a fresh isolated SIM.
These results replace the earlier application receipt at
`tests/simcenter/evidence/native-scenario-apply-mcp.json`. No production file was
edited; the changed CSV was a new benchmark artifact. Application never rereads
scenario bytes after validation, so the committed plan is the exact parsed snapshot
whose hashes are returned.


## Multi-body scenario persistence

The benchmark factory now accepts `block_origins_mm`: 1..16 finite XYZ origins in
millimetres, each within ±10000. It creates equal-sized solid blocks using the
existing length/width/height arguments. Overlapping blocks are rejected before file
creation; touching is allowed but does not create thermal contact automatically.
The default remains one block at the origin. Hollow-cavity creation remains limited
to the original single origin. The result reports actual FEM body count and origins.

Native NX 2606 verification created two 10 mm blocks, at [0,0,0] and [20,0,0].
Scenario application created 8 W and 2 W heat sources. A forced readback failure on
the second source restored load, constraint and expression identities for the whole
transaction; subsequent application returned 10 W. Public MCP independently created
a two-body fixture, applied both sources, rejected changed previews, replayed without
duplication and saved. Closing only the saved SIM and reopening preserved both powers,
provenance/accounting attributes and two distinct native targets. The old load ID was
rejected as `NX_OBJECT_STALE`; other loaded parts retained their modification flags.
The reopened SIM itself was marked modified, whose cause was not established by this
check; this is not evidence of a clean/fresh solved model. No solve was launched.

Combined evidence: `tests/simcenter/evidence/native-scenario-multi.json`.
Reproducible fixtures: `probe_scenario_multi.py`, `verify_scenario_multi_mcp.py` and
`verify_scenario_multi_reopen.py` in `examples/simcenter/`. Fresh fixture folders are
required for creation; the reopen fixture requires the saved, unmodified test SIM.


### Modified flag after scenario reopen

Follow-up diagnostics distinguish native loading from inspection. A fresh disk copy
was already modified when `OpenBaseDisplay` returned, before `SetWork`, load enumeration
or property/target/provenance inspection. Saving only that diagnostic copy with verified
backups then closing/reopening the same path twice produced unmodified parts on both
cycles. On that clean copy, individually traced scalar-wrapper, expression, field,
formula, target and provenance getters did not set the modified flag. Source files
and unrelated document flags were preserved.

This narrows the observed transition to initial native loading for the copied file;
it does not identify the internal NX change or prove why the original fixture’s
first reopen was dirty. Do not clear flags or bypass saved-dependency validation.
Inspect native state and explicitly save approved analysis changes before preparation.
No licensing or firewall settings were changed. Evidence:
`tests/simcenter/evidence/native-reopen-modified-diagnostics.json`.
Fixtures in `examples/simcenter/`: `probe_reopen_modified.py`,
`probe_same_path_reopen.py`, `probe_clean_property_reads.py`.


## Opening and closing analysis documents

`nx_sim_open(path)` opens a workspace `.sim` or `.fem` using an NX-host absolute path
or workspace-relative path, displays it and enters the simulation application.
A loaded document is reused with the same live reference; unsaved edits are not
saved or discarded. New native loads return load status, fully-loaded state,
modification flags, work/display paths and units. Partial loads fail explicitly;
files and session state remain available for inspection. No automatic dependency
repair or retry is performed. Existing loaded basenames must be distinct, even
across `.sim` and `.fem` extensions; the adapter rejects that conflict before NX.
The tool requires no known solver process and does not establish result freshness.

Native MCP tests opened fresh isolated SIM and FEM copies, reused a loaded SIM,
switched between documents and rejected a missing file. Original document flags
were preserved. An initial test deliberately retained equal basenames and received
NX 1020004; a distinct FEM basename loaded successfully. The final preflight returned
`NX_SIM_NAME_CONFLICT` / `not_started`, and loaded millimeter-unit readback passed.
Missing-dependency and inch-file cases have not been natively tested. Evidence:
`tests/simcenter/evidence/native-sim-open-mcp.json`. The clean fixture
`examples/simcenter/verify_sim_open_mcp.py` now uses distinct basenames; the separate
`verify_sim_open_distinct_mcp.py` records recovery from the original test conflict.


`nx_sim_close(document)` closes a loaded workspace FEM or SIM by its live reference.
Save approved changes explicitly first: modified targets are rejected with
`NX_SIM_UNSAVED_DOCUMENT`. Loaded parent assemblies and SIM-to-FEM dependencies
block closing with `NX_SIM_DOCUMENT_IN_USE`. Native close uses `DontCloseModified`
and does not save or delete files. Every actual unloaded part is reported, and its
references/history are invalidated even if native close later reports a failure.
Unused dependencies may be unloaded by NX; reacquire references before continuing.

Native public MCP acceptance covered an explicitly marked-unsaved test SIM, a
referenced FEM rejection, explicit save, SIM close/retry/reopen, and the same cycle
for an independent inactive FEM copy. Each close unloaded one part. Closed references
returned `NX_OBJECT_STALE`; reopened references differed. Other loaded document flags
were preserved. A local fault test covers native failure after unloading, ensuring
references/history are still invalidated; that failure path was not injected in NX.
Evidence: `tests/simcenter/evidence/native-sim-close-mcp.json`. Fixtures:
`prepare_close_unsaved_fixture.py`, `verify_sim_close_mcp.py` and
`verify_fem_close_mcp.py` in `examples/simcenter/`.


## Coupled setup: verified operations and remaining controls

`nx_sim_flow_setup` now accepts an active NX MULTIPHYSICS Coupled Thermal-Flow SIM.
`create_step` creates the installed `Step - Thermal Flow` step. `attach_defaults`
associates four natively verified tables: Thermal Parameters, Flow Solution Parameters,
Flow Surface Parameters and Thermal-Flow Output Requests. Flow-only setup retains
its original three-table path. Both actions now check known solver inactivity.

The coupled solution uses one combined output-request property; the separate thermal
and flow output keys do not apply. Native descriptor probes verified creation,
association and rollback for all four supported tables. Public MCP verified coupled
creation, step/table setup, replay, existing-table rejection and save.
`Coupled Solution Parameters` exists as a property but that same string is rejected
as a table descriptor with NX 3520001. The API returns this unresolved control mapping
and `solve_ready:false`; it does not substitute an arbitrary descriptor or infer a
missing module/licence. No coupled solve, numerical acceptance or benchmark E pass is
claimed. Solid/fluid assignment, interfaces, mesh and coupled controls remain required.

Evidence: `tests/simcenter/evidence/native-coupled-setup-mcp.json`.
Fixtures: `probe_coupled_tables.py`, `inspect_coupled_setup.py` and
`verify_coupled_setup_mcp.py` in `examples/simcenter/`. The descriptor probe expects an isolated coupled SIM with an initial step
and no assigned tables; the public MCP fixture creates its own fresh analysis.

### Optional execution-settings inspection

`nx_sim_solutions(document=..., include_execution_options=True)` returns each
solution's native solver-options descriptor and committed properties. The default
response omits this expansion. Property names and enum values remain native;
unsupported reads are explicit. Licence-related properties are excluded, and
reading these settings does not perform a licence checkout or change settings.

The public MCP test on the visible coupled-analysis session verified `Remote Solve`
was false and `Maximum Number of CPUs` was 1, with all document modification flags
preserved. Evidence: `tests/simcenter/evidence/native-execution-options-mcp.json`;
reproduction: `examples/simcenter/verify_execution_options_mcp.py` (expects these
settings on the active isolated SIM). The initial test used incorrect compacted
property names and failed its assertion; the corrected test uses actual NX names.

This table does not resolve the missing `Coupled Solution Parameters` descriptor.
The inspected coupled step's raw `Solution Type` value of 1 is not evidence of
steady-state configuration. Coupled solve readiness and numerical acceptance
remain unverified.

### Allowable solution-step discovery

`nx_sim_descriptors(document=..., kind="solution_step")` uses the installed UF
solution descriptor API to return allowed step names and their native
`step_type_index`. Filtering and pagination preserve original indices. This
read-only operation requires a SIM work part and does not activate the target,
create a step, change settings or check out a solver licence.

A native probe of the isolated coupled analysis returned one descriptor,
`Step - Thermal Flow`, at index 0, matching `AllowedStepTypeCount = 1`; all
document modification flags were preserved. This establishes the allowed step
descriptor, not the interpretation of its `Solution Type` property or coupled
solve readiness. Public regression: `examples/simcenter/verify_step_descriptors_mcp.py`.

The public MCP check passed for the coupled descriptor, end-of-page response and
unchanged document flags. Evidence:
`tests/simcenter/evidence/native-step-descriptors-mcp.json`. The local Simcenter
suite passed 279 tests after this extension; these do not substitute for numerical
coupled acceptance.

### Matched fine-mesh restriction comparison

`examples/simcenter/prepare_fine_k0.py` creates an isolated copy of the saved
K=2 flow benchmark and changes only its native head-loss coefficient to K=0.
Native readback verified 186765 elements and 71748 nodes, coefficient 2 → 0,
the unchanged source file SHA-256 and unchanged existing document modification
flags. Evidence: `tests/simcenter/evidence/native-fine-k0-preparation.json`.

`examples/simcenter/launch_fine_k0_mcp.py` exported and launched durable job
`fine-k0-flow-01` in `D-fine-k0-solve-20260908-r1`, with automatic observation
remaining active after the MCP client disconnected. The subsequent observation
wrapper (guest PID 14188) exceeded its observation window; re-polling that same
PID confirmed it remained live. A separate process/log check confirmed active
`niece_solver` PID 11464 and `mpiexec` PID 17324 with advancing residual output.
No duplicate solve was launched.

`examples/simcenter/audit_fine_k0_mcp.py` observes the existing job and audits its
terminal log. The completed operating-point comparison is recorded below; full
benchmark acceptance remains incomplete. These files are reproducible benchmark scripts, not a general
parameter-study API. The constant-density fluid representation and synthetic
fan curve retain the limitations documented above.

The K=0 job subsequently reached `solver_exited`; its observer stopped, and the
verified launch gate release succeeded without deleting result files or allowing
a relaunch of the old job. Evidence: `tests/simcenter/evidence/native-fine-k0-cycle.json`.

The independent deck comparison found identical exported node/element XML and
fan-curve properties. `Head Loss Coefficient` (0 versus 2) was the only differing
exported property. On this same fine mesh:

| Quantity | K=0 | K=2 |
|---|---:|---:|
| Flow (m³/s) | 0.0002524 | 0.0001912 |
| Fan pressure rise (Pa) | 0.3691 | 0.5221 |
| Native mass imbalance (%) | 0.01252 | 0.008865 |
| Final iteration | 13 | 15 |

Adding K=2 reduced flow by 24.247%. Both cases met their recorded final RMS
threshold of 1e-6 and a 0.1% mass-imbalance screening limit. Each pressure–flow
point agrees with the synthetic curve within 0.0002 Pa, covering the combined
rounding of the reported flow and pressure. These checks demonstrate a matched
restriction response; they do not establish mesh convergence or complete all
benchmark D requirements.

Evidence: `tests/simcenter/evidence/native-fine-duct-comparison.json`, with the two
`fine-k*-native.log` snapshots in the same directory. Reproduce the comparison
with `examples/simcenter/compare_fine_duct_inputs.py` on the NX host and
`examples/simcenter/audit_fine_duct_comparison.py` on the retained snapshots.

### Native opening head-loss authoring

`nx_sim_head_loss` creates or updates a native dimensionless opening-resistance
coefficient in an active NX MULTIPHYSICS Flow SIM. Supply the typed opening ID
from `nx_sim_objects`. Creation requires `name`; updates require the expected
current coefficient and reject a conflicting readback before writing. An equal
value is a no-op. Calls return committed values and properties, do not save or
solve, and require result revalidation after a change. Use `operation_id` for
retry deduplication.

Public MCP tests on a separate analysis copy verified creation, K=0→2 updates,
conflict rejection, replay, no-op and restoration to K=0, preserving other
document flags. Local failure injection verified rollback after mismatched
readback; native failure-injection coverage remains pending. Evidence:
`tests/simcenter/evidence/native-head-loss-mcp.json`; fixtures:
`examples/simcenter/verify_head_loss_mcp.py` and
`examples/simcenter/verify_head_loss_create_mcp.py`. The creation fixture detaches
an old table on its disposable copy without deleting that table.

This exposes the scalar native coefficient tested by the matched duct study.
It is not a porous-volume or pressure-loss-curve model. The general coefficient
convention remains explicitly unverified; do not infer vent coefficients from
geometry or assume it applies to arbitrary boundaries. Coupled assignment is
not supported by this tested adapter.

To read the expected value before editing, call
`nx_sim_objects(document=..., include_properties=True)`: Opening rows expose
`head_loss` with the actual coefficient, table name and units, or null when no
table is assigned. Native readback verified the newly created table at K=0.
Discovery reports 47 exposed tools and 31 with indexed native evidence, with
per-tool test scope rather than a blanket certification. Deployment/readback
receipt: `tests/simcenter/evidence/native-head-loss-discovery.json`.

### Coupled dialog discovery limitation

The installed Python API exposes `UI.DialogTester.InvokeMenuButtonAction` and
resolves the native `UG_SFEM_INSERT_SOLUTION` button (ID 22997). A single
recorded invocation on the isolated coupled analysis failed with NX 900000
and preserved all document modification flags. The generated C# journal
contains the exception and an unresolved argument, not coupled-control
construction calls. Recording was stopped normally; no solver was launched.

The .NET SDK lists Automated Testing Studio as an invocation requirement, but
this error does not establish missing or busy licensing. No licensing settings
were changed. `MenuButton.FreeResource` and the attempted UF error-decoding
entry points were not exposed through the inspected Python bindings. This UI
probe is not advertised as a supported modeling tool, and does not resolve the
`Coupled Solution Parameters` descriptor. Evidence:
`tests/simcenter/evidence/native-solution-dialog-probe.json`; reproducible
probe: `examples/simcenter/probe_solution_dialog.py` (retains a durable intent
and rejects repeating the same invocation).

### Result-to-job binding and revision audit

`nx_sim_result_identity(document=..., job_id="fine-k0-flow-01")` optionally
binds the active SIM and solution to their original durable job. It rejects a
different analysis path (including a copy) or solution before hashing results,
then compares the native result association with the job's observed result
artifact. The remaining `maximum_bytes` budget covers the supplied pre-solve
dependency hashes and current loaded-document flags. No saving, field loading
or solver launch occurs. Omitting `job_id` preserves file-identity inspection.

Native public MCP verification matched the K=0 result artifact and rejected an
unrelated coupled SIM. The original K=0 SIM's unsaved flag prevented current
revision verification; the audit returned `not_verified` while separately
reporting that the result artifact matched. A changed SIM hash or unsaved flag
can reflect solver metadata and does not identify a physics change by itself.
Neither a matching artifact nor matching supplied file revisions certifies
complete model freshness, dependency completeness or numerical validity.

Evidence: `tests/simcenter/evidence/native-result-binding-mcp.json`; reproduction:
`examples/simcenter/verify_result_binding_mcp.py`. Local tests additionally cover
changed saved/unsaved models, replaced results, extra result associations and
missing terminal evidence. The Simcenter suite passed 284 tests. Native geometry
change/remesh invalidation and a complete freshness proof remain outstanding.

### Fan operating points in the public flow audit

`nx_sim_flow_log` now includes `fan_operating_points`. For the observed NX2606
log layout it reads the native pressure-unit header, converts pressure to Pa
and flow to m³/s, and matches fan rows to uniquely named flow boundaries.
Missing summaries return `not_present`; unknown units, repeated summaries or
unmatched names return an explicit unverified state with no converted points.
The parser uses only the standard library inside NX.

Public MCP verification reproduced both completed fine-mesh points: K=0 at
0.3691 Pa / 0.0002524 m³/s and K=2 at 0.5221 Pa / 0.0001912 m³/s. Document flags
were preserved. Evidence: `tests/simcenter/evidence/native-fan-operating-points-mcp.json`;
reproduction: `examples/simcenter/verify_fan_operating_points_mcp.py`. The local
Simcenter suite passed 288 tests, including recorded logs and ambiguity cases.

These remain rounded log observations identified by display names. The log
read does not establish static versus total pressure convention, stable native
entity binding, current-model freshness or numerical acceptance. Other log unit
layouts and multi-region fan summaries require further native validation.

### Persistent launch-gate diagnostics

`nx_sim_job_status(job_id=..., include_launch_gate=True)` optionally reports
workspace gate ownership. A verified claim identifies its owning job, folder,
request hash and recorded state/revision. Incomplete, changed or inconsistent
owner/job records report `unknown`; inspection preserves them. A launch blocked
by another job now includes this diagnostic in the busy error.

Inspection creates no lock files, expires no claims, releases no ownership and
does not inspect solver processes. `unclaimed` therefore authorizes neither a
launch nor a conclusion that the solver is idle. Explicit terminal verification
and the existing launch/release checks remain required.

Public MCP verification on the completed K=0 job confirmed the compact default,
optional unclaimed-gate output and unchanged document flags. Local tests cover
claimed ownership, competing jobs, partial records and outside-workspace owner
paths without mutation or expiry. Evidence:
`tests/simcenter/evidence/native-gate-inspection-mcp.json`; reproduction:
`examples/simcenter/verify_gate_inspection_mcp.py`. The local Simcenter suite
passed 291 tests. Native interruption/cancellation and corrupt-gate recovery
remain separate uncompleted acceptance cases.

### Independent analysis clone: native fixture verification

`examples/simcenter/probe_clone_dryrun.py`, `probe_clone_native.py` and
`verify_clone_reopen.py` exercise installed NX 2606 `UFSession.Clone` bindings
on the disposable fine K=0 duct benchmark. These are bounded development
fixtures, not a released general-purpose variant tool. They refuse to reuse
an existing output directory and never retry a clone after an uncertain response.

The first inventory returned API code zero but `LoadStatus.Failed=true` and
720090 (`UF_CLONE_err_comp_not_found`). The installed header defines this as
failure to find a component using the current load options. The session used
`FromDirectory`; temporarily selecting `AsSaved` resolved the SIM, FEM and CAD
without warnings. The fixture checks both return code and load diagnostics,
terminates only its own clone context, and restores the original load method
in `finally`. No network or licence configuration change was needed.

An explicit three-file naming map passed native dry-run validation with zero
naming failures. Native cloning then created separate SIM/FEM/CAD files under
`ui-benchmarks/D-independent-clone-native-20260908-r1`. All three source hashes
and existing loaded-part modified flags were preserved. After opening the
clone, its actual SIM-to-FEM and FEM-to-CAD links pointed exclusively into the
new directory. NX initially left the associated CAD unloaded; explicitly
loading that exact expected file resolved the inspection. The copied model
retained 186765 elements, 71748 nodes, the Flow solution and opening coefficient
K=0. The clone remains displayed in the dedicated Simcenter window.

This clones saved disk state; unsaved source edits are not included. These
checks do not prove complete dependency packaging, fan/selection equivalence,
independent mesh editing, or result freshness. Those remain required before
publishing a variant API or claiming a refinement comparison. No new solve was
launched. Evidence: `tests/simcenter/evidence/native-clone-search-api.json`,
`native-clone-inventory.json`, `native-clone-dryrun.json`,
`native-clone-files.json` and `native-clone-reopen.json` in the same directory.

The next clone checks used a newly generated solver deck, rather than the XML
and BUN already present in the cloned directory. Native cloning copied solver
artifacts as well as the three parts; their presence is not evidence of a new
solve. The export fixture preserved these files and saved the cloned SIM into
a fresh output directory referencing the independent FEM.

The fresh deck's node/element lists, selection sets, simulation objects, fan
curve, field tables and solver settings matched the reference. All `Property`
elements matched. Only two material/collector `uname` attributes differed,
substituting `independent_mesh` for the original FEM basename; values, IDs and
material type were unchanged. This remains the documented constant-density
LIQUID surrogate, not an ideal-gas or coupled-flow validation.

`refine_independent_clone.py` then changed the copied core sizing from 1.5 to
1.25 mm, retaining eight layers, 0.1 mm first thickness and 1.2 growth rate.
The copied FEM increased from 186765 elements / 71748 nodes to 261589 /
98632. All other loaded FEM counts, original file hashes and unrelated modified
flags remained unchanged. Save/reopen retained the refined counts; native
quality checks reported zero error and warning occurrences under the recorded
settings. These checks establish isolated mesh editing, not numerical mesh
convergence. Existing results must be revalidated after this edit.

Evidence in `tests/simcenter/evidence/`: `native-clone-export-comparison.json`,
`native-clone-material-diff.json`, `native-clone-refinement.json` and
`native-refined-clone-quality.json`. The local Simcenter suite passed 294 tests.
`launch_independent_refined_mcp.py` and `audit_independent_refined_mcp.py` are
separate public-MCP launch and reconnect fixtures for job
`independent-refined-flow-01`; never rerun the launch fixture after an
observation timeout. Numerical acceptance is recorded separately after its
native result audit.

The refined job completed through the automatic observer after the launch MCP
client disconnected. A separate client verified `solver_exited`, released the
launch gate and read the native log. The final audit reports 13 iterations,
flow 0.0002530 m³/s, fan pressure rise 0.3674 Pa and native mass imbalance
0.008828%. Both reference and refined runs met the final residual criteria;
the synthetic fan-curve discrepancy was within the 0.0002 Pa log-rounding
allowance. Relative to the 1.5 mm reference, flow changed +0.237718% and fan
pressure rise −0.460580%.

The actual exported property values and fan curve match across refinement.
`ElementList`, `NodeList`, `ModelInformation` and `SimulationObjects` sections
changed. Geometric boundary-selection validation remains necessary for the
mesh-dependent simulation-object entries. Two core sizes with unchanged wall
layers do not establish convergence order, an extrapolated error bound or
boundary-layer convergence. No coupled-flow or product acceptance is claimed.

Reproduce the numerical comparison with `audit_refinement_comparison.py`, using
`native-fan-operating-points-mcp.json` and the retained public-MCP finish receipt.
Curated evidence is `native-independent-refined-cycle.json`,
`native-core-refinement-comparison.json` and `native-refined-deck-comparison.json`.
Native result files remain on the authorized host; they are not added to Git.

### Geometric boundary preservation after refinement

`audit_native_boundary_patches.py` checks every exported inlet/outlet face against
the exact loaded FEM: element connectivity and node coordinates must match the
deck before geometric checks run. A native probe established that the observed
NX 2606 TET4/WEDGE6 XML face number is one greater than the index accepted by
`FEElement.GetCornerNodesOnFace`. Passing the XML number directly selected a
different face; an out-of-range wedge index returned an empty list. This was an
inspection-adapter calibration finding, not evidence of an incorrect solver
boundary. The audit explicitly restricts supported element types and indices.

The reusable `boundary_geometry.py` checker validates linear triangular and
quadrilateral faces on an expected axis-aligned rectangular plane. It rejects
inconsistent coordinates, off-plane nodes, duplicate/degenerate faces,
nonmanifold or overlapping adjacency, disconnected patches and interior free
edges. Its scope is surface-patch coverage, not volumetric mesh validity.
Coordinate tolerance is 1e-7 mm; area/perimeter relative tolerance is 1e-6.

Both reference patches had 718 faces / 594 nodes; both refined patches had
950 faces / 764 nodes. Each covered 400 mm² with 80 mm perimeter, one connected
component and no interior free edges. Inlet x=1 mm and opening x=161 mm were
preserved, with y/z ranging from 1 to 21 mm. All selected connectivity and
coordinates matched their decks. Native FEM files and modified flags were
unchanged. This resolves the geometric boundary-selection check left open by
the two-level core-refinement comparison; boundary-layer convergence and
volumetric topology checks remain separate.

Evidence: `native-remesh-boundary-patches.json` and
`native-element-face-index-mapping.json` under `tests/simcenter/evidence`.
Six local fault-injection checks cover gaps, overlaps, duplicate faces, changed
coordinates, nonfinite inputs and a valid rectangle. The helper is deployed to
the dedicated Simcenter source without an NX restart; it is not yet a separate
public tool or a general curved-boundary inspector.

### Visible progress versus bridge activity

A user-reported static GUI was checked against a fresh VM screenshot and a live
native call. Simcenter displayed `refined_flow_r1.sim`, while its viewport still
showed plain geometry and a previous solve-check listing. The bridge responded
normally; recent read-only audits and background solves had not automatically
selected a result view. `show_refined_progress.py` displayed the completed
`Pressure - Element-Nodal` field in Pa, preserving modified flags. The native
listing panel requires `ListingWindow.CloseWindow()`; `Close()` alone closes
its output stream and does not hide the panel. A subsequent full-desktop capture
verified the pressure contour and legend in the visible Simcenter window.

The control panel now says “NX ready” between bridge calls. If a simulation
observer thread is alive, it lists the watched job IDs separately; native calls
and manual mode retain priority. This uses in-memory thread liveness only—no
filesystem reads, process scans or NX calls are added to the UI timer. The
`simulation_observers` status field explicitly distinguishes observer liveness
from solver state; zero observers does not imply an idle solver. Use
`nx_sim_job_status` for durable job state and numerical audit tools for residuals.
Code/testing work outside NX is not represented as native activity. Continuous
residual progress in the panel and automatic milestone-result display remain
UX work.

The update was applied to the running dedicated host without restarting it or
changing document flags. Native verification covered the no-active-observer
state and live panel update; active/dead observer and native/manual priority
cases passed local UI tests. A native running-job panel check remains pending
the next required benchmark solve. Evidence:
`tests/simcenter/evidence/native-ui-observer-status.json`.

The initial VM capture was cropped by Windows DPI virtualization. The scoped
`capture_vm_desktop.ps1` fixture sets process DPI awareness before reading screen
bounds and captures the complete physical-pixel desktop. It writes to a temporary
PNG and atomically replaces the published image after saving, preventing retrieval
of a partially written file. The corrected capture
was 3024×1890 rather than the earlier 2419×1512 image. This affects VM screenshots,
not numerical result data. Native display evidence is
`tests/simcenter/evidence/native-refined-visible-pressure.json`; screenshots are
retained outside Git in the task outputs.

A subsequent live check found that Windows PowerShell converted the null backup
argument in `File.Replace` into an invalid path, leaving the published screenshot
unchanged. Publication now runs inside a C# helper with an actual null argument.
The deployed capture produced a fresh 3024×1890 PNG. Independent UI heartbeat
samples advanced while reporting no native operation or observer; the solver
process inventory was empty. A static result view in this state means NX is idle,
not that a simulation is still progressing. Local implementation work does not
update the NX view.

### Variant preflight and associated solver files

`variant_plan.py` implements read-only preflight for a standalone SIM/FEM and
its direct CAD associations. It hashes all source files within a shared byte
budget, generates distinct destination basenames, rejects existing folders and
loaded-name collisions, and fails on unresolved/duplicate/not-fully-loaded
dependencies. Modified sources are rejected by default. Explicit
`saved_snapshot=true` plans only the saved disk revisions and lists excluded
unsaved sources; it neither saves nor discards their edits. The canonical plan
hash changes when source bytes or the plan change. No directory is created by
preflight. Public tools expose planning, creation and receipt recovery.

Native verification on the refined analysis rejected its modified SIM by
default and successfully planned the saved snapshot with three source files
(23033982 bytes). Five local tests cover destination/name conflicts, unsaved
sources, unresolved/duplicate dependencies, byte limits, workspace escape and
source-revision changes. Native evidence:
`tests/simcenter/evidence/native-variant-preflight.json`.

Installed `UFClone.SetDefAssocFileCopy` / `AskDefAssocFileCopy` bindings were
inspected before use. A separate native clone with copying disabled returned
false on readback and created exactly the SIM, FEM, CAD and clone log—no BUN,
solver log or other associated artifacts. Source hashes and loaded modified
flags were preserved. This option does not prove all external analysis inputs
are packaged, and omitted result files are not fresh results. Reopening this
specific copy was not tested because its basenames conflict with the displayed
refinement's dependencies; generated names in the reusable preflight avoid that
conflict. Evidence: `native-clone-associated-api.json` and
`native-clone-without-results.json`; fixture: `probe_clone_without_results.py`.
`variant_clone.py` adds a durable disk transaction: persist the exact plan and
accepted state, run native naming/dependency preflight, persist cloning intent,
clone, verify source/output hashes and loaded document flags, then persist the
committed receipt. Existing folders are inspected, never implicitly overwritten
or retried. Committed replay checks output hashes; incomplete or altered receipts
reject retry. Failures retain partial files and diagnostics. Associated solver
files are excluded, and result freshness is not inferred from the clone.

The deployed transaction created three independent native files from the refined
analysis and replayed its receipt without another native clone. Source hashes,
loaded modified flags and work/display documents were preserved. Eleven local
transaction tests cover replay, output tampering, incomplete states, source
changes, native initialization/load/iteration/naming failures, unexpected dry-run
writes and partial file creation. These injected tests do not establish native
interruption recovery. Evidence: `native-variant-transaction.json`; fixture:
`verify_variant_transaction.py`. General variant readback remains incomplete.

Opening this generated-name copy verified that its SIM resolves the cloned FEM
and that both FEM CAD associations resolve the cloned CAD. The CAD association
was initially unloaded and was explicitly opened before verification. Native
readback retained 261589 elements, 98632 nodes, the Flow solution and zero outlet
head-loss coefficient. Original file hashes and existing loaded modified flags
were unchanged. The cloned SIM is now the work/display document. This verifies
direct dependency rebinding, not all selections, external inputs or result
freshness. Evidence: `native-variant-transaction-reopen.json`; fixture:
`verify_variant_transaction_reopen.py`.

The public workflow is `nx_sim_variant_plan(document, folder, name)` → inspect
the returned mapping and `plan_sha256` → `nx_sim_variant_create` with the same
arguments, `expected_plan_sha256` and an operation ID. Use explicit
`saved_snapshot=true` on both calls only when saved revisions are intended.
After interruption, `nx_sim_variant_receipt(folder, expected_plan_sha256)` needs
no live document ID and never repeats native cloning. Creation leaves the
current work/display documents unchanged; open the returned SIM explicitly for
dependency inspection. All paths are checked on both MCP and NX boundaries.

Real MCP verification created a new standalone Flow variant, rejected an
incorrect plan hash, retrieved the committed receipt, replayed the operation ID
and rejected a workspace escape. Evidence: `native-variant-tools-mcp.json`;
reproducible fixture: `verify_variant_tools_mcp.py`. Complete external dependency
packaging, general selection equivalence and native interrupted-clone recovery
remain pending. No results or solver execution are implied by these tools.

### Orthotropic material authoring

`nx_sim_orthotropic_material(document, name, conductivities_w_m_k,
 density_kg_m3, heat_capacity_j_kg_k, provenance)` creates a local constant-property
orthotropic material in an explicit, workspace-owned millimeter FEM. Conductivities
are ordered in material X/Y/Z coordinates. The response includes committed scalar
expressions with native unit names and symbols, provenance, and a material reference
scoped to the session and owner generation. Creation activates the FEM and retains
an undo mark. It does not assign a collector/frame, save, solve, or add a library material.
The existing isotropic material operation remains available.

The NX 2606 native handler was deployed and exercised through the UI-thread probe
in `examples/simcenter/verify_public_orthotropic_material.py`. It created and read
back `[12, 7, 0.4]` W/(m K), 1900 kg/m³ and 900 J/(kg K), rolled the test material
back, restored the previous work/display documents, and checked all modified flags.
Public MCP acceptance also passed schema discovery, invalid axis-count rejection,
creation, same-operation replay with the same material reference, and duplicate-name
rejection using `examples/simcenter/verify_orthotropic_material_mcp.py`. Subsequent
native inventory confirmed exactly one material from the replayed creation. The adapter's three-axis conduction benchmark evidence above does not
establish general tensor, temperature-dependent, or mesh-converged support.


`nx_sim_materials(document, offset=0, limit=20)` returns paginated FEM-local material
references, native types, provenance and actual property expressions/units. Individual
inspection failures are explicit. It does not activate documents or read global library
materials. Pages reflect a live collection: restart paging after a mutation.
`examples/simcenter/verify_material_inventory_native.py` verified page size one across
two materials, provenance, absence of duplicate creation after MCP replay, and preserved
work/display documents and modified flags. This inventory test exercises the native
handler; public transport acceptance for inventory also passed in
`examples/simcenter/verify_material_inspection_mcp.py`. Seven local tests
cover paging and invalid page arguments; these do not replace native API evidence.


`nx_sim_collectors(document, offset=0, limit=20)` lists FEM mesh collectors and
inspects solid collector material assignment, inheritance and stored orientation.
It returns typed owner-scoped references, length units and a SHA-256 state token.
The token covers collector identity, assignment and stored frame, not material
property changes; it is omitted on incomplete native inspection. Non-solid collectors
are explicitly marked unsupported for assignment inspection. Selector 0 means the
stored frame is ignored in the verified export; selector 1 selects Cartesian axes.
Other native selectors are reported without an inferred interpretation.

Native verification against the solved OrthoZR1 FEM returned the expected orthotropic
material and cyclic Cartesian frame, stable repeat results, and unchanged document
flags/work/display state (`verify_collector_inventory_native.py`). Public MCP tests
verified both inventory tools, repeated collector state identity and invalid-page
rejection (`verify_material_inspection_mcp.py`). No assignments or solves are performed
by these inspection tools. Assignment and orientation mutation tools remain pending.

### Explicit solid material assignment

`nx_sim_assign_material(document, collector, material, expected_state_sha256)`
requires live typed references and the collector hash from `nx_sim_collectors`.
The material and collector must both belong to the selected FEM. The operation
rejects stale/incomplete state before activation, sets an explicit material assignment
(inheritance false), verifies readback and unchanged orientation, and retains an undo
mark. It neither saves nor solves. Native errors trigger rollback with explicit
rolled-back/partial reporting. The state hash does not cover material property edits.

`verify_material_assignment_native.py` exercised a temporary material in the isolated
OrthoZR1 FEM. The instrumented native run passed stale-state rejection, assignment
readback, orientation preservation, restoration of the original collector state,
removal of the temporary material, and preservation of document flags. An earlier
attempt returned an empty error diagnostic; independent inspection confirmed restored
assignment/frame, no temporary material and an unmodified FEM before retry. Its cause
remains unresolved. Public MCP assignment acceptance subsequently passed change/readback, same-operation
replay, rejection of the old state hash, and restoration of the original assignment
(`verify_material_assignment_mcp.py`). The final collector state matched the initial
state; the FEM was active and reported unmodified. No save or result revalidation
was performed.
Four local tests cover pre-activation state conflict, readback mismatch rollback,
rollback failure reporting and successful readback; these are simulated seams.


### Cartesian material frame editing

`nx_sim_material_frame(document, collector, expected_state_sha256, origin_mm,
x_axis, y_axis)` sets an explicit Cartesian frame on a solid collector in a
millimeter FEM. Origin is part-absolute millimeters; X and Y must be perpendicular
unit vectors, with Z their right-handed cross product. The operation binds to the
inspected collector state, validates ownership, activates the FEM, verifies native
frame readback and unchanged material assignment, and returns the new state hash.
Failures roll back; save and solve are separate operations. Existing results must
not be assumed fresh after a frame edit.

The deployed native handler passed stale-state rejection, identity-axis assignment,
material preservation and rollback to the original cyclic frame in the isolated
OrthoZR1 FEM (`verify_material_frame_native.py`). The fixture also checked the full
original collector state, document flags and work/display restoration. Public MCP
transport acceptance passed invalid-axis rejection, edit/readback, same-operation
replay, stale-state rejection and restoration of original axes and origin
(`verify_material_frame_mcp.py`). Restoration creates a new native frame identity;
it does not reuse the old frame tag or establish result freshness. The existing three-axis
conduction evidence establishes the internal adapter's axis mapping, not arbitrary
frame mesh convergence or general tensor support.


An internal `thermal_state.capture_thermal_state` reader now fingerprints live solid
material assignments, stored frames and evaluated constant thermal properties without
using native dirty flags. Runtime tags are excluded so equivalent frame values are
comparable after reopen/recreation; journal identifiers and owner paths remain part
of the scoped identity. No fingerprint is returned for empty or incompletely inspected
solid state. It does not cover mesh, loads, contacts, flow or full-model freshness.
`verify_live_thermal_state.py` verified stable repeat readback of the OrthoZR1 properties
and cyclic axes with document flags preserved. Integration into immutable preparation
manifests, launch guards and result audits remains pending; current result APIs continue
to report freshness as not verified. This reader alone is not stale-result protection.

### Live thermal revision guard integration

New Thermal preparations capture the scoped live solid thermal fingerprint before
export, verify it after export, and store it in the immutable job manifest. Missing
or incomplete constant-solid state is rejected for this preparation route. Accepted-job
preparation replay and native launch compare live state with that snapshot before
launch intent. Flow preparations retain their existing path; this fingerprint does
not cover flow models. Legacy manifests without the snapshot remain compatible but
cannot gain live-state verification retroactively.

Result job audits now compare the live snapshot as well as saved dependencies and
result artifacts. A detected thermal material/frame mismatch returns
`model_result_freshness: stale`; matching scoped state still returns full freshness
as `not_verified`, because mesh, loads, contacts and other dependencies remain separate.
Missing snapshots are explicit missing evidence. This does not certify numerical or
engineering acceptance.

The integrated preparation/launch/audit logic passes local tests, including rejection
before launch intent with unchanged saved files, and stale classification despite
matching saved artifacts. `verify_live_thermal_change.py` natively verified a frame
change alters the fingerprint and rollback restores the original fingerprint and
collector state. A fresh native prepare/solve/audit cycle using the new manifest
field remains pending; this narrower native test is not that end-to-end acceptance.

The new manifest path has now completed a fresh native cycle using
`launch_live_revision_mcp.py` and a disconnected/reconnected
`audit_live_revision_mcp.py`. Job `live-revision-thermal-01` prepared a new isolated
SIM/output directory, recorded the live thermal snapshot, launched once, reached
observed solver exit, released its launch gate, retrieved temperatures, audited the
result association, and displayed a native contour. The live thermal state matched
the immutable snapshot. The associated BUN matched the observer's artifact hash.

The 756-node synthetic conduction result was 20..1270.049560546875 °C. Its 1250.04956 K
rise differs from the analytic constant-property value 1250 K by 0.0495605 K
(0.00396484375%). This repeats the same coarse benchmark, not a mesh-refinement study.
The result hash was `f01c09c7a66031e503a413454fb2066874fd6076a53e17d177c51cedfb0536c4`.
NX VerifyResults reported `results_changed`; the SIM had unsaved edits after solving,
while all three saved dependency hashes matched preparation. Full revision/freshness
therefore remained unverified. The material/frame match does not override those
findings. Native stale detection after a deliberate post-solve edit and broader
mesh/load/contact revision coverage remain separate acceptance work.

Native post-solve stale detection now passes through public MCP
(`verify_stale_thermal_result_mcp.py`). The test audited the completed
`live-revision-thermal-01` job, changed the isolated FEM's material frame, reactivated
the SIM and audited the same result without solving. Its BUN still matched the
observer artifact, while the live thermal fingerprint differed. Both top-level
`result_freshness` and job-binding `model_result_freshness` returned `stale`.
Restoring original axes/origin returned the scoped comparison to `matches` and full
freshness to `not_verified`. No save or solver launch occurred. A separate second
logical run verified top-level propagation after that response inconsistency was
fixed. The original frame values were restored; native frame identity may differ.
This establishes frame-change stale detection, not complete mesh/load/contact/flow
revision tracking or physical acceptance.

Further contact investigation enumerated the entire installed Thermal load catalog
(17 entries) and constraint catalog (11 entries) without changing work/display
or document flags (`inspect_contact_categories.py`). Neither contains a conductive
contact/resistance descriptor. The constraint catalog does contain `Thermal Association
Zone` and `Simple Radiation to Environment`. Both exact catalog names were then tested
with `CreateBcBuilderForConstraintDescriptor` in the isolated Thermal context; both
returned `Invalid LBC neutral name`. Builder destruction/undo completed and document
flags remained unchanged (`inspect_thermal_association_constraints.py`).
These findings show that catalog presence alone is insufficient to establish an
accepted creation descriptor. They do not establish module/licence absence, conductive
contact support, radiation authoring, or numerical correctness. The descriptor tool's
`builder_creation_tested_by_call: false` distinction remains necessary. Native journal
mapping is still needed for these operations; benchmark B remains incomplete.

Installed `uf_sf.h` documents a Simulation work-part prerequisite for load/constraint
descriptor enumeration as well as solution-step discovery. The descriptor adapter
previously enforced it only for steps. It now rejects all categories from FEM/CAD
context with `NX_SIM_DOCUMENT_NOT_ACTIVE` and an activation next step before UF calls.
`verify_descriptor_context_guard.py` natively verified rejection of all three
categories from a FEM, successful constraint enumeration after SIM activation,
and restored work/display documents and modified flags. This fixes a prerequisite
validation bug; it does not resolve rejected contact/radiation builder names.
No separate neutral-name translation API was found in these installed UF descriptor
functions; no unsupported substitute API was introduced.

### Bounded fan-law table scaling

Fan-table creation now accepts optional `scaling_rpm_range` and `scaling_validity`
metadata. Both are required to authorize subsequent fan-law estimates; the range
must contain the source RPM. `nx_sim_scale_fan_table(document, source_field, name,
rpm)` creates a separate native table from a verified MCP-owned source field in the
active SIM. It preserves reference density, pressure convention, linear interpolation,
undefined out-of-range behavior and the unsupported reverse-flow policy. Flow scales
with RPM and pressure with RPM squared for the assumed same-geometry similarity.
It does not attach a fan, solve, predict acoustics/motor heat, or calculate operating
points. Use explicit validity limits supported by the study's evidence.

Derived provenance is now `assumed`, including original provenance and source
checksum/RPM/density. The shared Python FanCurve scaling method uses the same logic;
it no longer incorrectly preserves a measured/datasheet label for derived samples.
Seven local tests cover scaling, provenance, source preservation and rejected speeds.
`verify_fan_scaling_native.py` verified 1000→1100 RPM native table creation/readback:
flow [0, 0.00022, 0.00044] m³/s and pressure [1.21, 0.605, 0] Pa. The source table,
work/display documents and modified flags were preserved; the derived test table
was removed by rollback. Public MCP transport acceptance, a solved RPM comparison,
and save/reopen of derived provenance remain pending.

Public fan scaling acceptance now passes (`verify_fan_scaling_mcp.py`) on a new
analysis copy: out-of-range RPM rejection, native creation, same-operation replay,
save/close/reopen, exactly one derived table, retained derived provenance/samples,
unchanged source manifest and stale document-reference rejection. No solver was
launched by that acceptance fixture.

The solver-level RPM study setup created a separate `rpm_flow_r1.sim` from the
refined duct baseline, then stopped before curve creation or launch: the inlet's
legacy `Synthetic mode probe` field lacks MCP manifest attributes and is therefore
correctly excluded by managed fan-table enumeration. Read-only native inspection
(`inspect_legacy_duct_fan.py`) verified its actual samples as flows
[0, 0.0002, 0.0004] m³/s and pressures [1, 0.5, 0] Pa with scale factor 1. The 1000 RPM
reference comes from the synthetic benchmark fixture, not a native RPM attribute.
This evidence enables explicit reconstruction of a managed study source without
silently relabelling the unmanaged table. The scaled-flow solve remains pending;
`launch_rpm_flow_mcp.py` must not be rerun unchanged because its SaveAs destination
already exists. Continue from the inspected copy and preserve its retained receipt.

The configured RPM study exposed a save/export workflow defect: `nx_sim_save`
created `.nx-mcp-save-backups` inside the SIM's output folder, then preparation
rejected the nonempty directory. Save backups now go to workspace-root
`simcenter-save-backups/<unique-id>/`, retaining verified original bytes while
keeping solver directories clean. Existing backups are retained in place. Local
save tests assert the new placement. Native `launch_rpm_flow_clean_mcp.py` verified
SaveAs to a fresh directory, explicit save with an external backup, successful
preparation and launch of `rpm-flow-1100-r1`. No solver was dispatched by the failed
preparation. The earlier configured copy and all backups remain intact.

The 1100 RPM duct job `rpm-flow-1100-r1` subsequently completed natively, survived
MCP client disconnection, reached observer-verified exit and released its launch gate.
The configured residual criterion passed at iteration 13. Native rounded output
reported 0.0002848 m³/s and 0.4269 Pa at the fan, with 0.009955% mass imbalance.
The scaled synthetic curve gives 0.4268 Pa at that flow; the 0.0001 Pa difference is
within the existing 0.0002 Pa rounding allowance. The earlier 1000 RPM refined-duct
baseline reported 0.0002530 m³/s and 0.3674 Pa. This is a fan-law sensitivity result,
not supplier performance validation or an acoustic prediction. The study reused the
refined FEM and did not author geometry or mesh changes. Complete cross-run physics
fingerprinting and broader mesh convergence remain separate validation requirements.
Fixtures: `continue_rpm_flow_mcp.py`, `launch_rpm_flow_clean_mcp.py`,
`audit_rpm_flow_mcp.py`; retain failed setup receipts when reproducing recovery.

The 2026-09-08 GUI check found a live UI heartbeat with no active native
operation or solver, but the viewport still showed the RPM duct geometry and
the previous validation report. Agent mode intentionally retained input.
Displaying the completed pressure field and closing the Listing Window restored
visible feedback; the desktop capture confirmed the contour. NX rejected the
postview name `1100 RPM pressure (Pa)` with code 3960043; a direct rename
reproduced that rejection. `MCP pressure 1100 RPM` succeeded. The exact naming
restriction is not yet established. The RPM completion script now explicitly
shows the pressure result after its log audit; this does not change numerical
acceptance or establish general automatic UI progress reporting.

### Uniform surface flux and volume generation: native authoring

The internal `distributed_heat` adapter creates the installed `Heat Flux` and
`Heat Generation` loads with explicit `HeatFlux_Metric5` (W/m²) and
`HeatGeneration_Metric3` (W/m³) units. NX 2606 native tests committed and read back
10,000 W/m² on a SIM occurrence face and 100,000 W/m³ on a SIM occurrence body.
Both tests rejected an identical-target duplicate and verified rollback of load,
constraint and expression identities plus document modified flags. The previous
work/display documents were restored. The volume fixture creates a new isolated
CAD/FEM/SIM set and must use a fresh folder for another logical run.

Evidence: `tests/simcenter/evidence/native-surface-flux-authoring.json` and
`native-volume-generation-authoring.json`; fixtures:
`examples/simcenter/verify_distributed_heat_native.py` and
`verify_volume_heat_native.py`. Builder and unit discovery receipts are retained
in the same evidence directory. The first volume attempt on an existing heated
body was rejected before assignment, so testing moved to a new analysis.

The public `nx_sim_distributed_heat` tool exposes both distributions. Native MCP
acceptance verified discovery, typed-target rejection, replay returning the same
load, duplicate rejection, save/close/reopen and stale-document rejection. Readback
after reopening preserved both SI values, target journal identities and provenance.
Volume inputs accept direct FEM body references from `nx_sim_faces`, resolving
them to the corresponding SIM occurrence. Evidence:
`tests/simcenter/evidence/native-distributed-heat-mcp.json`; fixture:
`examples/simcenter/verify_distributed_heat_mcp.py`. Numerical temperature comparisons and geometry-integrated power are covered below;
independent conservation validation remains pending. Duplicate detection rejects exact targets. The distributed-heat tool also checks
face/body ownership overlap as described below.
The response reports the sum of density multiplied by native area/volume; it does not
subtract intersecting or overlapping geometry. No surface-flux or
volumetric-generation numerical pass is claimed.

### Distributed-heat numerical checks

Two isolated native solves exercised the public heat-density tool on a
100 × 10 × 10 mm bar, k = 200 W/(m·K), with x=0 fixed at 20°C and
otherwise adiabatic boundaries. The 3 mm linear-tetrahedral mesh has 756 nodes.
An end-face flux of 10,000 W/m² gives 1 W and analytical rise qL/k = 5 K.
NX returned 24.99998093°C maximum, 0.00038147% error in rise. Uniform
100,000 W/m³ generation gives 1 W and rise gL²/(2k) = 2.5 K. NX returned
22.50045967°C maximum, 0.01838684% error in rise. Both satisfy a 1% temperature
comparison tolerance; the fixed boundary is exactly 20°C at reported precision.

Exported length and force conversion factors are both 1000, so the log power
unit is mN·mm/s and 1 W = 1,000,000 native units. Both logs report rounded
input and sink flow of 1,000,000. Reported deviation values are 8.516 and
0.04962 respectively; they are retained without asserting that they represent
independent global energy-balance integrals. Full conservation acceptance, mesh
refinement, and full-model freshness remain separate. These checks validate
constant-property load behavior, not product cooling or the complete A–F suite.

Fixtures: `launch_surface_flux_mcp.py`, `audit_surface_flux_mcp.py`,
`launch_volume_generation_mcp.py`, `audit_volume_generation_mcp.py` and
`compare_distributed_heat.py` under `examples/simcenter`. Each launch uses a
fresh isolated folder and persistent job ID; do not rerun it with the same paths.
Comparison receipts and bounded native logs are in `tests/simcenter/evidence`,
including `distributed-heat-numerical.json`. Both solver jobs reached terminal
state, released their gates and displayed native temperature contours.

The distributed-heat preflight now reports `mutation_outcome: not_started` for
invalid selections and duplicate loads, preserves native error codes, and gives
a corrective next step. Explicit partial outcomes are not overwritten. Native
MCP testing confirmed unchanged loads and document state for both rejections
(`native-heat-preflight.json`).

`nx_sim_distributed_heat` now reports `total_power_w`, per-target measures and SI
measure units. It uses documented `UF.Sf.FaceAskArea` and
`BodyAskVolumeAndCentroid` on the direct FEM prototypes, with explicit mm²→m²
and mm³→m³ conversion. Unsupported units, ownership or nonpositive/invalid
measures fail before authoring. The 100 mm bar returned 100 mm² end area and
10,000 mm³ volume. A fresh public two-cube test returned 1 W surface heating
and 0.1 W volumetric heating, and passed replay/save/reopen checks. Evidence:
`native-heat-measures.json` and `native-distributed-heat-power.json` in
`tests/simcenter/evidence`; public fixture `verify_distributed_heat_power_mcp.py`.
Totals are sums over selected geometry, not geometric unions or solved heat flow.
Only constant-density direct-FEM cases are verified; this is not a complete
scenario energy audit or independent solver conservation result.

Distributed heat now accepts `overlap_policy="reject"` (default) or
`"allow_additive"`. Existing Heat Load, Heat Flux and Heat Generation targets are
checked using native CAE face/body types and `UF.Sf.FaceAskBody`. A face and its
body conflict; different faces on one body do not. Explicit additive mode permits
separate intended face/body contributions, returns the overlapping load names
and journal IDs, and still rejects exact-target duplicates. Unknown target kinds
fail inspection rather than being silently ignored. Distinct-body geometric
intersections are outside this ownership check.

Native testing on the isolated two-body model verified default rejection with
`not_started`, explicit additive creation/readback, and rollback preserving all
load/constraint/expression identities and document flags. Evidence:
`tests/simcenter/evidence/native-heat-overlap.json`; fixture:
`examples/simcenter/verify_heat_overlap_native.py`. The same ownership check now applies to `nx_sim_heat_power` with the same
explicit additive policy. Scenario import already rejects any nonempty load
collection before authoring; it retains that stronger creation-only rule. Public MCP acceptance of both additive options is recorded below.

Total-power overlap verification (`native-total-heat-overlap.json`, fixture
`verify_total_heat_overlap_native.py`) rejected a body assignment overlapping
an existing face load, then committed an explicit additive 0.1 W contribution
and rolled it back with unchanged document flags and creation identities.
Exact body-target duplicates are rejected even in additive mode. The subsequent public MCP test below covers transport and policy persistence.

Both additive options passed public MCP lifecycle acceptance in an isolated SIM
copy. Default face/body-overlap rejection preceded explicit additions of 0.25 W
internal power and 500 W/m² surface heating. Replay returned the same load
references. Save/close/reopen preserved four total loads, both added values,
provenance and the explicit `allow_additive` policy. The policy is stored as
`NX_MCP_HEAT_OVERLAP_POLICY` and exposed by `nx_sim_loads`; older loads without
that attribute return null. Source SIM files and shared FEM geometry were not
modified by the copy's load edits. Evidence:
`tests/simcenter/evidence/native-additive-heat-mcp.json`; fixture:
`examples/simcenter/verify_additive_heat_mcp.py`. This verifies authoring and
lifecycle behavior, not the physical validity of an additive heat assumption.

### Thermal fingerprint version 2

New thermal preparation records combine the material/frame fingerprint with
observed load and constraint properties, evaluated scalar-expression values,
and target journal/owner/subentity identities. A constant heat load change now
alters the fingerprint even before saving. Native testing added a surface load
to the solved volume benchmark, detected the changed hash, and verified that
rollback restored the original fingerprint and document flags. Evidence:
`tests/simcenter/evidence/native-boundary-state.json`; fixture:
`examples/simcenter/verify_boundary_state_native.py`. Local coverage also verifies
that a parameter's evaluated value changing with an unchanged formula changes
the hash, and property read failures prevent a hash.

Version 1 prepared records lack this scope and compare as `not_verified` against
version 2; prepare a fresh job instead of reusing an old preparation. Completed
legacy results remain inspectable without a freshness assertion. Prepare and
launch consumers have been rebound to the version 2 capture function. Native MCP prepare/change/launch-refusal acceptance for version 2 passed, as
described below.

Uninspected reference properties are explicitly listed (for example thermostat,
reference-temperature-set and temperature-file properties). Mesh, simulation
objects, contacts, solution settings, referenced-file content and full dynamic
field coverage remain outside this fingerprint. Matching observed state still
returns full-model freshness as `not_verified`; it is not proof that these
uninspected dependencies are unchanged.

The public `verify_boundary_guard_mcp.py` fixture prepared a fresh isolated SIM
copy with fingerprint adapter 2, added a heat load, and called `nx_sim_launch`.
It returned `NX_SIM_LIVE_STATE_CHANGED`, comparison `changed`, and mutation
outcome `not_started`. The job stayed `accepted` with its original immutable
manifest; no launch intent was committed. Live-state comparison now precedes
saved-file revision validation so this case reports its specific cause.
Evidence: `tests/simcenter/evidence/native-boundary-guard-mcp.json`. The test
copy remains deliberately changed and unsaved; its prepared inputs must not be
reused for that changed state. Original source files were preserved.

### Solution Monitor cancellation investigation

The installed NXOpen SimSolveManager documentation exposes solve/prerequisite
methods but no Stop/Abort method in that class. The THERMALFLOW installation
contains MayaMonitor.exe, Xtmgmon.exe and MapMonitor.exe. A read-only process
check confirmed the dedicated process is `simcenter3d` (PID 6584), distinct
from the original `ugraf` CAD process.

The Siemens presentation hosted by Maya HTT distinguishes Stop (retains
intermediate files and produces results) from Abort (removes temporary files,
no postprocessing/restart):
https://help.mayahtt.com/kb/files/overview_thermal_solver_files.pdf, page 5.
This documents UI semantics, not an external command/API or verified 2606
automation contract. No process-kill substitute or stop-file convention was used.

An isolated `monitor-probe-r1` Flow run completed and released its gate, with
pressure postview readback. A bounded standalone-monitor accessibility capture
returned no window controls; that does not prove monitor absence or unavailable
cancellation. The separate reused Simcenter-window artifact was malformed and
apparently contained old data, so it is excluded from acceptance evidence.
No Stop/Abort action was invoked. Next work requires a fresh, uniquely named,
atomic UTF-8 accessibility capture during a confirmed live monitor, bound to
the exact solver job before any control invocation. Native cancellation remains
unverified. Evidence: `solution-monitor-discovery.json`, `monitor-controls.json`,
and `native-monitor-probe-finish.json` under `tests/simcenter/evidence`.

Coupled property-specific follow-up: installed `UFSf.PropertyAskNameNx`,
`PropertyAskTypeNx` and `PropertyAskValueNx` enumerated 102 solution and 30
solver properties in 0.016 seconds with unchanged document flags. The coupled
reference is type 16; scalar value access returns 1765131. UF reports
`Thermal Solution Parameters` whereas earlier NXOpen association used
`Thermal Parameters`; reconcile these identities before further assignment.
`Solve Thermal` reads true. This is control inspection, not solve readiness.
Evidence: `tests/simcenter/evidence/coupled-property-values.json`.

Coupled mapping reconciliation (2026-09-08): NXOpen enumerates and resolves
`Thermal Parameters`; UF exposes `Thermal Solution Parameters`, which NXOpen
rejects as a named-table key (3520001). Keep the working NXOpen association; this
is an API-layer naming difference, not proof of an incorrect thermal assignment.
The coupled reference remains null. Native readback preserved all loaded document
modification flags. Evidence: `coupled-reference-mapping.json`.

Alternative template route was bounded to copies of shipped metric Multiphysics
and ThermalFlow SIM templates. Both contain zero solutions and zero modeling
tables, so neither supplies a populated coupled-control descriptor. Initial
inspection stopped on unloaded dependencies; the subsequent inspection reused the
loaded copy and retained load warnings. The ThermalFlow template references
`FemThermalFlowMetric.fem`, absent from the copied folder, and reports read-only
modified status. Do not solve or save these incomplete template copies. No installed
original was changed. Inspection took 0.953 seconds; candidate scan 0.328 seconds.
Evidence: `coupled-template-{candidates,load-failure,tables}.json`. These findings
do not establish a licence problem. This template-discovery route is exhausted.

Next coupled route: test whether native input export resolves documented defaults
with the empty table reference (whether it is optional is unverified), using a minimal two-region fixture and
explicit exported-control readback. Treat required-control errors as blockers;
do not claim defaults are adequate before inspecting exported values. This can
advance interface/mesh prerequisites without inventing a descriptor.

Coupled development fixture now exists (2026-09-08): two adjoining
20×10×5 mm bodies, separately meshed as Linear Tetrahedron and Fluid Linear
Tetrahedron at 5 mm. Solid k=200 W/(m K), rho=2700 kg/m³, Cp=900 J/(kg K);
air rho=1.2 kg/m³, viscosity=1.81e-5 Pa s, k=0.0257 W/(m K), Cp=1005 J/(kg K).
All are assumed constant benchmark properties, read back from committed native
objects. Native creation: 5.047 s; each mesh: 0.266 s. Saved FEM/SIM, then saved
an isolated SIM copy for export, preserving the original SIM file.

Export-only check failed in 0.86 s with NX code 1 and no solver deck. The last
native coupled setup report specifically rejects a single transient step and
requires a steady-state step or multiple transient steps. Mesh, material,
physical-property, modeling-object and load/constraint checks report no errors;
this does not validate absent boundary conditions or solid/fluid interfaces.
No error about the empty coupled-control reference was reported. Next action:
explicit steady-step configuration, native readback, and fresh export check.
No solver was launched. Evidence: `coupled-development-{build,export,setup-report}.json`.
Reproduction fixture: `examples/simcenter/build_coupled_development_fixture.py`
(stage receipt prevents blind reruns); export experiment:
`examples/simcenter/export_coupled_development_input.py`. Interfaces, boundaries,
convergence, balances and refinement remain incomplete.

Steady-step export gate passed on the generic two-region development fixture.
Changing native step `Solution Type` from 1 to 0, with committed readback, removed
the single-transient-step error. All native setup checks reported no errors.
Export took 1.765 seconds and produced a well-formed 126-element/68-node deck.
The deck identifies Coupled Thermal-Flow, step type 0, and retains coupled
parameter value -1; its solver meaning remains unverified. Empty controls do not
block export for this fixture. Air/solid interfaces and boundaries remain unvalidated;
no solver ran. Evidence: `coupled-steady-export.json` and `coupled-steady-deck.xml`.
The first copy attempt rejected a duplicate loaded basename before mutation; retained
in `coupled-steady-name-rejection.json`.

The `coupled_steady` action has been added to the local flow-setup implementation
with rollback/readback tests (six targeted tests pass). Deployment and public MCP
verification of that action remain pending; native experiment verification must
not be confused with verification of the newly exposed action.

Coupled boundary/steady public verification (2026-09-08): deployed flow, native
and server modules with 57 registered Simcenter handlers. Public MCP discovery
contains `coupled_steady`; invocation, same-operation replay and isolated SIM save
succeeded. Six targeted local flow tests pass. Public receipt:
`coupled-steady-public.json`. Save/reopen verification of these new boundaries is
still pending.

Native boundary authoring committed one 1 m/s inlet, one opening and one 0.1 W
solid heat source. The fixture's JSON serialization failed on the returned native
SimLoad; subsequent read-only inspection recovered all three objects and their
selections without retrying creation. Fixture serialization is corrected. Retain
`coupled-boundaries-native.json` (failure) and `coupled-boundaries-recovered.json`
(actual committed state). Opening pressure mode is 1 but its pressure value is
still the unset sentinel: explicitly assign atmospheric absolute pressure, 0 Pa relative pressure and inlet temperature before
export/solve. No boundary completion claim is made.

The existing deck contains zero shared node IDs between solid and fluid element
sets. This does not prove missing solver coupling, but geometric contact alone
is insufficient evidence. Establish native solid/fluid coupling and audit its
heat exchange in results. The deck predates the new saved boundaries and is stale
for the current SIM. Next batch: explicit ambient/inlet/outlet values, interface
configuration/readback, fresh deck and prerequisite checks.

Coupled environment export discrepancy (2026-09-08): native field readback
returned Fluid Temperature=20 C, Absolute Pressure=101325 Pa, and initial
temperature=20 C. Outlet readback and export correctly represent 101325 Pa
absolute plus 0 Pa relative; inlet exports 1000 mm/s and heat exports 100000
native power units (0.1 W under the deck unit factors). Setup reports no errors.
However, exported ambient Fluid Temperature and Absolute Pressure are both zero.
A fresh-copy experiment using scalar-field-wrapper setters and Ambient Pressure
mode 1 still exports zeros. Thus mode selection alone does not resolve the issue;
do not repeat that hypothesis or claim ambient temperature is correctly applied.
No solver ran. Preserve both decks and export receipts in
`tests/simcenter/evidence/coupled-{boundaries,environment}-{export.json,deck.xml}`.

Next action: inspect native ambient field ownership/evaluation and descriptor
keys versus the actual exported AmbientConditions section, or author explicit
Inlet Conditions using an installed, verified descriptor. Do not accept a
zero-temperature inlet as the requested 20 C benchmark. Solid/fluid interfaces
remain unverified. Current active analysis copy is
`ui-benchmarks/E-environment-wrapper-20260908-r1/coupled_environment_r1.sim`;
its shared FEM remains the original 126-element development FEM.

Ambient field investigation (2026-09-08): the documented
`GetScalarFieldPropertyValue` returns FieldExpression objects for Absolute
Pressure and Fluid Temperature, containing 101325 Pa and 20 C. Wrapper getters
subsequently return wrappers with no direct Expression (field-backed). The first
inspection failed its document-flag assertion, so getter initialization is a
possible side effect; the repeat preserved flags. This is not proof of general
read-only behavior. Evidence: `coupled-ambient-{getter-failure,fields}.json`.

One bounded edit experiment used the installed SDK's
`FieldExpression.EditFieldExpression(..., [], True)` and
`PropertyTable.SetScalarFieldPropertyValue`, then saved/exported a fresh copy.
Export returned without setup error but again wrote zero for both ambient values.
Neither generic scalar setters, scalar wrappers, pressure mode 1 nor explicit
FieldExpression update resolves this discrepancy. Do not repeat those routes.
Evidence: `coupled-field-export.json`, `coupled-field-deck.xml`. Next supported
route to investigate: explicit Inlet Conditions table with native/exported
temperature readback, retaining the global-ambient limitation until resolved.
No coupled solve has run; interfaces remain unverified. Active work/display copy:
`ui-benchmarks/E-environment-field-20260908-r1/coupled_field_r1.sim`.

Explicit inlet-condition discovery, bounded 2026-09-08: the modeling-table factory
rejects the exposed reference name `Inlet Conditions` (3520001, 0.031 s).
Installed command metadata exposes `Flow Boundary Condition` and `Flow Surface`,
but the simulation-object builder rejects both command subIds as neutral names
(1543292; 0.047/0.063 s). Rollback verified no created objects remained. These
command labels are not callable descriptor names. Inlet Conditions property type
reads -10; its native interpretation is not established. Do not repeat these
names or infer support from the UI commands. The UF load/constraint registry
contains 17/18 entries and exposes only initial-fluid constraints for the related
search; it does not supply the missing simulation-object neutral names.
Evidence: `coupled-inlet-conditions-probe.json`, `inlet-command-metadata.json`,
`coupled-flow-object-probes.json`, `coupled-flow-descriptor-registry.json`.

The precise coupled milestone blockers remain ambient field export (zero despite
valid native expressions) and verified solid/fluid interface construction. No
licence failure is established. Next investigate a supported native journal
recording or object-specific builder/reference API; stop descriptor-name guessing.
The existing small meshed fixture, explicit heat/velocity/pressure, steady export
and public steady action remain available. No solver launched in this discovery
batch.

Final ambient setter/update experiment (2026-09-08): explicit native
UpdateManager.DoUpdate returned zero errors before save/export, yet ambient
pressure and fluid temperature still exported zero. Preserve
`coupled-update-export.json`, `coupled-update-deck.xml`, and the compact
`coupled-ambient-reproducer.json` (deck checksum, requested/exported SI values,
failed comparison). This exhausts the update prerequisite route; do not rerun
setter variations without new evidence. A native UI journal of the solution's
ambient-temperature edit is the next targeted evidence source. User assistance
was requested; recording/manual handoff has not started. Current active copy:
`ui-benchmarks/E-environment-update-20260908-r1/coupled_update_r1.sim`.

User declined manual journal assistance; continue API investigation without
preparing a manual handoff. Vendor documentation supports ambient time tables:
https://help.mayahtt.com/kb/topics/analyze_diurnal_heating_of_a_rover.html
(boundary representation example, not validation of this coupled fixture).

Constant ambient time-table experiments: generic FieldWrapper setter was rejected
with "This Property type does not support this interface"; exception path rolled
back the environment edit. The supported scalar field wrapper accepted tables
with identical values at t=0 and 1e6 s; native data and reference readback passed.
Export still writes ambient pressure/temperature zero and an empty FieldTableList.
No solver ran. Evidence: `coupled-table-export.json`,
`coupled-time-table-export.json`, `coupled-time-table-deck.xml`. This is not a
working alternative. Current copy:
`ui-benchmarks/E-ambient-time-table-20260908-r1/coupled_time_table_r1.sim`.

Next distinguish export omission from solver interpretation through a bounded
translator/solver diagnostic using the tiny fixture, with explicit non-acceptance
status and solver log inspection of actual ambient values and thermal connections.
Before launch, extend/review coupled job guards and preserve persistent job identity;
never present a run at unintended conditions as the requested benchmark.
