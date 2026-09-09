"""Explicit, opt-in Simcenter tools using the existing bridge and receipts."""

from typing import Literal

READ_ONLY = {"nx_sim_capabilities", "nx_sim_documents"}
NON_MODEL = {"nx_sim_create_benchmark"}


def nx_sim_capabilities():
    """Inspect installed Simcenter/NX CAE APIs and solver files. Distinguishes API presence from tested operations and successful numerical benchmarks. Does not change licensing or launch solvers. Thermal installation does not imply coupled airflow availability."""


def nx_sim_documents(offset: int = 0, limit: int = 20):
    """List loaded CAD, FEM and SIM documents with typed document references, owner paths, units, modified flags and work/display roles. offset >= 0, limit 1..100. Read-only; does not activate, load or save documents."""


def nx_sim_create_benchmark(
    folder: str,
    length_mm: float = 100.0,
    width_mm: float = 10.0,
    height_mm: float = 10.0,
    analysis_type: Literal["thermal", "flow", "coupled_thermal_flow"] = "thermal",
    block_origins_mm: list[list[float]] | None = None,
):
    """Create isolated millimeter block CAD, FEM and SIM documents in a new workspace folder. Optional block_origins_mm supplies 1..16 finite XYZ origins for equal-sized, nonoverlapping solid blocks; default is one block at zero. Coordinates are millimeters in CAD absolute space. Touching blocks are allowed; interfaces are not assigned automatically. analysis_type selects thermal (default), flow, or coupled_thermal_flow. Thermal includes the verified steady thermal step; flow choices create the native solution and return allowed steps/default properties but require further flow configuration. The block is geometry, not a validated fluid domain. No mesh, fan, boundaries or solve is implied. Uses installed NX MULTIPHYSICS identifiers verified on NX 2606. Leaves the analysis displayed and saves only new files. Basenames are unique per folder; use returned paths. Existing folders are rejected. Failure closes new documents and reports retained partial files without deleting or saving production CAD. Supply operation_id for safe retry."""


def nx_sim_mesh(document: str, size_mm: float = 5.0):
    """Generate linear tetrahedral meshes for all bodies in an explicitly selected millimeter FEM. document is a current part ID from nx_sim_documents. Requires no existing mesh. Uses a visible undo mark and rejects empty mesh results; returns committed settings, element/node counts and owner paths. Does not save or claim mesh quality/convergence acceptance. Remesh and fluid meshing are not yet supported by this operation."""


NON_MODEL.add("nx_sim_mesh")


def nx_sim_material(
    document: str,
    name: str,
    conductivity_w_m_k: float,
    density_kg_m3: float,
    heat_capacity_j_kg_k: float,
    provenance: str,
    assign_all_solid_collectors: bool = False,
):
    """Create an isotropic thermal material in a selected FEM using explicit SI properties. document is a live part ID from nx_sim_documents. Positive finite values and nonempty provenance are required; names must be unique in that FEM. With assign_all_solid_collectors=true, explicitly replace the material on every solid mesh collector in that FEM; other collectors are untouched. Returns committed material properties and collector readback. Does not save, solve or add to the global material library. Failure rolls back within the activated FEM. Temperature-dependent and anisotropic properties are not supported by this operation."""


NON_MODEL.add("nx_sim_material")


def nx_sim_orthotropic_material(
    document: str,
    name: str,
    conductivities_w_m_k: list[float],
    density_kg_m3: float,
    heat_capacity_j_kg_k: float,
    provenance: str,
):
    """Create a constant-property orthotropic material in a live millimeter FEM. Supply exactly three positive SI conductivities in material X/Y/Z order, positive density and heat capacity, and property provenance. Returns actual committed expressions/units and a lifetime-scoped material reference. Does not assign collectors or orientation, save, solve, or modify the global material library. Activates the FEM and retains an undo mark; failures report rollback outcome. Directional thermal conduction is natively tested for three Cartesian axis permutations on NX 2606; general tensor and temperature-dependent properties are not supported. Use operation_id for safe retry."""


NON_MODEL.add("nx_sim_orthotropic_material")


def nx_sim_materials(document: str, offset: int = 0, limit: int = 20):
    """Inspect local materials in an explicit FEM without activation or mutation. offset >= 0; limit 1..100. Returns typed material references, native type, provenance, actual property expressions/units and per-property inspection failures. Coordinates are material axes; this does not imply collector assignment or frame orientation. Paging reflects the current live collection; restart paging after changes. Does not load library materials or solve."""


READ_ONLY.add("nx_sim_materials")


def nx_sim_collectors(document: str, offset: int = 0, limit: int = 20):
    """Page FEM mesh collectors with typed references. Solid collectors include actual material assignment, inheritance, stored Cartesian frame, explicit length units and a state hash. The hash binds identity, assignment and frame, not material property edits; failed inspection returns no hash. Other collector types are listed with unsupported assignment inspection. offset >= 0; limit 1..100. Read-only; preserves work/display documents. Restart paging after mutation. A stored frame with native selector 0 is ignored by the verified solver export; selector 1 uses Cartesian axes."""


READ_ONLY.add("nx_sim_collectors")


def nx_sim_assign_material(
    document: str, collector: str, material: str, expected_state_sha256: str
):
    """Assign one FEM-local material to one solid mesh collector using live typed IDs. Requires state_sha256 from nx_sim_collectors; rejects changed or incompletely inspected state before mutation. The hash covers assignment/frame, not material property changes. Activates the FEM, replaces inheritance with an explicit assignment, preserves orientation, and returns actual committed state plus an undo mark retained by the bridge. Does not save or solve. Native failures roll back and report partial recovery if rollback fails. Use operation_id for safe retry."""


NON_MODEL.add("nx_sim_assign_material")


def nx_sim_material_frame(
    document: str,
    collector: str,
    expected_state_sha256: str,
    origin_mm: list[float],
    x_axis: list[float],
    y_axis: list[float],
):
    """Set a Cartesian material frame on one solid collector in a millimeter FEM. Use live document/collector IDs and state_sha256 from nx_sim_collectors. origin_mm is part-absolute XYZ; x_axis/y_axis are perpendicular unit vectors in part coordinates, with Z their right-handed cross product. Rejects stale state, invalid axes and unsupported owners before mutation. Activates FEM, verifies actual frame and unchanged material assignment, retains undo and rolls back failures. Returns committed collector state and new hash. Does not save, solve or claim existing results remain fresh. Use operation_id for safe retry."""


NON_MODEL.add("nx_sim_material_frame")


def nx_sim_activate(document: str):
    """Display and activate an already-loaded FEM or SIM by its document ID, then enter the installed simulation application. Returns actual application and work/display documents. Preserves unsaved edits and does not save, close or recreate files. Application/document switching may invalidate undo marks; use saved analysis copies across such boundaries. Unsupported documents are rejected before activation."""


