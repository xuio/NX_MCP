"""Installed API evidence, distinct from numerical or licence acceptance."""

from __future__ import annotations

import importlib
from pathlib import Path

# Names verified against the installed 2606 Python binding, not inferred from .NET.
OPERATIONS = {
    "fem_create": ("FemPart", "NewFemCreationOptions", "FinalizeCreation"),
    "sim_create": ("SimPart", "FinalizeCreation"),
    "solution_create": ("SimSimulation", "CreateSolution"),
    "tetrahedral_mesh": ("Mesh3dTetBuilder", "CommitMesh"),
    "boundary_conditions": ("SimSimulation", "CreateBcBuilderForLoadDescriptor"),
    "solution_chain_solve": ("SimSolveManager", "SolveChainOfSolutions"),
    "single_solution_solve": ("SimSolution", "Solve"),
}


# Native release evidence is version-scoped and does not imply current licence availability.
TESTED_ADAPTERS = {
    "single_solution_solve": (
        "nx_sim_launch",
        "Prepared NX MULTIPHYSICS Flow background launch and automatic terminal observation; cancellation and numerical acceptance separate",
    ),
    "fem_create": (
        "nx_sim_create_benchmark",
        "new millimeter FEM associated with isolated block CAD",
    ),
    "sim_create": ("nx_sim_create_benchmark", "new SIM associated with benchmark FEM"),
    "solution_create": ("nx_sim_create_benchmark", "NX MULTIPHYSICS / Thermal / Thermal"),
    "tetrahedral_mesh": (
        "nx_sim_mesh",
        "linear solid tetrahedra; 496 elements / 196 nodes at 5 mm",
    ),
}


def inspect_capabilities(session):
    """Read installed files and Python members; never manipulate licence state."""
    root = Path(session.GetEnvironmentVariableValue("UGII_BASE_DIR"))
    try:
        cae = importlib.import_module("NXOpen.CAE")
    except ImportError:
        cae = None
    version = session.GetEnvironmentVariableValue("UGII_VERSION")
    from nx_mcp.simcenter.release_evidence import public_evidence

    operations = []
    for name, (class_name, *members) in OPERATIONS.items():
        cls = getattr(cae, class_name, None)
        available = cls is not None and all(hasattr(cls, m) for m in members)
        operations.append(
            {
                "capability": name,
                "api": [f"NXOpen.CAE.{class_name}.{m}" for m in members],
                "api_present": available,
                "status": (
                    "module_missing"
                    if cae is None
                    else "unsupported_by_api"
                    if not available
                    else "implemented_and_tested"
                    if name in TESTED_ADAPTERS and version == "v2606"
                    else "implemented_but_untested"
                    if name in TESTED_ADAPTERS
                    else "api_present_not_implemented"
                ),
                "adapter": TESTED_ADAPTERS.get(name, (None, None))[0],
                "tested_scope": TESTED_ADAPTERS.get(name, (None, None))[1],
                "tested_version": "v2606" if name in TESTED_ADAPTERS else None,
                "current_session_operation_test": "not_tested",
                "licence_checkout": "not_tested",
                "numerical_acceptance": "not_tested",
            }
        )
    executables = []
    for relative in (
        "NXBIN/simcenter3d.exe",
        "THERMALFLOW/tmgsolver/com/tmg.exe",
        "THERMALFLOW/tmgsolver/com/tmgexec.exe",
    ):
        path = root / relative
        executables.append(
            {"path": str(path), "present": path.is_file(), "execution_tested": False}
        )
    return {
        "nx_version": session.GetEnvironmentVariableValue("UGII_VERSION"),
        "installation_root": str(root),
        "cae_module_present": cae is not None,
        "solver_catalog": solver_catalog(session)
        if cae is not None
        else {"state": "module_missing"},
        "operations": operations,
        "public_tool_evidence": public_evidence(version),
        "unresolved_native_findings": [
            {
                "capability": "coupled_solution_controls",
                "status": "descriptor_mapping_unresolved",
                "tested_version": "v2606",
                "tested_language": "NX MULTIPHYSICS - Coupled Thermal-Flow",
                "property": "Coupled Solution Parameters",
                "rejected_descriptor": "Coupled Solution Parameters",
                "nx_code": 3520001,
                "rollback_verified": True,
                "licence_availability": "not_established_by_descriptor_failure",
                "next_step": "Determine the native control-table descriptor from a supported catalog or a recorded native command; do not launch an unvalidated coupled model",
                "evidence": "tests/simcenter/evidence/native-coupled-setup-mcp.json",
            },
            {
                "capability": "thermal_contact",
                "status": "descriptor_mapping_unresolved",
                "tested_version": "v2606",
                "tested_language": "NX MULTIPHYSICS - Thermal",
                "candidates": ["Interface Resistance", "Thermal Coupling"],
                "additional_native_probe": {
                    "rejected": ["Advanced Thermal Coupling", "Convection Coupling"],
                    "builder_accepted": "Radiation Thermal Coupling",
                    "radiation_target_sets": 2,
                    "radiation_committed": False,
                    "radiation_solved": False,
                    "scope": "Builder initialization and property inspection only; radiation does not establish conductive contact support",
                    "evidence": "tests/simcenter/evidence/native-contact-alternative-descriptors.json",
                },
                "solver_display_name": "Simcenter 3D Multiphysics",
                "active_language_matches_solution": True,
                "network_failure": "not_indicated_by_native_descriptor_rejection",
                "candidate_source": "installed UGII/command_finder/cae_lang_commands.xml",
                "builder_nx_code": 1543292,
                "legacy_creation_nx_code": 3520001,
                "rollback_verified": True,
                "licence_availability": "not_established_by_descriptor_failures",
                "journal_probe": {
                    "record_start_stop": "tested",
                    "contact_command_recorded": False,
                    "ui_obstacle": "Loads and Conditions tab exposes no accessibility action",
                },
                "next_step": "Obtain a journal of an actual native contact command; recorder alone does not establish the descriptor mapping",
                "evidence": "tests/simcenter/evidence/native-contact-context.json",
                "historical_evidence": "tests/simcenter/evidence/native-contact-descriptors.json",
            }
        ]
        if version == "v2606"
        else [],
        "executables": executables,
        "licensing_configuration_modified": False,
        "concurrency": {
            "nx_session_mutations": "serialized_on_nx_ui_thread",
            "external_solver_parallelism": "not_validated",
        },
        "warnings": [
            "API and executable presence do not establish a usable licence or a validated solve."
        ],
    }


