"""Version-scoped evidence for public tools; never a live licence assertion."""

# Each scope refers to actual public MCP native verification, not API reflection.
PUBLIC_EVIDENCE = {
    "nx_sim_distributed_heat": (
        "native-distributed-heat-mcp.json",
        "Surface-flux and volumetric-generation SI authoring, typed-target rejection, replay, duplicate rejection and save/reopen values/units/target journals/provenance; numerical acceptance and total-power integration separate",
    ),
    "nx_sim_variant_plan": (
        "native-variant-tools-mcp.json",
        "Saved standalone Flow SIM/FEM/CAD plan with unique destinations and actual source hashes; unsaved rejection checked by separate native preflight",
    ),
    "nx_sim_variant_create": (
        "native-variant-tools-mcp.json",
        "Native standalone Flow saved-file clone, plan-hash mismatch rejection and operation-ID replay; native interruption recovery untested",
    ),
    "nx_sim_variant_receipt": (
        "native-variant-tools-mcp.json",
        "Committed native clone receipt retrieval with output-hash verification and workspace-escape rejection; incomplete/tampered receipt handling tested locally only",
    ),
    "nx_sim_job_status": (
        "native-gate-inspection-mcp.json",
        "Completed native job status with compact default and optional unclaimed-gate diagnostics; claimed/corrupt-gate inspection covered locally only",
    ),
    "nx_sim_result_identity": (
        "native-result-binding-mcp.json",
        "K0 native result hash matched the recorded job artifact, unrelated analysis rejected, live unsaved revision reported without certifying freshness; changed-file/fake-artifact coverage local only",
    ),
    "nx_sim_flow_setup": (
        "native-coupled-setup-mcp.json",
        "Coupled step and four parameter tables, native descriptor rollback, public MCP retry/existing-table rejection/save; coupled solution controls unresolved, no coupled solve",
    ),
    "nx_sim_close": (
        "native-sim-close-mcp.json",
        "SIM and inactive FEM save/close/retry/reopen, stale references, unsaved and in-use FEM rejection, preserved other flags; partial native close failure covered locally only",
    ),
    "nx_sim_open": (
        "native-sim-open-mcp.json",
        "Fresh millimeter SIM/FEM copies, loaded reuse and switching, missing-path rejection, basename conflict preflight and preserved other document flags; missing-dependency recovery untested",
    ),
    "nx_sim_create_benchmark": (
        "native-scenario-multi.json",
        "Two disjoint 10 mm thermal blocks at explicit origins; native CAD/FEM body count; no mesh/solve acceptance",
    ),
    "nx_sim_scenario_preview": (
        "native-scenario-preview-mcp.json",
        "CSV scenario, live FEM body mapping, separate energy totals, invalid ID/missing mapping/workspace rejection and preserved document state",
    ),
    "nx_sim_scenario_apply": (
        "native-scenario-multi.json",
        "Two-source Thermal transaction, native second-source failure rollback, MCP retry, save/reopen powers/provenance/targets and stale-reference rejection; reopened SIM marked modified",
    ),
    "nx_sim_descriptors": (
        "native-descriptors-mcp.json",
        "Inactive Thermal SIM native load/constraint names, filtering, paging and preserved document state; simulation-object/contact names excluded",
    ),
    "nx_sim_launch": (
        "native-auto-observer-cycle.json",
        "Prepared Flow launch with automatic terminal observer surviving MCP client disconnect; no cancellation or NX restart test",
    ),
    "nx_sim_observe_job": (
        "native-auto-observer-cycle.json",
        "Reuses a live automatic observer without another solver launch; terminal record visible to a reconnected client",
    ),
    "nx_sim_release_job": (
        "native-gate-release-mcp.json",
        "Post-run gate fixture release against verified real artifacts, retry and preserved document flags; not automatic full lifecycle",
    ),
    "nx_sim_flow_log": (
        "native-fan-operating-points-mcp.json",
        "Two completed native duct jobs: residual observations, SI boundary flows and fan operating points with explicit pressure-unit/convention limits; no numerical acceptance",
    ),
    "nx_sim_prepare_solve": (
        "native-preparation-mcp.json",
        "Flow export, 186765 elements, saved dependency binding and accepted-job replay; no launch",
    ),
    "nx_sim_save": (
        "native-conduction-setup-save.json",
        "Existing isolated FEM/SIM save, backup hashes and replay",
    ),
    "nx_sim_export_input": (
        "native-thermal-export-mcp.json",
        "Thermal input export, 2658 elements, retry and overwrite rejection",
    ),
    "nx_sim_temperature": (
        "native-temperature-mcp.json",
        "Constant Kelvin face boundary, replay and save/reopen",
    ),
    "nx_sim_heat_power": (
        "native-heat-power-mcp.json",
        "Single-body total internal watts, duplicate rejection and save/reopen",
    ),
    "nx_sim_steady_thermal_controls": (
        "steady-controls-public-launch.json",
        "Explicit temperature stopping in K, public validation/replay/export; native persistence and optional relative-balance authoring separately verified",
    ),
    "nx_sim_temperature_material": (
        "temperature-material-public.json",
        "Isotropic temperature-dependent conductivity/heat-capacity and constant density: native/public creation, rollback, assignment, replay, FEM/SIM reopen and export verified; numerical behavior unverified",
    ),
    "nx_sim_heat_schedule": (
        "heat-schedule-public.json",
        "Time/power table binding, scale, coverage, replay and save/reopen verified; native target persistence, post-commit rollback and scaled export audited separately; no transient numerical acceptance",
    ),
    "nx_sim_scalar_table": (
        "scalar-tables-public.json",
        "Registered time/temperature scalar tables: native unit conversion, public replay, validation and save/reopen; no load/material binding or numerical acceptance",
    ),
    "nx_sim_scalar_tables": (
        "scalar-tables-public.json",
        "Paged compact/full registered table inventory, SI samples, metadata checksum and stale-document rejection; native corrupted metadata rejection separately verified",
    ),
    "nx_sim_emissivity_override": (
        "radiation-objects-public.json",
        "Thermal constant both-side emissivity: native/public authoring, replay, persistence, faces, units and export; top/bottom native authoring separately tested without numerical interpretation",
    ),
    "nx_sim_enclosure_radiation": (
        "radiation-objects-public.json",
        "Thermal deterministic enclosure with radiative environment, primary faces and empty secondary slot: native/public lifecycle and export; environment-off native authoring separately tested; no view-factor acceptance",
    ),
    "nx_sim_environment_radiation": (
        "radiation-environment-public.json",
        "Thermal simple environment radiation, constant effective emissivity, three temperature sources; native/public replay, units, targets, persistence and export; no numerical radiation acceptance",
    ),
    "nx_sim_convection": (
        "convection-environment-public.json",
        "Thermal-only constant coefficient and fluid/radiative/specified temperature selectors; native/public replay, units, face readback, persistence and export",
    ),
    "nx_sim_constraints": (
        "native-constraint-inventory-mcp.json",
        "Paged constraint properties and assigned targets",
    ),
    "nx_sim_loads": (
        "native-load-inventory-mcp.json",
        "Paged load properties and targets including empty target slots",
    ),
    "nx_sim_temperature_result": (
        "native-temperature-result-mcp.json",
        "Nodal Celsius extrema, invalid indices and preserved document flags",
    ),
    "nx_sim_show_temperature": (
        "native-temperature-postview.json",
        "Temperature postview field/unit readback and replay; multiple existing views untested",
    ),
    "nx_sim_mesh_quality": (
        "native-mesh-quality-mcp.json",
        "All-mesh native quality and criteria readback on a 2658-element thermal FEM",
    ),
    "nx_sim_solutions": (
        "native-solutions-mcp.json",
        "Paged solution references and active-state inspection; no solve readiness claim",
    ),
    "nx_sim_select_solution": (
        "native-solution-switch-mcp.json",
        "Switch between distinct solutions, reject foreign ownership, restore original selection",
    ),
    "nx_sim_initial_conditions": (
        "initial-conditions-public.json",
        "Automatic/uniform selectors, Kelvin readback, replay, save/reopen and Celsius export; no numerical acceptance",
    ),
    "nx_sim_transient_setup": (
        "native-transient-setup-mcp.json",
        "Three output times, committed step values, replay and extra-step rejection; no solve in this test",
    ),
    "nx_sim_steps": (
        "native-steps-mcp.json",
        "Paged inactive-solution steps and End Time readback; active solution preserved",
    ),
    "nx_sim_fan_table": (
        "native-fan-tables-mcp.json",
        "Static synthetic table, SI sample readback, typed reference, replay and duplicate-name rejection",
    ),
    "nx_sim_fan_tables": (
        "native-fan-tables-mcp.json",
        "Full and compact table inventory; metadata and sample readback; no operating-point calculation",
    ),
    "nx_sim_objects": (
        "native-sim-objects-mcp.json",
        "Paged Inlet/Opening descriptors, targets and committed properties; preserved document flags",
    ),
    "nx_sim_head_loss": (
        "native-head-loss-mcp.json",
        "Opening resistance creation, compare-and-set update, conflict/no-op and replay in an isolated Flow SIM; no porous-volume support or native failure-injection claim",
    ),
    "nx_sim_assign_fan": (
        "native-assign-fan-mcp.json",
        "Static fan assignment to an existing Flow inlet, replay, wrong-kind rejection and outer rollback; no solve",
    ),
}


