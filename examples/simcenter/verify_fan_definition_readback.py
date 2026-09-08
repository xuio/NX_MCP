"""Read supported fan definitions from native wrappers without solving or saving."""


def run(executor):
    import importlib
    import json
    from pathlib import Path

    import NXOpen as nx

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    module = importlib.reload(importlib.import_module("nx_mcp.simcenter.properties"))
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    import shutil

    from nx_mcp.simcenter.fan_boundary import assign_static_fan
    from nx_mcp.simcenter.fan_field import create_fan_table

    root = executor.workspace.resolve("ui-benchmarks/F1-fan-definition-20260909-r1")
    if root.exists():
        raise ValueError("Inspect retained fixture before retry")
    root.mkdir()
    source = executor.workspace.resolve(
        "ui-benchmarks/D-head-loss-mcp-20260908-r1/head_loss_test_r1.sim"
    )
    target = root / "f1_fan_definition_r1.sim"
    shutil.copy2(source, target)
    executor._sim_open(str(target))
    sim = executor.session.Parts.BaseWork
    curve = {
        "name": "Definition readback fixture",
        "pressure_convention": "static",
        "rpm": 1000,
        "reference_density_kg_m3": 1.2,
        "points": [
            {"flow_m3_s": 0.0, "pressure_Pa": 1.0},
            {"flow_m3_s": 0.0004, "pressure_Pa": 0.0},
        ],
        "stall_region": "Synthetic fixture",
        "provenance": {"kind": "assumed", "source": "API readback test"},
    }
    field = create_fan_table(executor.session, sim, curve)["table"]
    inlet = next(b for b in sim.Simulation.SimulationObjects if b.DescriptorName == "Inlet")
    assign_static_fan(executor.session, sim, inlet, field)
    wrapper = inlet.PropertyTable.GetScalarFieldWrapperPropertyValue("Fan Curve")
    matches = []
    for scale in (1.0, 2.0):
        wrapper.SetField(field, scale)
        row = next(
            r for r in module.read_properties(inlet.PropertyTable, nx) if r["name"] == "Fan Curve"
        )
        assert "inspection_status" not in row, row
        assert row["field_scale"] == scale
        assert row["field_definition"]["native_samples_si"] == {
            "flow_m3_s": [0.0, 0.0004],
            "pressure_Pa": [1.0, 0.0],
        }
        matches.append(
            {
                "document": executor._reference(sim, "part", sim, "SIM")["id"],
                "boundary": inlet.JournalIdentifier,
                "row": row,
            }
        )
    assert matches[0]["row"]["field_definition"] == matches[1]["row"]["field_definition"]
    wrapper.SetField(field, 1.0)
    after = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    assert all(after.get(path) == value for path, value in flags.items())
    result = {
        "passed": True,
        "matches": matches,
        "modified_flags_preserved": True,
        "solver_launched": False,
        "scope": "Native registered fan-table definition and scalar scale readback",
    }
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\fan-definition-readback.json").write_text(
        json.dumps(result, indent=2)
    )
    return result
