# Validation and upstream PR readiness

## Source provenance

The five implementation commits import the previously deployed patches in order, starting at upstream `179086b6de28a53d340132aca7678fa6ed03b422`. All tracked runtime files, original examples and package metadata were compared byte-for-byte with the deployed source and matched. The subsequent documentation commit adds these notes and a configurable copy of the public visualization runner. No runtime changes were made while creating the fork.

## Historical live-NX evidence

The deployed version is `0.2.0.dev2`, tested against Siemens NX v2606 in a graphical session. The latest visualization release passed seven native feature groups and eleven public MCP groups, with 77 tools discoverable through the installed Windows stdio and HTTP transports. Its targeted local checks passed 37 tests with one platform skip. These are scoped results from the preceding implementation/deployment session, not a claim that upstream's entire CI suite passed.

The eleven public groups covered schema/UI availability, underconstrained sketch diagnostics, color/transparency restoration, visibility restore ordering, native section lifecycle, nested collision highlighting, nested isolation, occurrence appearance without prototype recoloring, assembly sections preserving geometry, a fully constrained sketch fixture, and highlight cleanup on manual handoff. Native viewport images were retrieved with checksum verification. Positive and negative plane normals were visually checked on separated colored solids.

Native validation does not cover every NX version, reference-set configuration, legacy tool, solver conflict state or geometry topology. Photorealistic rendering and material assignment remain outside this release.

## Fresh fork comparison — 5 September 2026

Both source trees were tested on the same macOS/Python 3.12 environment with localhost socket access. The first sandboxed attempt was discarded as an environment-limited run; the following results use the required socket access:

| Check | Unmodified upstream | Imported fork |
|---|---|---|
| Complete non-real-NX pytest suite | 161 passed, 1 skipped, 1 deselected | 174 passed, 7 failed, 1 skipped, 1 deselected |
| Ruff lint | Passed | 24 findings in imported implementation/test files |

Command, with the checkout's `src` first on `PYTHONPATH`:

```sh
python -m pytest -q -p no:cacheprovider -m "not real_nx" --basetemp /tmp/nx-tests
python -m ruff check .
```

The seven failing tests are new relative to this upstream baseline:

- `tests/test_certified_server.py::test_experimental_file_tools_still_enforce_workspace_boundary`: the path is rejected, but the integration envelope returns `NX_INVALID_ARGUMENT` where upstream expects `NX_PATH_OUTSIDE_WORKSPACE`.
- `tests/test_nx_executor.py::test_open_save_export_and_close_part_lifecycle` and `test_mcp_sidecar_bridge_and_nx_executor_complete_core_workflow`: the fake NX module lacks the `StepCreator` enum required by the deployed export implementation.
- `tests/test_tools/test_measure.py::TestMeasureDistance::test_distance_success`, `TestMeasureAngle::test_angle_success`, `TestMeasureAngle::test_angle_custom_value`, and `tests/test_tools/test_modeling.py::TestSweep::test_sweep_success`: legacy mock tests return errors after shared lookup helpers changed. The mock/lookup contract needs reconciliation. These failures do not establish that angle or sweep are broken in real NX; those tools remain unverified there.

Do not weaken tests merely to obtain a green run. Preserve stable public error codes, update fake seams to model verified API behavior, and add focused lookup regression coverage. Formatting, lint, mypy and coverage gates need a complete pass before an upstream merge request. Mypy, coverage and the hosted OS/Python matrix were not rerun during this fork import.

## Reproduce public visualization checks

`examples/validate_visual_tools.py` is an explicit live test, not part of ordinary pytest. It creates and saves disposable parts/assemblies, changes the active part and control mode, and leaves its fixture files for inspection. Run it only against a dedicated test NX session and workspace; it does not restore an unrelated user's session.

Configure `NX_MCP_TEST_ENDPOINT` with a reachable HTTP MCP endpoint, `NX_VISUAL_RESULTS` with a local result directory, and `NX_FIXED_SKETCH_FIXTURE` with a workspace-relative part containing a fully constrained first sketch with persistent constraints. Create that simple fixture in NX first. No vendor or private CAD fixture is bundled. The runner assumes the endpoint's access is already configured; adapt its client transport if your endpoint requires additional authentication headers.

