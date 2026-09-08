def run(executor):
    import importlib

    import nx_mcp.simcenter.result_identity as identity

    importlib.reload(identity)
    from nx_mcp.workspace import Workspace

    sim = executor.session.Parts.BaseWork
    if "C-transient-fine-20260908" not in sim.FullPath:
        raise ValueError("Requires isolated benchmark")
    return identity.inspect_result_identity(
        sim.Simulation.ActiveSolution, Workspace(r"D:\CAD\SIMCENTER_MCP_WORKSPACE")
    )