NON_MODEL.add("nx_sim_activate")


def nx_sim_result_inventory(document: str, offset: int = 0, limit: int = 50):
    """Page result loadcases, iterations, native times/units and available fields for the active SIM document ID. offset >= 0; limit 1..200. Preserves displayed postviews. Metadata may describe older results: freshness is explicitly not_verified. Does not solve, save, activate documents or certify results. Reacquire result indices after model or result changes."""


READ_ONLY.add("nx_sim_result_inventory")


def nx_sim_result_identity(
    document: str, maximum_bytes: int = 1_073_741_824, job_id: str | None = None
):
    """Inspect associated result-file paths, sizes, SHA256 hashes and NX verification for an active SIM document ID. maximum_bytes is a positive total hashing budget (default 1 GiB); files outside the workspace are rejected. Does not load fields, solve, save or alter result associations. File identity and NX verification do not establish current-model freshness: result_freshness remains not_verified and engineering_accepted remains false. Preserve a pre-solve dependency manifest and job identity for that separate audit. Missing files and files changing during inspection are errors. Optional job_id binds to an existing job in simcenter-jobs: rejects a different analysis/solution, compares the associated result with the observed job artifact, and audits supplied pre-solve dependency hashes and current modification flags. maximum_bytes covers results plus dependencies. A SIM hash mismatch can reflect solve metadata; it does not establish a physics change. No audit result certifies numerical validity or complete model freshness."""


READ_ONLY.add("nx_sim_result_identity")


def nx_sim_flow_setup(
    document: str,
    action: Literal["create_step", "attach_defaults", "coupled_steady"],
    name: str = "Flow",
):
    """Configure an already active NX MULTIPHYSICS Flow or Coupled Thermal-Flow SIM by live document ID. create_step creates its first native step named name; attach_defaults creates and associates three Flow tables or five verified Coupled Thermal-Flow tables using name as a prefix. coupled_steady sets the sole active coupled step to steady state with native readback, retaining its name (name is only used by the creation actions). The coupled property key is mapped to the documented Thermal-Flow Coupled Solution Parameters descriptor; this is not complete coupled solver configuration. Returns actual committed properties. Existing steps or assigned tables are rejected, not replaced. Defaults and raw enum values are reported without claiming a steady or transient solve configuration. Does not save, mesh, assign fluid regions/boundaries or solve. Native rollback is attempted on failure, with explicit partial status if recovery fails. Supply operation_id for safe retry. Requires no known solver process."""


NON_MODEL.add("nx_sim_flow_setup")


def nx_sim_flow_convergence(
    document: str,
    residual: float,
    flow_imbalance_fraction: float,
    iteration_limit: int,
):
    """Set convergence controls on an active NX MULTIPHYSICS Flow SIM by document ID. Requires attached Flow Solution Parameters and verified RMS mode 1. residual and flow_imbalance_fraction are finite dimensionless fractions strictly between 0 and 1 (0.001 means 0.1%); iteration_limit is an integer 1..100000 for steady flow. Enables the flow-imbalance criterion and returns before/actual values. Does not save, launch or cancel a solve. Use only when no solver job is running. Changes require prior results to be revalidated. Repeating identical settings is a no-op; failed mutations attempt verified rollback. These requested controls are not evidence of achieved convergence. Supply operation_id for safe retry."""


NON_MODEL.add("nx_sim_flow_convergence")


def nx_sim_job_status(
    job_id: str,
    job_folder: str = "simcenter-jobs",
    include_manifest: bool = False,
    include_evidence: bool = False,
    check_processes: bool = False,
    include_launch_gate: bool = False,
):
    """Inspect a persistent Simcenter job without launching, retrying or changing it. job_folder is its workspace-relative storage folder; job_id is its durable ID. Returns recorded state/revision, observation time, request hash and retry prohibition. Optional manifest/evidence expand the compact default. include_launch_gate reports persistent workspace ownership and the owning job, or an explicit unknown state for incomplete/inconsistent records. It creates no lock files, does not expire or release a claim, and an unclaimed gate is not proof that no solver is running. check_processes=true rechecks previously recorded Windows process identities using PID, creation time and executable; missing/incomplete bindings report unbound. Live observations remain separate from recorded job state and never establish solve success or permit relaunch. Incomplete records return unknown. Missing jobs and workspace escapes are errors. Requires the bridge to respond; automatic process discovery, background monitoring and cancellation are not provided by this tool."""


READ_ONLY.add("nx_sim_job_status")


def nx_sim_save_as(document: str, path: str):
    """Save the active SIM under a new workspace .sim path, creating parent folders. Requires a live SIM document ID and a basename not already loaded. Existing files are rejected. Copies current live edits into the new SIM and preserves the original disk file; the active document acquires the new path. Returns new references and actual work/display paths. FEM/CAD remain shared: this is not an independent geometry variant, and copied result associations are not freshness evidence. Reacquire IDs after copying; never edit a shared FEM as though it were private. Failure retains files and reports partial state. Supply operation_id for safe retry."""


NON_MODEL.add("nx_sim_save_as")


def nx_sim_dependencies(document: str, offset: int = 0, limit: int = 50):
    """Inspect direct SIM/FEM/CAD document associations for a standalone FEM analysis. document is a live SIM ID; offset >=0, limit 1..100. Returns paged document references, ownership roles, paths, units, work/display roles, load and unsaved flags, and file availability. Does not activate, load, save or copy anything. Unloaded CAD associations and unenumerated assembly children are explicit. This is not a complete analysis package manifest: recursive components, external property/field files and solver/result dependencies remain excluded. Assembly FEM inspection is currently unsupported."""


READ_ONLY.add("nx_sim_dependencies")


def nx_sim_export_input(document: str):
    """Export and inspect native NX MULTIPHYSICS Thermal, Flow or Coupled Thermal-Flow input from the active SIM ID. Requires a workspace subfolder containing only that saved SIM; use nx_sim_save_as to create it. Existing artifacts are rejected before export. Returns actual XML/artifact paths, hashes, mesh counts and translator diagnostics; retains partial files on failure. Does not save edits or launch a solver. XML validity is not solve readiness or convergence evidence. Coupled export compares constant Celsius ambient readback with XML. Specified ambient pressure requires an expression-backed Pa value and matching XML; field-backed pressure is rejected. Altitude mode leaves stored absolute pressure inactive. These guards do not establish regional density, full field state or physical acceptance. Supply operation_id for safe retry."""


NON_MODEL.add("nx_sim_export_input")