```powershell
$env:NX_MCP_TEST_ENDPOINT = 'http://127.0.0.1:8765/mcp'
$env:NX_VISUAL_RESULTS = 'visual-results'
$env:NX_FIXED_SKETCH_FIXTURE = 'fixtures/fully-constrained.prt'
python examples/validate_visual_tools.py
```

The runner writes JSON results and native PNGs. It is the previously exercised runner with formatting and explicit endpoint configuration; the copied runner was syntax/lint checked, not executed against NX again for the fork import.

## Proposed upstream sequence

1. **Compatibility fixes:** isolate legacy imports from sidecar dependencies, repair NX2606 API use and sketch coordinate handling, and reconcile the core/legacy tests and stable error codes.
2. **Recovery and references:** agree on operation IDs, lifecycle semantics, checkpoint behavior and the public result contract. This is an architecture change requiring maintainer review.
3. **Graphical bridge and capture:** propose the serialized UI scheduler, manual handoff, capability gating and native viewport artifact delivery with NX-version-specific evidence.
4. **Inspection and visual tools:** propose assembly interference/clearance, highlighting, sections, appearance and solver diagnostics on the agreed foundations.

The imported commits preserve deployment history but are not all independently PR-ready: some later commits depend on broad earlier hardening. Extract smaller patches with their own tests when preparing submissions. Discuss the architecture with the maintainer before asking them to review the complete integration. No pull request has been opened as part of this fork import.

## Follow-up quality release: 0.2.0.dev3

All seven import-time test failures and the 24 lint findings were addressed. The full local suite now passes 183 tests (one platform skip), lint and sidecar mypy pass. The smoke workflow checks undo before export's save boundary and reacquires the sketch reference after undo. Added lookup tests check journal identifiers, case normalization, ambiguity and deduplication. Fake NX collections now expose the iterable interface verified in NX, and the STEP fake models the installed enum and a solid-bearing result. These remain fake seam tests, not native feature certification.

Whole-project branch coverage is approximately 51%, below the inherited 78% gate. The gate is deliberately retained: GUI/NX modules have substantial uncovered Python paths despite their separate live-NX acceptance checks. A green functional suite does not resolve that coverage gap. Consult the current GitHub workflow result for the exact total and platform matrix.

Versioned offline build, dependency locks, install and rollback procedures are documented in [releases](releases.md).

Final dev3 deployment evidence is summarized in [the validation receipt](dev3-validation.json). All nine hosted test combinations, eleven deployed native MCP groups, Windows stdio/HTTP checks, isolated rollback testing and the Windows release build passed. The retained full-project coverage gate reports 50.63% against 78%.

## Recovery coverage release: 0.2.0.dev4

The expanded local suite passes **303 tests**, with one platform skip and one real-NX deselection. Whole-project line/branch coverage reaches **79.59%**, above the unchanged **78%** gate. No coverage exclusions or threshold reductions were introduced. Stateful fake NX seams cover rollback, stale references, save boundaries, interrupted uploads, display snapshots, native inspection cleanup, coordinate/transform contracts and UI handoff failures. These tests verify Python control flow and arguments, not the Siemens geometry kernel.

Fault injection reproduced three runtime defects before repair:

- A failed screenshot-builder `Destroy()` skipped restoration of the original rendering style. Restoration now runs in a nested `finally`.
- A failed sketch `Deactivate()` skipped rollback of the temporary work region. Rollback now runs independently of deactivation; rollback failure is explicitly reported as partial.
- The executor overwrote an inspection handler's explicit partial-cleanup outcome with `not_started` when no outer undo mark existed. It now preserves that outcome, while a real outer rollback still determines its own result.

The deployment follows the existing offline release and saved-session procedure. Historical dev3 results and receipts above remain unchanged as historical evidence.
