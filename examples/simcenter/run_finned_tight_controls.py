"""Same-mesh numerical-control check before comparing spatial refinement."""


def iteration_limit_for(variant):
    """Explicit budgets prevent new diagnostic variants silently inheriting defaults."""
    if variant in ("stock_copy", "material_contrast"):
        return 100
    if variant == "layer_extended":
        return 1200
    if variant in ("layer_fine", "tight", "refined", "fine"):
        return None  # Preserve the retained mesh-study input settings.
    raise ValueError("No reviewed iteration budget for this fixture variant")


def run(executor, *, variant="tight"):
    import json
    import time
    import xml.etree.ElementTree as ET

    import NXOpen as nx

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    iteration_limit = iteration_limit_for(variant)
    require_solver_idle()
    cases = {
        "material_contrast": (
            "E-finned-material_contrast-20260908-r1",
            "E-finned-material-contrast-run-20260908-r1",
            "finned_material_contrast_run_r1",
            "coupled-finned-material-contrast-r1",
        ),
        "stock_copy": (
            "E-finned-stock_copy-20260908-r1",
            "E-finned-stock-copy-run-20260908-r1",
            "finned_stock_copy_run_r1",
            "coupled-finned-stock-copy-r1",
        ),
        "layer_extended": (
            "E-finned-layer_fine-run-20260908-r1",
            "E-finned-layer-extended-20260908-r1",
            "finned_layer_extended_r1",
            "coupled-finned-layer-extended-r1",
        ),
        "layer_fine": (
            "E-finned-layer_fine-20260908-r1",
            "E-finned-layer_fine-run-20260908-r1",
            "finned_layer_fine_run_r1",
            "coupled-finned-layer-fine-r1",
        ),
        "tight": (
            "E-finned-run-20260908-r2",
            "E-finned-tight-20260908-r1",
            "finned_tight_r1",
            "coupled-finned-tight-r1",
        ),
        "refined": (
            "E-finned-refined-20260908-r1",
            "E-finned-refined-run-20260908-r1",
            "finned_refined_run_r1",
            "coupled-finned-refined-r1",
        ),
        "fine": (
            "E-finned-fine-20260908-r1",
            "E-finned-fine-run-20260908-r1",
            "finned_fine_run_r1",
            "coupled-finned-fine-r1",
        ),
    }
    if variant not in cases:
        raise ValueError("Select a bounded mesh-study case")
    source_folder, run_folder, basename, job_id = cases[variant]
    sim = executor.session.Parts.BaseWork
    if source_folder not in sim.FullPath:
        raise ValueError("Activate the completed finned baseline")
    receipt = executor.workspace.resolve(f"ui-benchmarks/E-finned-{variant}-r1.json")
    if receipt.exists():
        return {"existing_receipt": json.loads(receipt.read_text()), "solver_relaunched": False}
    rows = {"acceptance": False, "mesh_changed": False, "job_id": job_id}

    def record(key, value):
        rows[key] = value
        receipt.write_text(json.dumps(rows, indent=2))

    record(
        "copy",
        executor._sim_save_as(
            executor._reference(sim, "part", sim, "SIM")["id"],
            f"ui-benchmarks/{run_folder}/{basename}.sim",
        ),
    )
    solution = sim.Simulation.ActiveSolution
    settings = []
    mark = executor.session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "MCP finned numerical controls"
    )
    try:
        for table_key, values in (
            (
                "Flow Solution Parameters",
                {
                    "Maximum Residuals": 1e-6,
                    "Global Flow Imbalance Fraction": 0.001,
                    "Global Heat Imbalance Fraction": 0.001,
                },
            ),
            (
                "Coupled Solution Parameters",
                {
                    "Coupled Solver Maximum Temperature Change": 0.001,
                    "Coupled Solver Global Heat Imbalance Fraction": 1e-4,
                },
            ),
        ):
            props = solution.PropertyTable.GetNamedPropertyTablePropertyValue(
                table_key
            ).PropertyTable
            for key, value in values.items():
                old, unit = props.GetBaseScalarWithDataPropertyValue(key)
                props.SetBaseScalarWithDataPropertyValue(key, value, unit)
                actual, actual_unit = props.GetBaseScalarWithDataPropertyValue(key)
                assert actual == value and actual_unit == unit
                settings.append(
                    {
                        "table": table_key,
                        "property": key,
                        "previous": old,
                        "value": actual,
                        "units": unit.Name if unit else "dimensionless",
                    }
                )
            if table_key == "Flow Solution Parameters":
                assert props.GetIntegerPropertyValue("Convergence Criteria") == 1
                for key in (
                    "Global Flow Imbalance Fraction Option",
                    "Global Heat Imbalance Fraction Option",
                ):
                    props.SetBooleanPropertyValue(key, True)
                    assert props.GetBooleanPropertyValue(key)
        if iteration_limit is not None:
            # The retained 500-iteration run decayed steadily but did not converge.
            # Increase only the bounded budget, never relax the convergence targets.
            for table_key, key in (
                ("Thermal Parameters", "Thermal Steady State - Iteration Limit"),
                ("Flow Solution Parameters", "3D Flow Steady State - Iteration Limit"),
            ):
                props = solution.PropertyTable.GetNamedPropertyTablePropertyValue(
                    table_key
                ).PropertyTable
                props.SetIntegerPropertyValue(key, iteration_limit)
                actual = props.GetIntegerPropertyValue(key)
                assert actual == iteration_limit
                settings.append(
                    {"table": table_key, "property": key, "value": actual, "units": "iterations"}
                )
            props = solution.PropertyTable.GetNamedPropertyTablePropertyValue(
                "Thermal-Flow Output Requests"
            ).PropertyTable
            for key in ("Fluid Densities", "Mass Fluxes"):
                props.SetBooleanPropertyValue(key, True)
                assert props.GetBooleanPropertyValue(key)
                settings.append(
                    {
                        "table": "Thermal-Flow Output Requests",
                        "property": key,
                        "value": 1,
                        "units": "boolean",
                    }
                )
        record("settings", settings)
    except Exception:
        executor.session.UndoToMark(mark, None)
        raise
    status = sim.Save(nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue)
    if status:
        status.Dispose()
    sid = executor._reference(sim, "part", sim, "SIM")["id"]
    started = time.monotonic()
    prepared = executor._sim_prepare_solve(sid, rows["job_id"])
    record("prepare", prepared)
    record("prepare_seconds", time.monotonic() - started)
    xml = ET.parse(prepared["input_path"]).getroot()
    for setting in settings:
        values = xml.findall(".//Property[@name='" + setting["property"] + "']/Value")
        assert len(values) == 1, setting
        assert abs(float(values[0].text) - setting["value"]) < 1e-12, setting
    record("exported_controls_match", True)
    record("launch_intent", "Inspect existing job after interruption; never relaunch")
    record("launch", executor._sim_launch(sid, rows["job_id"]))
    return rows
