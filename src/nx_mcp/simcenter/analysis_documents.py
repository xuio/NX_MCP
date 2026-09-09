"""Create standalone FEM/SIM associations for an existing saved user CAD part."""

import hashlib

from nx_mcp.runtime import NXToolError


def create(executor, cad, folder, name):
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
                "Coupled Thermal-Flow",
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
            "Coupled Thermal-Flow",
            "Thermal-Flow",
            name,
            cae.SimSimulation.AxisymAbstractionType.NotSet,
        )
        if sim.FemPart != fem or solution.AnalysisType != "Coupled Thermal-Flow":
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "SIM/FEM or solution association differs")
        # Inspection uses the installed CAD association property, never a filename inference.
        if fem.MasterCadPart != cad:
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "FEM master CAD association differs")
        if len(list(fem.Bodies)) != len(list(cad.Bodies)):
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "FEM body count differs from selected CAD"
            )
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
            "presentation": presentation,
            "next_step": "Create initial step and attach defaults with nx_sim_flow_setup; initialize coupled_steady before environment",
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
