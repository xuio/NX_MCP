def run(executor):
    import importlib
    import json
    from pathlib import Path

    import nx_mcp.simcenter.flow as flow

    importlib.reload(flow)
    s = executor.session
    sim = s.Parts.BaseWork
    if "D-flow-mcp-20260908" not in sim.FullPath:
        raise ValueError("Requires isolated MCP Flow fixture")
    record = Path(sim.FullPath).parent / "flow-tables-01.json"
    if record.exists():
        return {"replayed": True, "receipt": json.loads(record.read_text())}
    receipt = flow.attach_default_tables(s, sim, "MCP flow")
    with record.open("x") as f:
        json.dump(receipt, f, indent=2)
    return receipt