def nx_sim_faces(document: str, offset: int = 0, limit: int = 50):
    """Page face selections for the active SIM with one direct standalone FEM occurrence. offset >=0; limit 1..100. Returns typed SIM occurrence face references, prototype FEM body references and native face bounding boxes in FEM part-absolute coordinates with readable units. Bounds are not transformed into assembly coordinates and are not exact surface geometry. No nested assembly traversal. References use the existing session/owner lifecycle; reacquire after geometry, mesh or manual-session changes. Does not activate, save, select onscreen or modify geometry."""


READ_ONLY.add("nx_sim_faces")


def nx_sim_emissivity_override(
    document: str,
    faces: list[str],
    emissivity: float,
    name: str,
    provenance: str,
    side: Literal["both", "top", "bottom"] = "both",
):
    """Create native Override Thermal Emissivity on 1..1000 distinct SIM CAE face IDs. Requires active NX MULTIPHYSICS Thermal. emissivity is a constant dimensionless value in [0,1]; side maps to native both/top/bottom selectors. Native side meaning depends on solid/shell geometry; no shell interpretation or numerical heat-transfer claim is made. Readback verifies value/units, selector, face targets, solution membership and provenance. Returns a typed simulation object, available in nx_sim_objects. Does not assign optical material, save, solve or remove other assignments; conflicting/overlapping existing overrides require inspection by the caller. Visible undo with verified creation rollback. Supply operation_id for deduplicated retry."""


NON_MODEL.add("nx_sim_emissivity_override")


def nx_sim_enclosure_radiation(
    document: str,
    faces: list[str],
    name: str,
    provenance: str,
    include_radiative_environment: bool = True,
):
    """Create native Enclosure Radiation with deterministic calculation on 1..1000 distinct SIM CAE face IDs. Requires active NX MULTIPHYSICS Thermal. include_radiative_environment controls the native ambient-inclusion selector; ambient temperature is a separate unresolved dependency. Assigns documented target set 0 and verifies the second slot stays empty. Does not construct/check a closed cavity, assign emissivity, calculate view factors, save or solve. Monte Carlo/GPU methods and secondary-slot authoring are not exposed. Returns actual properties, typed simulation object, face/solution membership and provenance; inspect via nx_sim_objects. No numerical radiation acceptance is implied. Visible undo with verified creation rollback. Supply operation_id for retry deduplication."""


NON_MODEL.add("nx_sim_enclosure_radiation")


def nx_sim_environment_radiation(
    document: str,
    faces: list[str],
    effective_emissivity: float,
    name: str,
    provenance: str,
    temperature_source: Literal[
        "fluid_ambient", "radiative_ambient", "specified"
    ] = "radiative_ambient",
    temperature_k: float | None = None,
):
    """Create native Simple Environment Radiation on 1..1000 distinct SIM face IDs. Requires active NX MULTIPHYSICS Thermal. effective_emissivity is a dimensionless constant in [0,1], not an optical material assignment. Uses top-side effective-emissivity mode; shell-side and enclosure/view-factor options are not provided. temperature_source selects fluid/radiative ambient or specified; only specified accepts a finite nonnegative temperature_k in Kelvin. Ambient effective values are not resolved here. Returns actual selectors, expressions/units, typed constraint, face and solution membership readback and provenance. Nonempty name/provenance required. Visible undo with verified creation rollback; does not save, solve or certify heat transfer. Reacquire face IDs after geometry/mesh/session changes. Supply operation_id for replay deduplication."""


NON_MODEL.add("nx_sim_environment_radiation")


def nx_sim_convection(
    document: str,
    faces: list[str],
    coefficient_w_m2_k: float,
    name: str,
    provenance: str,
    temperature_source: Literal[
        "fluid_ambient", "radiative_ambient", "specified"
    ] = "fluid_ambient",
    temperature_k: float | None = None,
):
    """Create assumed convection on 1..1000 distinct SIM occurrence face IDs from nx_sim_faces. Requires the active NX MULTIPHYSICS Thermal solution; Flow/coupled solutions are rejected to avoid imposing assumed convection on solved interfaces. coefficient_w_m2_k is positive finite W/(m² K). temperature_source selects fluid_ambient (default), radiative_ambient or specified. Only specified accepts temperature_k, a finite nonnegative Kelvin constant. Reads back active selectors, coefficient/temperature units, solution membership and faces; ambient dependency values are not resolved here. Coefficient uses the native top-side constant mode; shell-side options and time-dependent fields are not supported by this operation. Nonempty name/provenance required; provenance is stored as a native constraint attribute. Returns a typed constraint reference. Visible undo/rollback; does not save or solve. Reacquire selections after model/mesh/manual-session changes. Supply operation_id for safe retry."""


NON_MODEL.add("nx_sim_convection")


def nx_sim_constraints(
    document: str,
    offset: int = 0,
    limit: int = 20,
    include_properties: bool = False,
    include_targets: bool = False,
):
    """Inspect constraints in the active SIM and reacquire typed references after reopen. offset >=0; limit 1..100. Compact rows include type, target-set count and stored MCP provenance/basis when present. include_properties returns native values, units and explicit unsupported/read-failed fields. include_targets returns up to 100 members per set with truncation flags; SIM face members have typed refs, other kinds are marked unsupported. This covers the Constraints collection, not loads or simulation objects. Read-only: no activation, save, mutation or solve."""


READ_ONLY.add("nx_sim_constraints")


def nx_sim_distributed_heat(
    document: str,
    targets: list[str],
    kind: Literal["surface_flux", "volume_generation"],
    value: float,
    name: str,
    provenance: str,
    overlap_policy: Literal["reject", "allow_additive"] = "reject",
):
    """Create uniform internal heat on 1..1000 distinct SIM occurrence targets. surface_flux requires face IDs and nonnegative W/m^2; volume_generation requires body IDs from nx_sim_faces (direct FEM prototypes are resolved to occurrences) and nonnegative W/m^3. Requires the active NX MULTIPHYSICS Thermal SIM in the workspace. Returns committed value, units, selections, native properties and provenance. Duplicate exact-target heat assignments are rejected; face/body ownership overlaps are rejected unless overlap_policy=allow_additive explicitly identifies intended additive heat. Exact-target duplicates remain rejected. Distinct-body geometric intersections are not checked. Returns total applied watts from summed native FEM areas/volumes at constant density; this is neither geometric union nor solved heat flow. Requires millimeter SIM/FEM documents. Does not save or solve; existing results require revalidation. Native create/readback/rollback tested on NX 2606, numerical validation pending. Supply operation_id for safe retries."""


NON_MODEL.add("nx_sim_distributed_heat")


