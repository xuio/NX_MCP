"""Create standalone FEM/SIM associations for an existing saved user CAD part."""

import hashlib

from nx_mcp.runtime import NXToolError


def analysis_environment(analysis_type):
    if analysis_type == "thermal":
        return "Thermal", "Thermal"
    if analysis_type == "coupled_thermal_flow":
        return "Coupled Thermal-Flow", "Thermal-Flow"
    raise NXToolError(
        "NX_INVALID_ARGUMENT", "analysis_type must be thermal or coupled_thermal_flow"
    )


def initialize_steady_thermal(sim, solution, native):
    """Use the NX 2606 descriptors verified by the native conduction benchmark."""
    tables = []
    for descriptor, key in (
        ("Thermal Parameters", "Thermal Parameters"),
        ("Multiphysics Thermal Output Requests", "Thermal Output Requests"),
    ):
        table = sim.ModelingObjectPropertyTables.CreateModelingObjectPropertyTable(
            descriptor, "NX MULTIPHYSICS - Thermal", "NX MULTIPHYSICS", key, 0
        )
        solution.PropertyTable.SetNamedPropertyTablePropertyValue(key, table)
        committed = solution.PropertyTable.GetNamedPropertyTablePropertyValue(key)
        if committed != table:
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Thermal table association differs")
        tables.append(
            {"property": key, "descriptor": committed.DescriptorType, "name": committed.Name}
        )
    descriptor = native.Sf.SolutionAskDescriptorNx(solution.Tag)
    allowed = [
        native.Sfl.StepDescriptorAskNameNx(
            native.Sfl.SolutionAskNthAllowableStepDescriptorNx(descriptor, i)
        )
        for i in range(solution.AllowedStepTypeCount)
    ]
    if allowed.count("Step - Thermal") != 1:
        raise NXToolError("NX_SIM_STEP_UNAVAILABLE", "Expected one Step - Thermal descriptor")
    step = solution.CreateStep(allowed.index("Step - Thermal"), True, "Conduction")
    step.PropertyTable.SetIntegerPropertyValue("Solution Type", 0)
    if (
        step.PropertyTable.GetIntegerPropertyValue("Solution Type") != 0
        or solution.ActiveStep != step
    ):
        raise NXToolError("NX_SIM_READBACK_MISMATCH", "Active steady thermal step differs")
    return {
        "parameter_tables": tables,
        "step": {
            "name": step.Name,
            "descriptor": "Step - Thermal",
            "active": True,
            "solution_type": 0,
        },
    }


