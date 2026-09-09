"""Verify restored mesh and save only the isolated guard fixture documents."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    env = dict(os.environ)
    env.update(
        PYTHONPATH=r"C:\ProgramData\BasementHypervisor\nx-mcp-simcenter\source\src",
        NX_MCP_ENABLE_SIMCENTER="1",
        NX_MCP_ENABLE_EXPERIMENTAL="1",
        NX_MCP_WORKSPACE=r"D:\CAD\SIMCENTER_MCP_WORKSPACE",
        NX_MCP_BRIDGE_DESCRIPTOR=r"C:\Users\cadadmin\AppData\Local\nx-mcp\simcenter-bridge.json",
        NX_MCP_SURFACE="full",
    )
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "nx_mcp.server"], env=env
    )
    receipt = {"responses": {}}
    output = shared / "mesh-guard-saved-public.json"

    def record():
        output.write_text(json.dumps(receipt, indent=2))

    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()

        async def call(label, name, args, error=False):
            response = await client.call_tool(name, args)
            receipt["responses"][label] = response.model_dump(mode="json")
            record()
            assert bool(response.isError) == error, response
            return response.structuredContent

        restored = json.loads((shared / "mesh-guard-restoration.json").read_text())
        assert restored["restored"] and restored["fuse_restored"] and not restored["fuse_calls"]
        fem = await call("open_fem", "nx_sim_open", {"path": restored["fem_path"]})
        fid = fem["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": fid})
        state = await call("state", "nx_sim_mesh_state", {"document": fid})
        assert state["mesh_state"] == restored["mesh_state"]
        await call("save_fem", "nx_sim_save", {"document": fid})
        sim = await call("open_sim", "nx_sim_open", {"path": restored["sim_path"]})
        await call("save_sim", "nx_sim_save", {"document": sim["document"]["id"]})
        job = await call("cancelled_job", "nx_sim_job_status", {"job_id": "mesh-guard-r1"})
        assert job["state"] == "cancelled"
        receipt.update(passed=True, solver_launched=False)
        record()


if __name__ == "__main__":
    asyncio.run(main())