def nx_sim_heat_power(
    document: str,
    body: str,
    power_w: float,
    name: str,
    provenance: str,
    overlap_policy: Literal["reject", "allow_additive"] = "reject",
):
    """Assign total internal heat in finite nonnegative watts to one prototype FEM body ID from nx_sim_faces. Requires an active NX MULTIPHYSICS Thermal SIM with one direct FEM occurrence. Returns a typed simulation_load reference and committed SIM body/power readback. Rejects an existing heat load on that body and duplicate names. Nonempty provenance is stored on the native load. Only internal heat belongs here: do not add exported electrical energy or battery storage, or sum converter input and output as heat. Visible undo/rollback; does not save or solve. Coupled-flow, time-dependent and multi-body power assignment are not exposed here. Supply operation_id for safe retry. Face/body ownership overlaps are rejected by default; allow_additive explicitly permits separate intended contributions. Exact-target duplicate total-power loads remain rejected; distinct-body intersections are not checked."""


NON_MODEL.add("nx_sim_heat_power")


def nx_sim_loads(
    document: str,
    offset: int = 0,
    limit: int = 20,
    include_properties: bool = False,
    include_targets: bool = False,
):
    """Page loads in the active SIM and reacquire simulation_load references after reopen. offset >=0; limit 1..100. Compact rows include type, target-set count, stored provenance and energy-accounting label. Optional properties expose actual native values/units and unsupported reads. Optional targets return up to 100 members per set with counts/truncation flags; direct SIM body/face targets have typed references, other kinds are explicit unsupported targets. Does not sum mixed loads or infer total applied scenario power. Constraints and simulation objects are separate collections. Read-only; does not save, activate or solve."""


READ_ONLY.add("nx_sim_loads")


def nx_sim_temperature(
    document: str, faces: list[str], temperature_k: float, name: str, provenance: str
):
    """Create a prescribed absolute-temperature constraint on distinct SIM face IDs from nx_sim_faces. temperature_k is finite and nonnegative Kelvin, not Celsius. Requires the active NX MULTIPHYSICS Thermal solution. Returns typed constraint/face references, committed temperature and native property readback; provenance is stored on the constraint. Nonempty name/provenance required; duplicate names rejected. Uses verified creation rollback; does not save or solve. Time-varying temperatures and automatic overconstraint analysis are not supported here. Supply operation_id for safe retry."""


NON_MODEL.add("nx_sim_temperature")


def nx_sim_save(document: str):
    """Save one existing, fully loaded FEM or SIM at its workspace path. Creates and verifies a private backup of the previous disk file before calling NX Save with component saving and closing disabled. Checks unsaved-object counts, modified flag and other loaded document flags. Returns actual file hashes and backup path. Does not activate, save dependencies, delete backups or establish result freshness. Requires files within the 1 GiB hashing budget. Failure retains the backup and reports partial state; inspect before retrying. Supply operation_id for deduplication; save dependencies explicitly before saving their SIM."""


NON_MODEL.add("nx_sim_save")


def nx_sim_temperature_result(
    document: str,
    loadcase_index: int = 0,
    iteration_index: int = 0,
    location: Literal["nodal", "elemental", "element_nodal"] = "nodal",
):
    """Read minimum/maximum temperature in degC from the active SIM's selected field. Select nodal (default), elemental, or element_nodal explicitly; inventory lists available fields. In coupled results, nodal temperature may contain only solid values. Field location does not imply a semantic region filter. Use nx_sim_result_inventory to choose zero-based loadcase and iteration indices; indices must be nonnegative. Returns field, units, extrema, native location IDs, node count and typed owner document. Native location IDs belong only to that result revision and are not geometric face/node references. Preserves existing displayed result views. Does not activate, solve, save or establish freshness; result_freshness is not_verified. Averages, coordinates, region filters and junction-temperature interpretation are not provided by this operation. Audit model/mesh/job identities separately before engineering comparison."""


READ_ONLY.add("nx_sim_temperature_result")


def nx_sim_show_temperature(
    document: str, loadcase_index: int = 0, iteration_index: int = 0, name: str = "MCP temperature"
):
    """Create and activate a temperature postview in the visible Simcenter UI. Requires the selected SIM to be both work and display part. Choose zero-based result indices from nx_sim_result_inventory. Displays nodal temperature in Celsius, verifies field/indices/unit readback, and preserves existing views. Returns a session-local postview ID, not a stable geometry reference. Fits and refreshes the view and closes the Information window without clearing its contents; presentation failures return warnings. Does not save, solve, export an image or certify freshness. Use screenshot separately. New view creation is a mutation; supply operation_id to avoid duplicate views on retry. Invalid selections fail without creating a view; cleanup failures report partial state."""


NON_MODEL.add("nx_sim_show_temperature")


def nx_sim_mesh_quality(document: str, include_settings: bool = False):
    """Run native element-quality checks on all meshes in the selected standalone FEM. Returns tested element count, per-test counts/errors/warnings/worst values and summed issue occurrences (not unique failed elements). include_settings adds current solver quality criteria; element-specific overrides are flagged but not enumerated. Empty meshes/checks are errors. Does not activate, save, remesh, repair or solve. Native checks may highlight elements, so this is not classified read-only. A zero-error report does not establish mesh convergence, connected fluid regions or solve readiness."""


NON_MODEL.add("nx_sim_mesh_quality")


def nx_sim_solutions(
    document: str,
    offset: int = 0,
    limit: int = 20,
    include_properties: bool = False,
    include_execution_options: bool = False,
    include_membership: bool = False,
):
    """Page solutions in a loaded SIM with typed simulation_solution references, active flag, solver/analysis identifiers and step count. offset >=0, limit 1..100. Optional properties expose committed native solution values and explicit unsupported reads. include_execution_options separately reports the native solver-options table, including execution/parallelism/scratch settings and raw enum values; licence-related properties are excluded. Reading settings neither changes them nor tests solver availability. Does not activate, save or solve. include_membership optionally adds direct BC membership and ordered steps for each returned solution without activating it; unsupported folders/overrides are explicitly unverified, and this membership hash excludes boundary values. Expansion is bounded to 1000 steps per solution; use limit=1 for inspection. Result freshness requires separate inspection; references follow the owner SIM's session/generation lifetime."""


READ_ONLY.add("nx_sim_solutions")


def nx_sim_select_solution(document: str, solution: str):
    """Select an existing typed solution from nx_sim_solutions in the active SIM. Rejects wrong-owner or stale references, verifies ActiveSolution readback, and restores the prior selection on failure when possible. Already-active selection is a no-op with readback. Does not activate another document, save, change solver settings, launch a solve or refresh results. Subsequent loads/results tools operate on this selected solution. Supply operation_id for retry deduplication."""


NON_MODEL.add("nx_sim_select_solution")