def create(executor, cad, folder, name, analysis_type="coupled_thermal_flow"):
    analysis, solution_type = analysis_environment(analysis_type)
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    nx, session = executor.nxopen, executor.session
    if not isinstance(cad, nx.Part):
        raise NXToolError("NX_SIM_DOCUMENT_TYPE", "Select an ordinary CAD .prt document")
    source = executor.workspace.resolve(cad.FullPath)
    if not source.is_file() or cad.IsModified:
        raise NXToolError(
            "NX_SIM_PRECONDITION", "Save the selected CAD explicitly before creating associations"
        )
    if cad.PartUnits != nx.BasePart.Units.Millimeters or not list(cad.Bodies):
        raise NXToolError(
            "NX_SIM_PRECONDITION", "Requires millimeter CAD with directly owned bodies"
        )
    if (
        cad.ComponentAssembly.RootComponent is not None
        and cad.ComponentAssembly.RootComponent.GetChildren()
    ):
        raise NXToolError(
            "NX_SIM_UNSUPPORTED",
            "Assembly FEM creation is not supported; select a standalone CAD part",
        )
    if not isinstance(name, str) or not name.strip():
        raise NXToolError("NX_INVALID_ARGUMENT", "Supply a solution name")
    target = executor.workspace.resolve(folder)
    if target.exists():
        raise NXToolError("NX_SIM_TARGET_EXISTS", "Use a fresh analysis folder")
    require_solver_idle()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    prefix = "analysis_" + hashlib.sha256(str(target).encode()).hexdigest()[:12]
    paths = {"fem": target / (prefix + "_mesh.fem"), "sim": target / (prefix + "_analysis.sim")}
    if any(p.Name.casefold() in {v.name.casefold() for v in paths.values()} for p in session.Parts):
        raise NXToolError("NX_SIM_NAME_CONFLICT", "Analysis basename already loaded")
    before_context = session.Parts.BaseWork, session.Parts.BaseDisplay
    opened = []
    target.mkdir(parents=True)
    stage = "fem"
    try:
        fem = session.Parts.NewBaseDisplay(str(paths["fem"]), nx.BasePart.Units.Millimeters)
        opened.append(fem)
        options = fem.NewFemCreationOptions()
        try:
            options.SetCadData(cad, "")
            options.SetSolverOptions(
                "NX MULTIPHYSICS",
                analysis,
                cae.BaseFemPart.AxisymAbstractionType.NotSet,
            )
            options.SetGeometryOptions(
                cae.FemCreationOptions.UseBodiesOption.AllBodies, [], fem.NewFemSynchronizeOptions()
            )
            fem.FinalizeCreation(options)
        finally:
            options.Dispose()
        stage = "sim"
        sim = session.Parts.NewBaseDisplay(str(paths["sim"]), nx.BasePart.Units.Millimeters)
        opened.append(sim)
        sim.FinalizeCreation(fem, ["NX MCP user CAD association"])
        solution = sim.Simulation.CreateSolution(
            "NX MULTIPHYSICS",
            analysis,
            solution_type,
            name,
            cae.SimSimulation.AxisymAbstractionType.NotSet,
        )
        if (
            sim.FemPart != fem
            or solution.AnalysisType != analysis
            or solution.SolutionType != solution_type
            or solution.SolverType != "NX MULTIPHYSICS"
        ):
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "SIM/FEM or solution association differs")
        # Inspection uses the installed CAD association property, never a filename inference.
        if fem.MasterCadPart != cad:
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "FEM master CAD association differs")
        if len(list(fem.Bodies)) != len(list(cad.Bodies)):
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "FEM body count differs from selected CAD"
            )
        initialization = None
        if analysis_type == "thermal":
            stage = "thermal_initialization"
            import NXOpen.UF as uf

            initialization = initialize_steady_thermal(sim, solution, uf.UFSession.GetUFSession())
        stage = "save"
        for part in (fem, sim):
            status = part.Save(
                nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue
            )
            if status:
                status.Dispose()
        if cad.IsModified or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise NXToolError(
                "NX_SIM_SOURCE_CHANGED", "Source CAD changed during association creation"
            )
        session.Parts.SetWork(sim)
        session.ApplicationSwitchImmediate("UG_APP_SFEM")
        from nx_mcp.simcenter.postviews import present_result

        presentation = present_result(session, sim)
        return {
            "cad": executor._reference(cad, "part", cad, "CAD"),
            "fem": executor._reference(fem, "part", fem, "FEM"),
            "sim": executor._reference(sim, "part", sim, "SIM"),
            "paths": {k: str(v) for k, v in paths.items()},
            "source_sha256": digest,
            "source_preserved": True,
            "body_count": len(list(fem.Bodies)),
            "geometry_association": "all CAD bodies",
            "cad_shared": True,
            "solution": solution.Name,
            "analysis_type": analysis_type,
            "initialization": initialization,
            "presentation": presentation,
            "next_step": (
                "Assign mesh, materials, thermal contacts, loads and boundary conditions"
                if analysis_type == "thermal"
                else "Create initial step and attach defaults with nx_sim_flow_setup; initialize coupled_steady before environment"
            ),
            "saved": True,
            "meshed": False,
            "solver_launched": False,
        }
    except Exception as error:
        issues = []
        for part in reversed(opened):
            try:
                part.Close(
                    nx.BasePart.CloseWholeTree.FalseValue,
                    nx.BasePart.CloseModified.CloseModified,
                    None,
                )
            except Exception as cleanup:
                issues.append(
                    {"stage": "close_new", "nx_code": getattr(cleanup, "ErrorCode", None)}
                )
        try:
            work, display = before_context
            if display is not None:
                _, status = session.Parts.SetDisplay(display, False, False)
                if status:
                    status.Dispose()
            if work is not None:
                session.Parts.SetWork(work)
        except Exception:
            issues.append({"stage": "restore_context"})
        raise NXToolError(
            "NX_SIM_CREATION_FAILED",
            "Analysis creation failed; partial files retained, source CAD not saved",
            nx_code=getattr(error, "nx_code", getattr(error, "ErrorCode", None)),
            details={
                "stage": stage,
                "mutation_outcome": "partial",
                "cleanup_issues": issues,
                "paths": {k: str(v) for k, v in paths.items()},
                "cause": str(error),
            },
        ) from error