def public_evidence(version):
    from nx_mcp.simcenter.server import NON_MODEL, READ_ONLY

    exposed = READ_ONLY | NON_MODEL
    return {
        "scope": "Indexed public-tool regression evidence; not a complete capability inventory",
        "exposed_tool_count": len(exposed),
        "indexed_tool_count": len(PUBLIC_EVIDENCE),
        "unindexed_tools": sorted(exposed - PUBLIC_EVIDENCE.keys()),
        "unindexed_semantics": "No assessment in this evidence index; consult the per-operation capability and benchmark records",
        "tools": [
            {
                "tool": name,
                "status": "implemented_and_tested"
                if version == "v2606"
                else "implemented_but_untested",
                "tested_version": "v2606",
                "tested_scope": scope,
                "evidence": "tests/simcenter/evidence/" + file,
                "current_session_test": "not_performed_by_discovery",
                "licence_checkout": "not_tested",
            }
            for name, (file, scope) in PUBLIC_EVIDENCE.items()
        ],
        "remaining_work": {
            "generic_async_solve_and_cancel": "native launch, automatic terminal observation and successful-output release exposed; cancellation, running/failure binding and NX restart acceptance incomplete",
            "coupled_cooling_acceptance": "not_complete",
            "thermal_contact": "Native/public total R/G authoring, persistence/export and 200-element explicit-stopping resistance artifact benchmark verified; whole-model freshness not established",
            "detailed_rotating_fans_and_acoustics": "not_validated; module availability must be established separately",
            "full_model_result_freshness": "not_established; live SIM may be modified after solving",
            "exact_screenshot_resolution": "native postview export ignores requested device dimensions in observed test",
        },
    }