def nx_sim_transient_setup(
    document: str,
    output_times_s: list[float],
    max_temperature_change_k: float = 0.05,
    min_time_step_s: float = 0.01,
):
    """Configure 2..200 absolute output times in seconds on the active NX MULTIPHYSICS Thermal solution. Times must start at zero and strictly increase; requires at least one existing thermal step and rejects extra existing steps rather than deleting them. Sets transient step type and output flag with native readback. Positive finite temperature-change/minimum-step settings are stored, but the installed time-method default is retained: their numerical effect is NOT verified and may be inactive; response warns explicitly. Actual integration times require solver-log inspection. Invalidates prior results; does not save or solve. Use only when no solver is running. Supply operation_id for safe retry; failures attempt NX undo and report partial recovery if undo fails."""


NON_MODEL.add("nx_sim_transient_setup")


def nx_sim_steps(
    document: str,
    solution: str,
    offset: int = 0,
    limit: int = 20,
    include_properties: bool = False,
    include_membership: bool = False,
):
    """Page steps/subcases of a typed solution belonging to the selected loaded SIM. offset >=0, limit 1..100. Returns owner-scoped simulation_step references, ordinal, native step type and active flag within the solution; optionally includes actual property values/units. include_membership adds direct BC/folder membership for returned steps only, flags unsupported folders, and does not infer inherited solution-level conditions. Supports inactive solutions without activating them. Ordinals change when steps are added/removed/reordered; typed references follow the existing owner generation lifetime. Stored settings are not proof of actual solver integration intervals. Does not modify, save or solve, and does not establish result freshness."""


READ_ONLY.add("nx_sim_steps")


def nx_sim_scalar_table(
    document: str,
    name: str,
    axis: Literal["time", "temperature"],
    quantity: Literal[
        "power", "temperature", "conductivity", "heat_capacity", "density", "convection"
    ],
    samples: list[list[float]],
    provenance: str,
):
    """Create a registered native 1D thermal field table in the active millimeter SIM. samples contains 2..1000 [axis,value] pairs with finite values and strictly increasing nonnegative axes. Axis units: time s, temperature K. Value units: power W, temperature K, conductivity W/(m K), heat_capacity J/(kg K), density kg/m³, convection W/(m² K). Temperature values must be nonnegative; other physical range requirements belong to the consuming load/material. Native temperature axes use Celsius: Kelvin inputs are explicitly converted and verified back in SI. Stores linear interpolation and native Undefined outside-table behavior; consumers must validate coverage before solving. Reads back all samples/units/interpolation against bounded checksummed provenance stored on the field. Returns a typed field, count/range/hash and compact readback; inspect samples via nx_sim_scalar_tables. Does not attach a load/material, save, solve or establish evaluator/solver behavior. Visible creation undo/rollback. Supply operation_id for deduplicated retry."""


NON_MODEL.add("nx_sim_scalar_table")


def nx_sim_scalar_tables(
    document: str, offset: int = 0, limit: int = 20, include_samples: bool = False
):
    """Page registered native scalar field tables in a loaded SIM. offset >=0; limit 1..100; include_samples defaults false. Verifies native 1D samples, unit conversion and interpolation against the model-owned manifest. Returns typed fields, counts, SI axis ranges, hashes and optional SI samples; corrupt/edited tables fail readback explicitly. Skips unregistered fields and separately registered fan curves. No activation, mutation, save, dependency binding or solve. Reacquire IDs after document closure; restart paging after changes. Stored interpolation is not evidence of solver behavior or whole-model freshness."""


READ_ONLY.add("nx_sim_scalar_tables")


def nx_sim_fan_table(
    document: str,
    name: str,
    points: list[tuple[float, float]],
    pressure_convention: Literal["static", "total"],
    rpm: float,
    reference_density_kg_m3: float,
    stall_region: str,
    provenance_kind: Literal["measured", "datasheet", "assumed"],
    provenance_source: str,
    scaling_rpm_range: list[float] | None = None,
    scaling_validity: str | None = None,
):
    """Create a native fan curve table in the active millimeter SIM. points contains 2..1000 [flow_m3_s, pressure_Pa] pairs with strictly increasing nonnegative flow; pressure must be finite. Positive RPM and density describe the source curve, not an imposed speed. Retains and reads back provenance and conventions in native attributes. Linear interpolation, undefined out-of-range values, no reverse-flow model. Duplicate names are rejected case-insensitively. Returns a typed simulation_field reference and SI readback. Does not attach a fan boundary, save, solve, scale RPM or establish static/total solver interpretation. Supply operation_id for retry deduplication."""


NON_MODEL.add("nx_sim_fan_table")


def nx_sim_scale_fan_table(document: str, source_field: str, name: str, rpm: float):
    """Create a derived native fan table from a verified MCP-owned source field in the active SIM. Requires source scaling_rpm_range and scaling_validity; target RPM must lie in that range. Uses same-geometry Q proportional to RPM and pressure proportional to RPM squared at unchanged reference density. Preserves pressure convention, interpolation, no-extrapolation/reverse-flow policy and validity assumptions. Derived provenance is assumed, with source checksum/RPM/density retained. Verifies native samples and metadata. Does not modify the source, attach a fan, save, solve, predict acoustics or calculate an operating point. Use operation_id for safe retry."""


NON_MODEL.add("nx_sim_scale_fan_table")


def nx_sim_fan_tables(
    document: str, offset: int = 0, limit: int = 20, include_samples: bool = False
):
    """Inspect MCP-owned fan tables in a selected loaded SIM, with typed references, owner context and retained curve conventions. Pages contain 1..100 tables; samples are omitted unless include_samples=true. Validates stored metadata checksum and actual table units/interpolation/samples against the manifest; corrupt metadata or changed samples raise errors. Unmanaged NX fields are excluded. Does not activate, save, attach fans or establish result freshness. References last until document close or bridge invalidation; reacquire after regeneration."""


READ_ONLY.add("nx_sim_fan_tables")


def nx_sim_objects(
    document: str,
    offset: int = 0,
    limit: int = 20,
    include_properties: bool = False,
    include_targets: bool = False,
):
    """Page the active SIM's SimulationObjects collection with typed references and native descriptors, including flow inlets/openings. Separate from nx_sim_loads and nx_sim_constraints. offset >= 0, limit 1..100. Optional committed properties include native units/defaults and opening head_loss coefficients for compare-and-set updates; target expansion reports at most 100 members per set with explicit truncation and unsupported target kinds. Inlets include actual fan mode, field reference and scale when present. Does not create, activate, save, solve or establish result freshness. Reacquire references after document close or geometry regeneration."""


READ_ONLY.add("nx_sim_objects")


