"""Launch the fixed uniform-heating conduction fixture once; not a public solve API."""


def run(executor):
    import hashlib
    from pathlib import Path

    import NXOpen.CAE as cae

    sim = executor.session.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or not sim.FullPath.endswith(
        r"A-thermal-export-20260908-r1\thermal_input_r1.sim"
    ):
        raise ValueError("Expected isolated thermal export SIM")
    root = Path(sim.FullPath).parent
    deck = root / "thermal_input_r1-Conduction.xml"
    raw = deck.read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != "7d0a49b3d7336e79f5dfc45808880f81fd3bf800bef8152c8e5d6bf9bd593708"
    ):
        raise ValueError("Expected independently audited thermal input")
    solution = sim.Simulation.ActiveSolution
    if solution.SolverType != "NX MULTIPHYSICS" or solution.AnalysisType != "Thermal":
        raise ValueError("Wrong solution")
    fem = sim.FemPart
    em, nm = fem.BaseFEModel.FeelementLabelMap, fem.BaseFEModel.FenodeLabelMap
    try:
        if (em.NumElements, nm.NumNodes) != (2658, 756):
            raise ValueError("Mesh changed")
    finally:
        em.Dispose()
        nm.Dispose()
    data = {
        "job_id": "isolated-thermal-01",
        "expected_maximum_rise_k": 2.5,
        "power_w": 1,
        "fixed_temperature_k": 293.15,
        "scope": "Uniform volumetric heating conduction fixture; numerical audit pending",
    }
    import importlib

    import nx_mcp.simcenter.jobs as jobs_module

    importlib.reload(jobs_module)
    for name in (
        "result_identity",
        "solver_log",
        "solver_manifest",
        "revisions",
        "prepared_input",
        "output_claims",
        "launch",
    ):
        importlib.reload(importlib.import_module("nx_mcp.simcenter." + name))

    from nx_mcp.simcenter.dependencies import inspect_direct
    from nx_mcp.simcenter.jobs import JobStore
    from nx_mcp.simcenter.launch import launch_isolated
    from nx_mcp.simcenter.prepared_input import capture_prepared_input, validate_prepared_input
    from nx_mcp.simcenter.solver_manifest import input_identity, preserve_input

    store = JobStore(executor.workspace, "ui-benchmarks/A-thermal-export-20260908-r1/jobs")
    manifest = {
        key: value
        for key, value in data.items()
        if key
        not in ("created_at", "state", "solver_launched", "deck_sha256", "numerical_validation")
    }
    manifest["input_xml_content_sha256"] = input_identity(raw)["xml_content_sha256"]
    manifest["analysis_path"] = sim.FullPath

    dependencies = inspect_direct(executor.session, sim, executor.workspace)
    if dependencies["unresolved"]:
        raise ValueError("Unresolved native dependencies")
    doc_rows = [{k: v for k, v in row.items() if k != "part"} for row in dependencies["rows"]]
    manifest["prepared_input"] = capture_prepared_input(executor.workspace, str(deck), doc_rows)
    manifest["dependency_scope"] = dependencies["scope"]
    manifest["excluded_dependencies"] = dependencies["excluded"]

    def native_launch():
        import subprocess

        check = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "@(Get-Process -Name niece_solver,mpiexec,tmg,tmgexec,nx2tmg -ErrorAction SilentlyContinue).Count",
            ],
            capture_output=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if check.returncode or check.stdout.decode().strip() != "0":
            raise ValueError("Another solver/translator exists or process preflight failed")
        current = inspect_direct(executor.session, sim, executor.workspace)
        current_rows = [{k: v for k, v in row.items() if k != "part"} for row in current["rows"]]
        validate_prepared_input(executor.workspace, manifest["prepared_input"], current_rows)
        preserve_input(
            executor.workspace.ensure_inside(store.root / "isolated-thermal-01"),
            "before-launch",
            raw,
        )
        sol = sim.Simulation.ActiveSolution
        old = sol.PropertyTable.GetBooleanPropertyValue("Foreground")
        try:
            sol.PropertyTable.SetBooleanPropertyValue("Foreground", False)
            if sol.PropertyTable.GetBooleanPropertyValue("Foreground"):
                raise ValueError("Background solve setting did not commit")
            sol.Solve(
                cae.SimSolutionSolveOption.Solve,
                cae.SimSolutionSetupCheckOption.CompleteCheckAndOutputErrors,
            )
        finally:
            sol.PropertyTable.SetBooleanPropertyValue("Foreground", old)
        return {
            "background_launch_requested": True,
            "foreground_setting_restored": sol.PropertyTable.GetBooleanPropertyValue("Foreground")
            == old,
        }

    return {
        "job": launch_isolated(
            store, "isolated-thermal-01", manifest, native_launch, output_directory=str(root)
        ),
        "scope": "actual native asynchronous launch with durable intent; process/result audit remains separate",
    }
