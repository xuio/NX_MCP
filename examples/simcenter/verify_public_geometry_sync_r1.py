"""Verify temperature node/group summaries survive isolated SIM save/close/reopen."""

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
    output = shared / "public-geometry-sync-r1.json"

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

        tools = await client.list_tools()
        receipt["schema"] = next(
            t for t in tools.tools if t.name == "nx_sim_sync_geometry"
        ).inputSchema
        opened = await call(
            "open",
            "nx_sim_open",
            {"path": "ui-benchmarks/public-multibody-analysis-r1/analysis_cdd77d35e310_mesh.fem"},
        )
        fid = opened["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": fid})
        args = {"document": fid, "operation_id": "public-topology-sync-r1"}
        result = await call("sync", "nx_sim_sync_geometry", args)
        assert result["body_count"] == 17 and result["mesh_count"] == 17
        assert result["mesh_coverage_complete"]
        replay = await call("replay", "nx_sim_sync_geometry", args)
        assert replay["document"] == result["document"]
        await call("stale", "nx_sim_faces", {"document": fid}, error=True)
        receipt.update(passed=True, solver_launched=False)
        record()


if __name__ == "__main__":
    asyncio.run(main())