def nx_sim_head_loss(
    document: str,
    opening: str,
    coefficient: float,
    expected_coefficient: float | None = None,
    name: str | None = None,
):
    """Set a finite nonnegative native dimensionless Head Loss coefficient on an Opening in the active NX MULTIPHYSICS Flow SIM. opening is a simulation_object ID from nx_sim_objects. Create with name and no expected_coefficient; update with expected_coefficient and no name. Conflicting actual values are rejected without mutation. Returns actual coefficient, previous value and table properties; rolls back failed updates. Zero adds no modeled opening restriction. K=0/K=2 response was tested on a synthetic duct, but a general pressure-loss convention is not independently verified. Not a porous-volume or loss-curve model. Checks known solvers are idle; does not save or solve. Changed settings require result revalidation. Supply operation_id for safe replay."""


NON_MODEL.add("nx_sim_head_loss")


def nx_sim_assign_fan(document: str, inlet: str, field: str):
    """Assign an MCP static-pressure fan table to an existing Inlet in the active NX MULTIPHYSICS Flow SIM. inlet is a simulation_object ID from nx_sim_objects; field is a simulation_field ID from nx_sim_fan_table(s). Both must belong to document. Audits curve values/conventions, checks known solver processes are absent, sets mode 5 and scale 1, and reads back the binding. Existing orientation and pressure references remain unchanged; motor heat is not assigned. Does not save or solve. Results become stale. Total-pressure and coupled assignment are not supported by this tested adapter. Supply operation_id for retry deduplication."""


NON_MODEL.add("nx_sim_assign_fan")


def nx_sim_job_log(
    job_id: str,
    log_name: str,
    job_folder: str = "simcenter-jobs",
    offset: int = 0,
    maximum_bytes: int = 8192,
    file_identity: str | None = None,
):
    """Read bounded complete lines from a log in a job's verified isolated output directory. log_name is an ASCII .log basename, never a path. maximum_bytes 256..65536; offset is a raw byte cursor from next_offset. Retain file_identity on subsequent calls to detect replacement. Holds incomplete trailing lines; rejects truncated/replaced files and overlong lines. Keyword-based licensing/credential-line redaction is limited, not a complete secret scanner. UTF-8 decoding uses replacement. Does not launch, cancel, update job state, or establish convergence; requires a responsive bridge and existing output ownership."""


READ_ONLY.add("nx_sim_job_log")


def nx_sim_job_logs(
    job_id: str, job_folder: str = "simcenter-jobs", offset: int = 0, limit: int = 20
):
    """List readable log basenames, sizes, modification times and file identities in the selected job's verified owned output directory. offset >= 0, limit 1..100. Direct ASCII .log files only; symlinks/device names excluded. Directory scan is bounded to 4096 entries. Live listing may change between pages; refresh as needed. Use returned log_name and file_identity with nx_sim_job_log. Does not read log contents or infer solver success."""


READ_ONLY.add("nx_sim_job_logs")


def nx_sim_pressure_result(
    document: str,
    field: Literal["pressure", "total_pressure"] = "pressure",
    loadcase_index: int = 0,
    iteration_index: int = 0,
):
    """Read element-nodal pressure or total-pressure extrema in Pa from the active SIM's native result. Returns native location IDs/sub-IDs and result indices; those are not geometry selection references. Pressure uses the native solution reference, not an inferred absolute/gauge convention. Requires an associated result containing the selected field. Does not activate, save, solve or infer convergence/freshness. Reacquire indices after results change; result_freshness remains not_verified."""


READ_ONLY.add("nx_sim_pressure_result")


def nx_sim_show_pressure(
    document: str,
    field: Literal["pressure", "total_pressure"] = "pressure",
    loadcase_index: int = 0,
    iteration_index: int = 0,
    name: str = "MCP pressure",
):
    """Create and display a pressure or total-pressure contour in Pa in the interactive Simcenter viewport. Requires the SIM as work and display document and an associated result. Preserves existing postviews, retains result ownership, and reads back field/unit/indices. Returns session-local postview ID. Fits and refreshes the view and closes the Information window without clearing its contents; presentation failures return warnings. Does not save, solve, infer pressure reference convention or validate result freshness. Use nx_screenshot afterward to retrieve the visible view. Supply operation_id for replay deduplication."""


NON_MODEL.add("nx_sim_show_pressure")


def nx_sim_prepare_solve(document: str, job_id: str, job_folder: str = "simcenter-jobs"):
    """Export native Thermal, Flow or Coupled Thermal-Flow input and reserve an immutable job, without solving. Coupled temperature and active specified-pressure export guards apply. Activate a standalone SIM saved in a fresh subfolder containing only that SIM; save/load all direct FEM/CAD dependencies first. job_id: 1..80 lowercase letters/digits/_/-, first alphanumeric. job_folder must be outside the native output folder. Checks known solver processes, exports with native setup checks, hashes saved dependencies and input, and permanently claims outputs. Same accepted job revalidates bytes without re-export; launched jobs only report their existing state. Retains partial files on failure. No saving, licence modification, solver launch, convergence or complete-dependency claim. Inspect the manifest through nx_sim_job_status. Supply operation_id for transport retry."""


NON_MODEL.add("nx_sim_prepare_solve")


def nx_sim_launch(document: str, job_id: str, job_folder: str = "simcenter-jobs"):
    """Launch one prepared Thermal/Flow job in native background mode. Requires the prepared SIM as work/display part, its unique active solution, unchanged saved dependencies/input and owned outputs, and no known host solver processes. Persists launch intent before calling NX; reusing the job ID never repeats a launch, even after a timeout. Returns API-observation state, not solver exit, convergence or validated results. Restores the native Foreground property; solving may modify SIM state and regenerate input, which requires subsequent auditing. Does not save documents or change licensing. Starts a bounded filesystem/process observer worker automatically; it does not use NX APIs and does not release the gate. Cancellation and exact process-to-job binding are not yet implemented. Use nx_sim_job_status and nx_sim_job_logs for observations. Supply operation_id for transport retry."""


NON_MODEL.add("nx_sim_launch")


def nx_sim_flow_log(
    job_id: str, log_name: str, job_folder: str = "simcenter-jobs", offset: int = 0, limit: int = 50
):
    """Inspect a directly owned steady-flow job log (maximum 8 MiB). log_name is a .log basename from nx_sim_job_logs. Returns paged equation residuals (offset >=0, limit 1..100), final residual-criterion observations, native percent imbalances and boundary flows in m3/s and kg/s with positive inflow convention. Reports native fan operating points in Pa and m3/s only when the observed pressure-unit header and fan/flow summaries are unambiguous; absent, incomplete or unsupported summaries have explicit states. Static/total pressure convention remains unverified by this log read. Preserves overflow markers and warns that rounded boundary sums are not exact balances. Returns the hash of bytes inspected; a growing file is not an immutable snapshot across pages. Never marks a job complete, accepts convergence, saves documents or changes solver state. Observed Simcenter 2606 single steady-history format only; unknown/incomplete tables cannot establish residual criteria."""