def solver_catalog(session):
    """Enumerate descriptors with UF_SFL; the installed API requires an active SIM."""
    import NXOpen.UF as uf

    work = session.Parts.BaseWork
    if work is None or type(work).__name__ != "SimPart":
        return {
            "state": "requires_active_sim",
            "languages": [],
            "next_step": "Create or activate an isolated SIM document, then repeat discovery",
        }
    native = uf.UFSession.GetUFSession()
    rows = []
    solver_count = native.Sfl.AskNumSolversNx()
    if solver_count > 100:
        return {"state": "inventory_limit", "languages": [], "solver_count": solver_count}
    for i in range(solver_count):
        solver = native.Sfl.AskNthSolverNx(i)
        count = native.Sfl.AskNumLanguagesNx(solver)
        if count > 100:
            raise ValueError("Native solver language count exceeds the supported inventory limit")
        for j in range(count):
            language = native.Sfl.AskNthLanguageNx(solver, j)
            info = native.Sf.AskLanguage(language)
            name = info[0]
            if not any(word in name.lower() for word in ("thermal", "flow", "acoustic")):
                continue
            descriptors = {}
            for key, count_fn, nth_fn, name_fn in (
                (
                    "solutions",
                    native.Sfl.AskNumSolutionDescriptorsNx,
                    native.Sfl.AskNthSolutionDescriptorNx,
                    native.Sfl.SolutionDescriptorAskNameNx,
                ),
                (
                    "loads",
                    native.Sfl.AskNumLoadDescriptorsNx,
                    native.Sfl.AskNthLoadDescriptorNx,
                    native.Sfl.AskLoadDescriptorNameNx,
                ),
                (
                    "constraints",
                    native.Sfl.AskNumBcDescriptorsNx,
                    native.Sfl.AskNthBcDescriptorNx,
                    native.Sfl.AskBcDescriptorNameNx,
                ),
            ):
                total = count_fn(language)
                if total > 1000:
                    raise ValueError(
                        "Native descriptor count exceeds the supported inventory limit"
                    )
                descriptors[key] = [name_fn(nth_fn(language, k)) for k in range(total)]
            rows.append(
                {
                    "language": name,
                    "descriptors": descriptors,
                    "solver_checkout": "not_tested",
                    "solve_acceptance": "not_tested",
                }
            )
    return {
        "state": "enumerated",
        "languages": rows,
        "solver_count": solver_count,
        "scope": "descriptors registered in this NX session; not licence availability",
    }
