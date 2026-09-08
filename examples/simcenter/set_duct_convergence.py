"""Persist tighter controls in the isolated duct benchmark and verify export."""


def run(executor):
    import hashlib
    import json
    import shutil
    import xml.etree.ElementTree as ET
    from pathlib import Path

    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.flow_controls import configure_convergence

    session = executor.session
    sim = session.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Isolated duct SIM required")
    root = Path(sim.FullPath).parent
    record = root / "flow-convergence-01.json"
    if record.exists():
        return {"replayed": True, "receipt": json.loads(record.read_text())}
    backup = root / "before-flow-convergence-01"
    backup.mkdir(exist_ok=False)
    shutil.copy2(sim.FullPath, backup / Path(sim.FullPath).name)
    data = {"state": "accepted", "saved": False, "solver_launched": False, "backup": str(backup)}
    with record.open("x") as stream:
        json.dump(data, stream)
    try:
        data["configuration"] = configure_convergence(
            session, sim, residual=1e-6, flow_imbalance_fraction=0.001, iteration_limit=1000
        )
        status = sim.Save(
            nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue
        )
        status.Dispose()
        data["saved"] = True
        sim.Simulation.ActiveSolution.Solve(
            cae.SimSolutionSolveOption.WriteSolverInputFile,
            cae.SimSolutionSetupCheckOption.CompleteCheckAndOutputErrors,
        )
        raw = (root / "benchmark_4ba7072a1d7a_analysis-Flow_benchmark.xml").read_bytes()
        tree = ET.fromstring(raw)
        expected = {
            "Maximum Residuals": 1e-6,
            "Global Flow Imbalance Fraction": 0.001,
            "Global Flow Imbalance Fraction Option": 1,
            "3D Flow Steady State - Iteration Limit": 1000,
        }
        actual = {}
        for name, value in expected.items():
            values = [
                float(p.findtext("Value")) for p in tree.iter("Property") if p.get("name") == name
            ]
            if values != [value]:
                raise ValueError("Export mismatch for " + name + ": " + str(values))
            actual[name] = values[0]
        data.update(
            state="export_verified",
            exported=actual,
            deck_sha256=hashlib.sha256(raw).hexdigest(),
            prior_results_require_revalidation=True,
        )
    except Exception as error:
        data.update(
            state="failed",
            error=str(error),
            nx_code=getattr(error, "ErrorCode", None),
            mutation_outcome="partial",
            next_step="Inspect current controls and saved backup; do not launch from an unverified export",
        )
        raise
    finally:
        record.write_text(json.dumps(data, indent=2))
    return data