READ_ONLY.add("nx_sim_flow_log")


def nx_sim_release_job(job_id: str, job_folder: str = "simcenter-jobs"):
    """Release this job's workspace launch gate after a verified independent solver_exited observation. Rechecks owned log/result hashes, canonical input and known solver inactivity under an OS file lock. Preserves a durable release receipt before removing only the bridge gate record. Never deletes CAD, solver/results, permanent output ownership or job history; never permits relaunch of the old job. Missing/changed terminal evidence or foreign gate ownership is rejected. Retry after release leaves any newer owner's gate untouched. Does not accept numerical results or modify NX models. Current support requires the successful-output observer path; failed/cancelled gate recovery is not yet implemented. Supply operation_id for safe transport retry."""


NON_MODEL.add("nx_sim_release_job")


def nx_sim_observe_job(
    job_id: str, job_folder: str = "simcenter-jobs", maximum_seconds: int = 3600
):
    """Start or resume bounded observation of an already reserved job; never launch a solver. maximum_seconds 1..86400 (default 3600), poll interval 5 seconds. Reuses a live worker in this NX process without resetting its deadline; maximum_seconds applies only to a newly started worker and actual duration is returned. Terminal jobs need no worker. The worker performs filesystem/process checks only, records verified terminal evidence in durable job history, and writes at most 64 KiB to its returned log path. Query nx_sim_job_status for current thread liveness and persisted state. Observation timeout or NX process exit does not cancel the solver or permit relaunch; call this tool to resume observation after reconnect/restart. No CAD changes, licensing changes, cancellation or gate release. Exact process-to-job binding and failure classification remain incomplete."""


NON_MODEL.add("nx_sim_observe_job")


def nx_sim_descriptors(
    document: str,
    kind: Literal["load", "constraint", "solution_step"] = "load",
    offset: int = 0,
    limit: int = 50,
    name_contains: str | None = None,
):
    """Discover installed load/constraint names or allowable solution_step descriptors for a loaded SIM's selected solution, without activating it. Step discovery requires a SIM work part and returns native step_type_index values; it does not interpret step property enums. document is a live SIM ID; offset >=0, limit 1..100; optional name_contains is case-insensitive, at most 100 characters. Returns native names, solver/analysis/solution context and paginated cardinality; these are definitions, not instance IDs. UF enumeration does not establish that a builder can commit or that the licence is available. Simulation-object descriptors, including thermal contact, are not enumerated by this API. Does not create builders, modify models, save documents or change active selection."""


READ_ONLY.add("nx_sim_descriptors")


def nx_sim_scenario_preview(
    document: str,
    path: str,
    region_targets: dict[str, str],
    format: Literal["json", "csv"] = "json",
    metadata: dict | None = None,
):
    """Preview a heat scenario from a UTF-8 workspace JSON/CSV file, at most 1 MiB and 1000 sources. JSON uses HeatScenario schema version 1. CSV columns: name,region,watts,category,accounting_id,provenance_kind,provenance_source; supply metadata with name,workload_revision,ambient_K. region_targets maps every internal-heat region exactly once to a live FEM body ID from this SIM's face inventory. Rejects missing/unused mappings and duplicate targets. Returns scenario/file hashes, separate internal/exported/storage power totals, provenance and resolved references. Does not apply heat or ambient conditions, inspect existing load conflicts, activate documents or solve. Target validity applies at preview time only; application must revalidate."""


READ_ONLY.add("nx_sim_scenario_preview")


def nx_sim_scenario_apply(
    document: str,
    path: str,
    region_targets: dict[str, str],
    expected_preview_sha256: str,
    format: Literal["json", "csv"] = "json",
    metadata: dict | None = None,
):
    """Apply all internal-heat rows from a workspace scenario as one creation-only transaction. Uses the same JSON/CSV schema and exact mapping as nx_sim_scenario_preview, with fresh parsing and live target resolution. expected_preview_sha256 is required from preview; changes to file bytes, metadata, owner or mapped IDs are rejected before mutation. Requires an active standalone Thermal SIM with no existing loads and no known solver process. Rejects duplicate targets and case-insensitive load names before authoring. Verifies each committed watt value and total; failure rolls back the complete creation using one outer undo mark. Stores per-source provenance, accounting identity and scenario hash on each load. Returns separate excluded exported/storage totals. Ambient temperature is reported but NOT applied; boundary setup remains explicit. Does not save, solve, delete existing loads or accept stale results. Supply operation_id for idempotent transport retry."""


NON_MODEL.add("nx_sim_scenario_apply")


def nx_sim_open(path: str):
    """Open and display an existing workspace FEM/SIM by absolute NX-host or relative path. Reuses a loaded document instead of reopening it, preserving unsaved edits. Different loaded FEM/SIM files need distinct basenames even across extensions; conflicts are preflighted. Enters the simulation application and returns a live document reference, actual work/display paths, load issues and modified flags. Incomplete loading is an explicit error with retained session state. Native opening may mark a document modified; no automatic save or flag reset occurs. Requires no known solver process. Does not close other documents, change licensing, or establish result freshness. Activation may invalidate undo marks. Supply operation_id for transport retry; reacquire document IDs after close/reopen."""


NON_MODEL.add("nx_sim_open")


def nx_sim_close(document: str):
    """Close one loaded workspace FEM/SIM by live document ID, without saving or discarding unsaved edits. Rejects modified targets and FEMs referenced by loaded SIMs or assemblies. Requires no known solver process. Uses native DontCloseModified and reports every actual unloaded document, including any unused dependencies unloaded by NX. Invalidates their object references and recovery history even if native close partially fails. Returns remaining count and actual work/display paths; reacquire IDs before further work. Save approved changes explicitly with nx_sim_save first. Does not delete files or automatically close dependent analyses. Supply operation_id for transport retry."""


NON_MODEL.add("nx_sim_close")


def nx_sim_variant_plan(document: str, folder: str, name: str, saved_snapshot: bool = False):
    """Plan an independent saved-file SIM/FEM/CAD variant from a live SIM ID. Read-only: creates no folder and saves no edits. Requires fully loaded direct dependencies inside the workspace; assembly dependencies are rejected. folder must be new; name generates distinct loaded-safe basenames. Modified sources require explicit saved_snapshot=true, which excludes unsaved edits. Returns exact source/destination mapping, units, hashes and plan_sha256; total source hashing is bounded to 1 GiB. Use the same arguments and expected_plan_sha256 with nx_sim_variant_create. External inputs/results are not packaged."""


