"""Read both native pressure fields from the isolated completed fan result."""


def run(executor):
    import importlib

    from nx_mcp.simcenter import flow_results

    importlib.reload(flow_results)
    sim = executor.session.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Isolated cavity SIM required")
    return {
        "fields": [
            flow_results.pressure_extrema(executor.session, sim, field=field)
            for field in ("pressure", "total_pressure")
        ],
        "scope": "native extraction only; model/job freshness must be audited separately",
    }