READ_ONLY.add("nx_sim_variant_plan")


def nx_sim_variant_create(
    document: str, folder: str, name: str, expected_plan_sha256: str, saved_snapshot: bool = False
):
    """Clone the saved SIM/FEM/CAD files from nx_sim_variant_plan using its exact arguments and required plan hash. Revalidates sources and saved native dependencies, persists intent before cloning, then verifies committed file hashes and unchanged loaded document flags. Requires no known solver process. Does not activate the copy, save edits or copy solver/results files. Open the returned SIM path explicitly to inspect dependency rebinding. A matching completed transaction returns its verified receipt; incomplete/changed output folders reject retry and retain partial files. Use nx_sim_variant_receipt after interruption, including after source documents close. This is not a complete analysis package or result-freshness certification. Supply operation_id for transport deduplication."""


NON_MODEL.add("nx_sim_variant_create")


def nx_sim_variant_receipt(folder: str, expected_plan_sha256: str):
    """Recover a saved-file clone receipt without requiring a live document ID. Read-only: validates the expected plan and current output hashes within a 1 GiB budget. Returns a historical committed clone, not a claim about current source revisions. Incomplete, missing, corrupt or changed receipts reject automatic retry; retain files for inspection. Does not rerun cloning, load files, save or solve."""


READ_ONLY.add("nx_sim_variant_receipt")


def nx_sim_external_temperature(
    document: str, boundaries: list[str], name: str, temperature_c: float
):
    """Assign specified external air temperature to 1..100 distinct Inlet/Opening IDs in an active NX MULTIPHYSICS Coupled Thermal-Flow SIM. temperature_c is finite Celsius above absolute zero. Creates one External Conditions table; verifies actual value, mode and all bindings. Rejects stale/foreign IDs, duplicate names and existing assignments. Does not change global ambient, humidity, pressure, mesh or solve. Results require revalidation. Does not save. Failure attempts native rollback with explicit partial status if recovery fails. Supply operation_id for safe replay. Only constant temperature is supported; global ambient export limitations remain separate."""


NON_MODEL.add("nx_sim_external_temperature")


def nx_sim_cancel(job_id: str, expected_revision: int, job_folder: str = "simcenter-jobs"):
    """Cancel an accepted job before launch using its inspected revision. Atomically prevents future launch; preserves inputs/results and permanent job identity. Safe replay returns the cancelled state. Once launch intent exists, returns NX_SIM_CANCELLATION_UNAVAILABLE: running native solver cancellation is not verified. Does not signal processes, release launch gates, modify CAD, or save documents. Use nx_sim_job_status to inspect state/revision. Supply operation_id for transport retry."""


NON_MODEL.add("nx_sim_cancel")


def nx_sim_contact(
    document: str,
    primary_faces: list[str],
    secondary_faces: list[str],
    mode: Literal["resistance", "conductance"],
    value: float,
    name: str,
    provenance: str,
):
    """Create native Contact Thermal Coupling between disjoint SIM CAE face sets (1..1000 each). Active NX MULTIPHYSICS Thermal only. mode resistance: positive total K/W; conductance: positive total W/K, Per Element disabled. No area normalization. Explicit primary/secondary regions; no override region or shell-side assignment. Returns actual native properties, typed targets and verified active-solution membership. Does not validate physical contact, mesh coupling, save or solve. Nonempty provenance stored on boundary. Uses undo/rollback; operation_id provides safe retry. Inspect via nx_sim_objects(include_properties=True, include_targets=True). Numerical acceptance remains unverified."""


NON_MODEL.add("nx_sim_contact")


def nx_sim_steady_thermal_controls(
    document: str,
    maximum_temperature_change_k: float,
    iteration_limit: int = 10000,
    relative_heat_balance: float | None = None,
):
    """Select explicit stopping controls for the active NX MULTIPHYSICS Thermal solution with steady steps only. Positive maximum_temperature_change_k is a temperature difference in kelvin. iteration_limit is a bounded integer 1..1000000. relative_heat_balance=None disables the additional heat-balance check; otherwise supply a fraction in (0,1], not percent, to select Global Fraction mode. Requires an existing associated Thermal Parameters table. Returns committed selectors, values, native units, typed table/solution references and prior state. Does not claim Automatic-mode semantics, numerical convergence or complete freshness. Uses undo/rollback; no save, export or solve. Supply operation_id for replay. Inspect linked properties through nx_sim_solutions(include_properties=True)."""


NON_MODEL.add("nx_sim_steady_thermal_controls")


def nx_sim_heat_schedule(
    document: str,
    body: str,
    field: str,
    name: str,
    provenance: str,
    scale: float = 1.0,
    overlap_policy: Literal["reject", "allow_additive"] = "reject",
):
    """Bind a registered time/power scalar table to one body as total internal watts in the active Thermal SIM. body is a direct FEM prototype ID from nx_sim_faces; field is a simulation_field ID from nx_sim_scalar_table(s). Requires transient steps and table coverage from zero through every configured end time. Scale and scaled powers must be finite and nonnegative. Reads back the native field definition, separate scale, single-body target and global solution membership; no step-specific activation claim. Preserves linear/undefined-outside table settings. Rejects duplicate body sources and overlaps by default; allow_additive permits distinct intended overlapping contributions. Does not modify the table, time settings, save or solve. Later schedule/step edits require revalidation. Numerical behavior remains unverified. Supply operation_id for safe replay."""


NON_MODEL.add("nx_sim_heat_schedule")


def nx_sim_temperature_material(
    document: str,
    name: str,
    conductivity_samples: list[list[float]],
    heat_capacity_samples: list[list[float]],
    density_kg_m3: float,
    provenance: str,
):
    """Create an isotropic thermal material in the active millimeter FEM with temperature-dependent conductivity and heat capacity, and constant density. Samples are 2..1000 [temperature_K,value] pairs per property; values use W/(m K) and J/(kg K), respectively, and must be positive. Axes are nonnegative and strictly increasing; their domains must overlap. Density must be positive finite kg/m³. Name 1..80 characters; provenance required. Creates registered native fields named name_K and name_CP, converts Kelvin axes to native Celsius, and checks full committed definitions, scale 1, control selectors 0 and SI density. Linear interpolation, undefined outside the tables; returns their common domain without claiming actual solution temperatures stay inside it. Atomic creation rollback covers material, field and expression identities. Returns typed material/field references, values and provenance. Does not assign collectors, save or solve; use nx_sim_assign_material with inspected collector state. No phase change, anisotropy, temperature-dependent density or numerical acceptance is implied. Supply operation_id for safe replay."""


NON_MODEL.add("nx_sim_temperature_material")
